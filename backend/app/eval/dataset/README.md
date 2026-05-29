# Held-Out Evaluation Dataset — Schema & Requirements

## Purpose

This directory contains the held-out dataset used by `harness.py` to compute
Quadratic Weighted Kappa (QWK) between AI grading and human grading.

**Nothing ships without a measured QWK delta against baseline.**

---

## Dataset Schema

Each item in the dataset (JSON array in `dataset.json`) must have:

```json
{
  "id": "unique-submission-id",
  "submission": {
    "path": "path/to/submission/file",
    "type": "text | handwritten | coding",
    "question_text": "...",
    "assignment_id": "uuid"
  },
  "human_score": 7,
  "human_max_score": 10,
  "human_per_criterion": {
    "criterion_1": 3.0,
    "criterion_2": 2.0,
    "criterion_3": 2.0
  },
  "grader_ids": ["grader_a", "grader_b"],
  "notes": "Optional notes about this submission"
}
```

---

## Requirements

> **IMPORTANT: 2+ human graders per item are needed to establish the human-vs-human
> QWK ceiling. You cannot expect the AI to exceed inter-rater agreement.**

1. **Minimum dataset size:** 50+ submissions for meaningful QWK (recommend 100+).
2. **Multi-grader:** Each submission should be independently graded by at least 2
   human graders. Use the average (or majority) as `human_score`.
3. **Human ceiling:** Compute QWK between grader_a and grader_b scores first.
   This is the ceiling — AI QWK should approach but not be expected to exceed it.
4. **Stratified:** Include a mix of submission types (text, handwritten, coding)
   and quality levels (strong, average, weak).

---

## Baseline Procedure

Before changing any pipeline code:

1. Run the **current system** against this dataset.
2. Record the result in `baselines/current_pipeline.json`.
3. All future changes are measured as delta against this baseline.

```bash
# From backend/
python -m app.eval.run_baseline
```

---

## Current Status

⚠️ **No human-graded data collected yet.**

Placeholder `dataset.json` is empty. The harness runs against a stub grader
(random scores) to validate plumbing. Real QWK numbers require real data.

---

## Files

- `dataset.json` — held-out submissions (fill this with real data)
- `baselines/` — baseline EvalReport JSONs saved before each architecture change
- `../reports/` — EvalReport JSONs for each architecture variant
