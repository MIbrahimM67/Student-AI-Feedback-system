"""Measured text similarity for instructor review; never adjusts rubric marks."""
from collections import Counter
from datetime import datetime, timezone
import json
import math
import re
import uuid
from app.db.postgres import get_conn


def compare_texts(texts: list[str]) -> list[list[float]]:
    tokens = [re.findall(r'\w+', text.lower()) for text in texts]
    frequencies = Counter(word for words in tokens for word in set(words))
    vectors = [
        {word: count * (math.log((1 + len(texts)) / (1 + frequencies[word])) + 1)
         for word, count in Counter(words).items()}
        for words in tokens
    ]
    norms = [math.sqrt(sum(value * value for value in vector.values())) for vector in vectors]
    shingles = [set(tuple(words[i:i + 3]) for i in range(max(0, len(words) - 2))) for words in tokens]
    matrix = [[0.0] * len(texts) for _ in texts]
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if not norms[i] or not norms[j]:
                continue
            cosine = sum(value * vectors[j].get(word, 0) for word, value in vectors[i].items()) / (norms[i] * norms[j])
            union = shingles[i] | shingles[j]
            overlap = len(shingles[i] & shingles[j]) / len(union) if union else cosine
            score = round(min(100.0, (0.4 * cosine + 0.6 * overlap) * 100), 2)
            matrix[i][j] = matrix[j][i] = score
    return matrix


async def refresh_internal_similarity(org_id: str, assignment_id: str, batch_id: str | None = None) -> None:
    from app.services.entitlements import assignment_owner_is_verified
    async with get_conn(org_id) as conn:
        enabled = await conn.fetchval('SELECT internal_similarity_enabled FROM assignments WHERE id=$1', assignment_id)
        # Only the approved faculty owner (or an admin) may run this job.
        if not enabled or not await assignment_owner_is_verified(conn, assignment_id):
            return
        batch_size = await conn.fetchval('SELECT count(*) FROM submissions WHERE batch_id=$1', batch_id) if batch_id else 0
        rows = await conn.fetch(
            "SELECT s.id,s.batch_id,s.student_name,s.file_name,s.input_text FROM submissions s "
            "JOIN subjects subject ON subject.id=s.subject_id "
            "WHERE s.assignment_id=$1 AND s.status IN ('graded','approved','published') "
            "AND ($2::uuid IS NULL OR s.batch_id=$2) AND length(trim(coalesce(s.input_text,'')))>0 "
            "ORDER BY s.created_at DESC,s.id LIMIT 30",
            assignment_id, batch_id if batch_size > 1 else None,
        )
        matrix = compare_texts([r['input_text'] for r in rows])
        for i, row in enumerate(rows):
            matches = sorted([
                {'type':'internal_similarity','method':'tfidf_and_word_trigrams',
                 'sourceSubmissionId':str(other['id']),
                 'sourceName':f"{other['student_name'] or 'Student'} ({other['file_name'] or 'submission'})",
                 'matchedText':other['input_text'][:350], 'similarity':matrix[i][j],
                 'scope':'same_batch' if batch_size > 1 else 'same_assignment',
                 'note':'Text overlap is evidence for review, not proof of plagiarism.'}
                for j, other in enumerate(rows) if i != j and matrix[i][j] >= 15
            ],key=lambda match:match['similarity'],reverse=True)[:5]
            score = max((matrix[i][j] for j in range(len(rows)) if j != i),default=None)
            # Refresh both earlier and later reports so upload order does not hide matches.
            await conn.execute('DELETE FROM plagiarism_reports WHERE submission_id=$1', row['id'])
            await conn.execute(
                'INSERT INTO plagiarism_reports(id,org_id,submission_id,batch_id,similarity_score,matches,created_at) VALUES($1,$2,$3,$4,$5,$6,$7)',
                str(uuid.uuid4()), org_id, row['id'], row['batch_id'], score, json.dumps(matches), datetime.now(timezone.utc),
            )
