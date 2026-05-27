"""
Evaluation harness — the accuracy machinery you wire into CI.

A 'golden set' is a JSONL file of records that real instructors have graded.
This harness runs each record through your grading pipeline (via the
`grade_fn` callback) and reports how closely the AI agrees with the humans.

USAGE
  python -m eval.run_eval --golden eval/golden_set.example.jsonl

THE RULE
  No prompt change, model change, or pipeline change ships to production
  without re-running this and confirming none of the three core metrics
  regress vs the previous release:

      1. Mean absolute score error  (lower is better)
      2. Within ±1 mark              (higher is better)
      3. Rubric criterion agreement  (higher is better)

WHEN TO ADD A RECORD
  - A real instructor grades a real submission you can capture (best signal).
  - You find an adversarial case worth pinning (gibberish, prompt injection,
    rubric edge case, non-native English, mixed Urdu/English, etc.).

WIRING TO THE REAL PIPELINE
  Replace `_stub_grade` at the bottom of this file with a call into your
  feedback_pipeline once Phase 6 is built. Until then the stub returns the
  human grade unchanged so the harness can be exercised end-to-end.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable


# ---- Golden-set record ------------------------------------------------------

@dataclass
class GoldenRecord:
    id: str
    subject_id: str
    assignment_id: str
    student_answer: str
    instructor_overall_score: float
    instructor_max_score: float
    instructor_rubric_scores: dict[str, float]   # {criterion_id_or_name: score}
    notes: str = ""
    # Optional extras you may capture later:
    instructor_uid: str = ""
    submission_id: str = ""


@dataclass
class EvalResult:
    record_id: str
    ai_overall: float
    instructor_overall: float
    abs_error: float
    within_one_mark: bool
    rubric_agreement: float                     # 0..1
    missing_criteria: list[str] = field(default_factory=list)
    extra_criteria: list[str] = field(default_factory=list)


# ---- IO ---------------------------------------------------------------------

def load_golden(path: Path) -> list[GoldenRecord]:
    records: list[GoldenRecord] = []
    with path.open() as f:
        for line_no, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw or raw.startswith("//"):
                continue
            try:
                d = json.loads(raw)
                records.append(GoldenRecord(**d))
            except Exception as e:                                  # noqa: BLE001
                raise ValueError(f"Bad golden record on line {line_no}: {e}") from e
    return records


# ---- Eval -------------------------------------------------------------------

async def evaluate(
    records: list[GoldenRecord],
    grade_fn: Callable[[GoldenRecord], Awaitable[dict]],
) -> list[EvalResult]:
    results: list[EvalResult] = []
    for rec in records:
        ai = await grade_fn(rec)

        ai_overall = float(ai["overallScore"])
        abs_err = abs(ai_overall - rec.instructor_overall_score)
        within_one = abs_err <= 1.0

        ai_rubric: dict[str, float] = {
            item["criterion"]: float(item["score"])
            for item in ai.get("rubricScores", [])
        }
        inst_rubric = rec.instructor_rubric_scores

        matches = 0
        total = max(1, len(inst_rubric))
        missing: list[str] = []
        for cid, inst_score in inst_rubric.items():
            ai_score = ai_rubric.get(cid)
            if ai_score is None:
                missing.append(cid)
            elif abs(ai_score - inst_score) <= 1.0:
                matches += 1
        extra = [c for c in ai_rubric if c not in inst_rubric]

        results.append(EvalResult(
            record_id=rec.id,
            ai_overall=ai_overall,
            instructor_overall=rec.instructor_overall_score,
            abs_error=abs_err,
            within_one_mark=within_one,
            rubric_agreement=matches / total,
            missing_criteria=missing,
            extra_criteria=extra,
        ))
    return results


def report(results: list[EvalResult]) -> dict:
    if not results:
        print("No records.")
        return {}

    abs_errors = [r.abs_error for r in results]
    within_one_pct = 100 * sum(1 for r in results if r.within_one_mark) / len(results)
    rubric_avg_pct = statistics.mean(r.rubric_agreement for r in results) * 100

    print(f"Records evaluated:        {len(results)}")
    print(f"Mean abs score error:     {statistics.mean(abs_errors):.2f}")
    print(f"Median abs score error:   {statistics.median(abs_errors):.2f}")
    print(f"Within ±1 mark:           {within_one_pct:.1f}%")
    print(f"Rubric criterion agree:   {rubric_avg_pct:.1f}%")
    print()
    print("Worst 5 by abs error:")
    for r in sorted(results, key=lambda x: -x.abs_error)[:5]:
        print(f"  {r.record_id:>20}  AI={r.ai_overall:6.2f}  inst={r.instructor_overall:6.2f}  err={r.abs_error:.2f}")

    return {
        "n": len(results),
        "mean_abs_error": statistics.mean(abs_errors),
        "median_abs_error": statistics.median(abs_errors),
        "within_one_mark_pct": within_one_pct,
        "rubric_agree_pct": rubric_avg_pct,
    }


# ---- Stub grader (replace with real pipeline in Phase 6) -------------------

async def _stub_grade(rec: GoldenRecord) -> dict:
    """Returns the human grade unchanged. Use only to exercise the harness."""
    return {
        "overallScore": rec.instructor_overall_score,
        "rubricScores": [
            {"criterion": cid, "score": s, "maxScore": 10}
            for cid, s in rec.instructor_rubric_scores.items()
        ],
    }


# ---- CLI --------------------------------------------------------------------

async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--golden", required=True, type=Path,
                   help="Path to a JSONL golden-set file.")
    p.add_argument("--out", type=Path, default=None,
                   help="Optional path to write per-record JSON results.")
    args = p.parse_args()

    records = load_golden(args.golden)
    results = await evaluate(records, _stub_grade)
    summary = report(results)

    if args.out:
        args.out.write_text(json.dumps({
            "summary": summary,
            "results": [r.__dict__ for r in results],
        }, indent=2))
        print(f"\nWrote {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
