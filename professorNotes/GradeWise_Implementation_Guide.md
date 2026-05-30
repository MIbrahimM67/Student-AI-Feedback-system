# GradeWise — Implementation Guide (Agent Spec)

> **For the coding agent:** This is an executable specification, not background reading. Build the modules
> in the order given. Each task has explicit deliverables and acceptance criteria. Do not skip Task 0 (the
> eval harness) — later tasks are validated against it. Where a decision is left open, pick the simplest
> option that satisfies the acceptance criteria and leave a `# DECISION:` comment explaining the choice.

---

## 0. Context & Goal

GradeWise is an AI grading system. It compares a **student submission** against **reference material**
(rubric, model answer, textbook/slide sections) for a known assignment, and produces a **score + feedback**.

We are replacing a one-size-fits-all RAG pipeline with a **routing ladder** that picks the cheapest tier
that can grade correctly:

- **Tier 0 — Context stuffing:** reference fits in the model's context window → load it whole (text + page
  images). Default path. No retrieval.
- **Tier 1 — Tree navigation:** reference too large but structured → navigate a hierarchical index to the
  right section, load that section whole.
- **Tier 2 — Vector fallback:** large + unstructured → rubric-anchored, multimodal-aware vector retrieval
  (the existing pipeline, upgraded).

Two cross-cutting rules apply to every tier:

1. **Render, don't OCR.** Documents reach the model as **page images** (so embedded screenshots/diagrams are
   visible), not as OCR'd text. OCR is a supplement only for literal code/terminal grading.
2. **Rubric-anchored, not submission-anchored.** Where retrieval happens, it is driven by rubric criteria,
   not by similarity to the student's text.

### Assumed stack (match existing system)

- Python 3.11+
- Grading LLM: **Gemini 2.5 Flash** via `google-genai` SDK (multimodal input)
- PDF rendering/extraction: **PyMuPDF (`fitz`)**
- DOCX→PDF: **LibreOffice headless** (`soffice`)
- DB: **PostgreSQL** (+ `pgvector` for Tier 2 only)
- Embeddings (Tier 2 only): **BGE-M3**; reranker: **BGE Reranker (cross-encoder)**
- OCR (supplement only): **Tesseract** via `pytesseract`

If any dependency is absent, add it to `requirements.txt` / `pyproject.toml` and note it.

### Target module layout

```
gradewise/
  ingest/
    __init__.py
    ingest.py          # render-don't-OCR pipeline → DocumentPayload
    docx_to_pdf.py     # LibreOffice headless wrapper
    ocr_supplement.py  # OCR for code/terminal regions only
  router/
    __init__.py
    router.py          # size + structure → Tier 0/1/2 decision
    structure.py       # heading/TOC detection, token estimation
  tiers/
    __init__.py
    tier0_context.py   # load whole reference, grade
    tier1_tree.py      # build/navigate hierarchical index
    tier2_vector.py    # rubric-anchored vector retrieval (existing, upgraded)
  grading/
    __init__.py
    grader.py          # single grading entrypoint used by all tiers
    rubric.py          # rubric decomposition into criteria
  eval/
    __init__.py
    harness.py         # QWK + secondary metrics, ablation runner
    metrics.py         # qwk(), per_criterion_accuracy(), etc.
  types.py             # shared dataclasses (see below)
  config.py            # tunables (DPI, context budget, thresholds)
```

### Shared types (`types.py`)

```python
from dataclasses import dataclass, field
from enum import Enum

class Tier(str, Enum):
    CONTEXT = "tier0_context"
    TREE = "tier1_tree"
    VECTOR = "tier2_vector"

@dataclass
class PageImage:
    page_number: int
    image_bytes: bytes          # PNG, rendered at config.RENDER_DPI
    mime_type: str = "image/png"
    extracted_text: str | None = None       # optional, for text-dense pages
    code_ocr_text: str | None = None         # supplement for literal code grading

@dataclass
class DocumentPayload:
    source_path: str
    pages: list[PageImage]
    est_tokens: int
    has_structure: bool         # headings/TOC detected
    text_only: bool             # plain text / md, no rendering needed
    plain_text: str | None = None

@dataclass
class Criterion:
    id: str
    description: str
    max_points: float
    reference_hint: str | None = None   # filled at Tier 1/2 retrieval time

@dataclass
class GradingResult:
    score: float
    max_score: float
    per_criterion: dict[str, float]      # criterion_id -> awarded points
    feedback: str
    tier_used: Tier
    reference_sections_used: list[str]   # for explainability/logging
```

---

## Task 0 — Eval Harness FIRST (`eval/`)

**Build this before any tier.** Nothing ships without a measured QWK delta against baseline.

**Deliverables**

- `metrics.py`:
  - `qwk(y_true: list[int], y_pred: list[int], n_classes: int) -> float` — Quadratic Weighted Kappa.
  - `cohen_kappa(...)` for pass/fail rubrics.
  - `per_criterion_accuracy(results, gold) -> dict[str, float]`.
  - `feedback_faithfulness(results, references) -> float` — % of feedback claims traceable to a reference
    section (LLM-as-judge is acceptable here; document the prompt).
- `harness.py`:
  - `run_eval(grader_fn, dataset) -> EvalReport` where `dataset` is a held-out set of
    `(submission, assignment_ref, human_scores)` rows.
  - `EvalReport` includes: QWK, per-criterion accuracy, tier distribution, p50/p95 latency per tier,
    cost per grading event.
  - `compare(reports: dict[str, EvalReport])` — prints an ablation table across named variants.

**Acceptance criteria**

- `qwk()` returns 1.0 for identical inputs and matches a reference implementation (e.g. sklearn's
  `cohen_kappa_score(..., weights="quadratic")`) on a unit test.
- `run_eval` works against a stub grader that returns random scores (proves plumbing before any tier exists).
- Provide a `dataset/README.md` describing the held-out-set schema and noting that **2+ human graders per
  item** are needed to compute the human-vs-human QWK ceiling.

**Do not proceed until baseline QWK of the *current* system is recorded in `eval/baselines/`.**

---

## Task 1 — Ingestion: Render, Don't OCR (`ingest/`)

**Deliverables**

- `ingest.py`: `ingest(path: str) -> DocumentPayload` implementing this routing:
  - DOCX → convert to PDF (`docx_to_pdf.py`) → treat as PDF.
  - PDF → render each page to PNG via PyMuPDF `page.get_pixmap(dpi=config.RENDER_DPI)`; populate
    `PageImage.image_bytes`. Optionally fill `extracted_text` for text-dense pages.
  - Standalone image (PNG/JPG) → single `PageImage`, no OCR.
  - Plain text / Markdown → `text_only=True`, `plain_text` set, `pages=[]`.
- `docx_to_pdf.py`: `convert(path: str) -> str` — wraps `soffice --headless --convert-to pdf`, returns the
  output PDF path. Handle missing `soffice` with a clear error.
- `ocr_supplement.py`: `ocr_code_region(image_bytes: bytes) -> str` — Tesseract OCR used **only** when a page
  is flagged as containing code/terminal content to be graded literally. Populates `PageImage.code_ocr_text`.
  - Detection heuristic for "code/terminal screenshot": monospace-dominant region, dark background, or
    assignment metadata flagging a coding task. Keep the heuristic in one function so it can be tuned.

**Acceptance criteria**

- A PDF containing an embedded screenshot produces `PageImage` objects whose `image_bytes` visibly contain
  the screenshot (add a test that renders a known fixture PDF and asserts non-trivial image size).
- A DOCX with a pasted screenshot survives the DOCX→PDF→render path with the screenshot intact.
- `RENDER_DPI` defaults to **150** and is read from `config.py`.
- OCR is **never** invoked on the default path — only via `ocr_code_region` when the code-screenshot flag is
  set. Add a test asserting OCR is not called for a normal text+image PDF.

---

## Task 2 — Router (`router/`)

**Deliverables**

- `structure.py`:
  - `estimate_tokens(payload: DocumentPayload) -> int` — text tokens + (page_count × `config.TOKENS_PER_PAGE_IMAGE`).
  - `detect_structure(path: str) -> bool` — true if the PDF/DOCX has a TOC or heading hierarchy (PyMuPDF
    `doc.get_toc()`, or DOCX heading styles).
- `router.py`: `route(payload: DocumentPayload) -> Tier`:
  - `est_tokens <= config.CONTEXT_BUDGET_TOKENS` → `Tier.CONTEXT`
  - else if `payload.has_structure` → `Tier.TREE`
  - else → `Tier.VECTOR`

**Acceptance criteria**

- `CONTEXT_BUDGET_TOKENS` is set **below** the model max (reserve room for submission + rubric + feedback);
  default to a conservative value in `config.py` with a `# DECISION:` comment.
- Unit tests cover all three branches with synthetic payloads.

---

## Task 3 — Grading Core + Rubric Decomposition (`grading/`)

**Deliverables**

- `rubric.py`: `decompose(rubric_text: str) -> list[Criterion]` — runs **once at assignment setup time**
  (cache the result keyed by assignment ID; do not re-run per submission).
- `grader.py`: `grade(submission: DocumentPayload, reference_pages: list[PageImage], criteria: list[Criterion],
  tier: Tier) -> GradingResult`:
  - Builds a multimodal Gemini request: submission page images + reference page images + criteria.
  - Grades **per criterion**, returns `per_criterion` map and aggregate `score`.
  - Records `reference_sections_used` for explainability.

**Acceptance criteria**

- Grading request includes images as inline image parts (not OCR'd text). Add a test asserting image parts
  are present in the request payload.
- `per_criterion` keys exactly match the input criterion IDs.

---

## Task 4 — Tier 0: Context Stuffing (`tiers/tier0_context.py`)

**Deliverables**

- `grade_tier0(submission, reference_payload, criteria) -> GradingResult` — loads the **entire** reference
  (all page images + text) into the grading call. No chunking, no retrieval.

**Acceptance criteria**

- Measure QWK and p50/p95 latency vs. baseline on the held-out set. **Expected: the largest single QWK gain
  here.** Record the report in `eval/reports/`.

---

## Task 5 — Tier 1: Tree Navigation (`tiers/tier1_tree.py`)

**Deliverables**

- `build_index(path) -> TreeIndex` — hierarchical index from headings/TOC (`section_title, parent_id,
  page_range`). Built once at setup time.
- `navigate(index, criterion) -> page_range` — LLM reads the top-level index and drills to the relevant
  section for a given **criterion** (not the student's text).
- `grade_tier1(...)` — navigate per criterion, load that section's page images whole, hand to `grader.grade`.

**Acceptance criteria**

- For a large structured fixture, navigation returns the correct section for a known criterion.
- Loaded section is passed as **page images**, preserving any embedded figures.

---

## Task 6 — Tier 2: Rubric-Anchored Vector Fallback (`tiers/tier2_vector.py`)

**Deliverables**

- Upgrade the existing pipeline: retrieve **per rubric criterion** (embed the criterion's requirement, not
  the student paragraph) → BGE-M3 search → BGE reranker → top-K.
- Retrieved sections are passed to `grader.grade` as page images where available (multimodal-aware).

**Acceptance criteria**

- A regression test on the "recursion retrieves trees" class of failure shows the rubric-anchored retrieval
  pulls the correct reference where submission-anchored retrieval did not.
- pgvector/embedding/reranker code is reachable **only** via Tier 2.

---

## Task 7 — Wire the Ladder + Logging

**Deliverables**

- A single entrypoint `grade_submission(submission_path, assignment_id) -> GradingResult` that:
  ingests → routes → dispatches to the chosen tier → returns result.
- Structured log per event: `tier_used`, `reference_sections_used`, criteria coverage, latency, est. cost.
  These feed the eval harness's tier-distribution and cost metrics.

**Acceptance criteria**

- End-to-end test grades one fixture per tier and asserts the expected tier was selected.
- Final ablation in `eval/reports/`: baseline vs. Tier 0 vs. +multimodal vs. +rubric-anchored, reported as a
  QWK table. **Ship a change only if QWK improves, or holds while improving latency/cost.**

---

## Config defaults (`config.py`)

```python
RENDER_DPI = 150                  # raise for dense code screenshots
TOKENS_PER_PAGE_IMAGE = 800       # estimate; calibrate against real renders
CONTEXT_BUDGET_TOKENS = 200_000   # DECISION: conservative, well below model max
GEMINI_MODEL = "gemini-2.5-flash"
TIER2_TOP_K = 6                   # after reranking
```

---

## Guardrails for the agent

- **Do not** add an OCR step to the default ingestion path. OCR is supplement-only (code/terminal regions).
- **Do not** make Tier 2 (vector/embeddings) the default. It is the unstructured-only fallback.
- **Do not** retrieve based on similarity to the student's submission text. Retrieval is rubric-criterion
  driven.
- **Do not** report "it works" without a QWK number from the harness against the held-out set.
- Treat latency and cost as **constraints**, not objectives. A faster pipeline that grades worse is rejected.
- Leave a `# DECISION:` comment anywhere you resolve an ambiguity, so it can be reviewed.
