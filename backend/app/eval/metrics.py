"""
GradeWise evaluation metrics.

Pure-Python, zero hard dependencies (stdlib only) so the scoring math is auditable
and trustworthy. The headline metric is Quadratic Weighted Kappa (QWK), the standard
for ordinal agreement in automated grading.

Validated against the hand-computed example in the test suite and equivalent to
sklearn's `cohen_kappa_score(y_true, y_pred, weights="quadratic")`.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping, Sequence


# --------------------------------------------------------------------------- #
# Rating helpers
# --------------------------------------------------------------------------- #

def score_to_rating(score: float, max_score: float, n_levels: int) -> int:
    """
    Bin a (possibly continuous) score onto an ordinal rating in [0, n_levels - 1].

    QWK requires discrete ordinal categories. Grading scores are often continuous
    (e.g. 7.5 / 10), so bin them consistently for both human and AI scores before
    computing kappa.

    >>> score_to_rating(0, 10, 11)
    0
    >>> score_to_rating(10, 10, 11)
    10
    >>> score_to_rating(7.5, 10, 11)
    8
    """
    if n_levels < 1:
        raise ValueError("n_levels must be >= 1")
    if max_score <= 0:
        raise ValueError("max_score must be > 0")
    frac = min(max(score / max_score, 0.0), 1.0)
    rating = round(frac * (n_levels - 1))
    return int(rating)


# --------------------------------------------------------------------------- #
# Quadratic Weighted Kappa
# --------------------------------------------------------------------------- #

def quadratic_weighted_kappa(
    y_true: Sequence[int],
    y_pred: Sequence[int],
    min_rating: int | None = None,
    max_rating: int | None = None,
) -> float:
    """
    Quadratic Weighted Kappa between two sets of integer ordinal ratings.

    Returns a value in [-1, 1]:
        1.0  = perfect agreement
        0.0  = agreement no better than chance
        < 0  = worse than chance

    Ratings must already be integers (use `score_to_rating` to bin continuous scores).
    If `min_rating`/`max_rating` are not given they are inferred from the data.

    Matches sklearn's cohen_kappa_score(..., weights="quadratic").
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have equal length")
    if len(y_true) == 0:
        raise ValueError("cannot compute kappa on empty input")

    if min_rating is None:
        min_rating = min(min(y_true), min(y_pred))
    if max_rating is None:
        max_rating = max(max(y_true), max(y_pred))

    n = max_rating - min_rating + 1
    if n == 1:
        # Only one possible rating -> all items agree by definition.
        return 1.0

    # Observed confusion matrix O[true][pred]
    O = [[0] * n for _ in range(n)]
    for t, p in zip(y_true, y_pred):
        O[t - min_rating][p - min_rating] += 1

    total = len(y_true)

    # Marginal histograms
    hist_true = [0] * n
    hist_pred = [0] * n
    for i in range(n):
        for j in range(n):
            hist_true[i] += O[i][j]
            hist_pred[j] += O[i][j]

    # Quadratic weights w[i][j] = (i - j)^2 / (n - 1)^2
    denom = (n - 1) ** 2
    num_term = 0.0  # sum(w * O)
    den_term = 0.0  # sum(w * E)
    for i in range(n):
        for j in range(n):
            w = ((i - j) ** 2) / denom
            expected = (hist_true[i] * hist_pred[j]) / total
            num_term += w * O[i][j]
            den_term += w * expected

    if den_term == 0:
        # No expected disagreement (e.g. one rating dominates entirely).
        return 1.0
    return 1.0 - (num_term / den_term)


# Convenience alias
def qwk(
    y_true: Sequence[int],
    y_pred: Sequence[int],
    min_rating: int | None = None,
    max_rating: int | None = None,
) -> float:
    return quadratic_weighted_kappa(y_true, y_pred, min_rating, max_rating)


# --------------------------------------------------------------------------- #
# Cohen's Kappa (unweighted) -- for pass/fail or nominal rubrics
# --------------------------------------------------------------------------- #

def cohen_kappa(y_true: Sequence, y_pred: Sequence) -> float:
    """Unweighted Cohen's Kappa. Use for binary/pass-fail rubrics."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have equal length")
    if len(y_true) == 0:
        raise ValueError("cannot compute kappa on empty input")

    total = len(y_true)
    labels = sorted(set(y_true) | set(y_pred))
    idx = {lab: k for k, lab in enumerate(labels)}
    n = len(labels)
    if n == 1:
        return 1.0

    O = [[0] * n for _ in range(n)]
    for t, p in zip(y_true, y_pred):
        O[idx[t]][idx[p]] += 1

    observed_agreement = sum(O[i][i] for i in range(n)) / total

    hist_true = [sum(O[i]) for i in range(n)]
    hist_pred = [sum(O[i][j] for i in range(n)) for j in range(n)]
    expected_agreement = sum(
        (hist_true[i] / total) * (hist_pred[i] / total) for i in range(n)
    )

    if expected_agreement == 1.0:
        return 1.0
    return (observed_agreement - expected_agreement) / (1.0 - expected_agreement)


# --------------------------------------------------------------------------- #
# Per-criterion accuracy
# --------------------------------------------------------------------------- #

def per_criterion_accuracy(
    predicted: Sequence[Mapping[str, float]],
    gold: Sequence[Mapping[str, float]],
    tolerance: float = 0.0,
) -> dict[str, dict[str, float]]:
    """
    Per-criterion grading agreement.

    `predicted` and `gold` are aligned lists; each element maps criterion_id -> points.
    For each criterion returns:
        - mae:        mean absolute error of awarded points
        - within_tol: fraction of items where |pred - gold| <= tolerance
        - n:          number of items the criterion appeared in

    This is the metric that tells you *where* grading breaks down, criterion by
    criterion, rather than only an aggregate score.
    """
    if len(predicted) != len(gold):
        raise ValueError("predicted and gold must have equal length")

    errors: dict[str, list[float]] = {}
    hits: dict[str, int] = {}
    counts: dict[str, int] = {}

    for pred_row, gold_row in zip(predicted, gold):
        for cid, gold_pts in gold_row.items():
            if cid not in pred_row:
                continue
            err = abs(pred_row[cid] - gold_pts)
            errors.setdefault(cid, []).append(err)
            hits[cid] = hits.get(cid, 0) + (1 if err <= tolerance else 0)
            counts[cid] = counts.get(cid, 0) + 1

    result: dict[str, dict[str, float]] = {}
    for cid, errs in errors.items():
        result[cid] = {
            "mae": sum(errs) / len(errs),
            "within_tol": hits[cid] / counts[cid],
            "n": counts[cid],
        }
    return result


# --------------------------------------------------------------------------- #
# Feedback faithfulness (LLM-as-judge, injectable)
# --------------------------------------------------------------------------- #

FAITHFULNESS_JUDGE_PROMPT = """You are auditing AI-generated grading feedback for faithfulness.

You are given:
- REFERENCE: the authoritative reference material used for grading.
- FEEDBACK: the AI's feedback to the student.

Identify each distinct factual/grading CLAIM in FEEDBACK (e.g. "the answer omits the base case",
"the formula is incorrect"). For each claim decide whether it is SUPPORTED by REFERENCE
(directly traceable) or UNSUPPORTED (asserted without basis in the reference).

Respond with ONLY a JSON object, no prose, no markdown fences:
{"total_claims": <int>, "supported_claims": <int>}
"""


def feedback_faithfulness(
    feedbacks: Sequence[str],
    references: Sequence[str],
    judge_fn=None,
) -> float | None:
    """
    Fraction of feedback claims traceable to the reference (0..1).

    `judge_fn(prompt, feedback, reference) -> dict` must return
    {"total_claims": int, "supported_claims": int}. Inject your Gemini call here.

    Returns None (skipped) if no judge_fn is supplied, so the harness stays runnable
    without a live model. The judge prompt is `FAITHFULNESS_JUDGE_PROMPT`.
    """
    if judge_fn is None:
        return None
    if len(feedbacks) != len(references):
        raise ValueError("feedbacks and references must have equal length")

    total = 0
    supported = 0
    for fb, ref in zip(feedbacks, references):
        verdict = judge_fn(FAITHFULNESS_JUDGE_PROMPT, fb, ref)
        total += int(verdict.get("total_claims", 0))
        supported += int(verdict.get("supported_claims", 0))
    if total == 0:
        return None
    return supported / total


# --------------------------------------------------------------------------- #
# Percentiles (stdlib-only, used by the harness for latency)
# --------------------------------------------------------------------------- #

def percentile(values: Iterable[float], pct: float) -> float:
    """Linear-interpolation percentile. pct in [0, 100]."""
    data = sorted(values)
    if not data:
        return float("nan")
    if len(data) == 1:
        return data[0]
    rank = (pct / 100.0) * (len(data) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(data) - 1)
    frac = rank - lo
    return data[lo] + (data[hi] - data[lo]) * frac
