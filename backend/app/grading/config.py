"""
GradeWise — Routing Ladder tunables.

All values are defaults; override via environment variables.
"""

# ---- Ingestion ---------------------------------------------------------------

# DECISION: 150 DPI balances readability of in-image text (code screenshots,
# dense tables) with image size. Raise to 200 if fine text is missed.
RENDER_DPI: int = 150

# ---- Router ------------------------------------------------------------------

# Token cost estimate per page image sent to the model.
# DECISION: 800 tokens/page is a conservative estimate calibrated from Gemini's
# image token pricing (~258 tokens for a 512x512 tile; a rendered page at 150 DPI
# is roughly 1240x1755px ≈ 3 tiles horizontally × 4 vertically ≈ 800 tokens).
TOKENS_PER_PAGE_IMAGE: int = 800

# Maximum tokens to load into context before falling back to Tier 1 or 2.
# DECISION: 200,000 tokens is conservative (well below Gemini 2.5 Flash's 1M
# context limit) to leave room for the submission, rubric, system prompt, and
# feedback generation output. Raise if reference materials are consistently large.
CONTEXT_BUDGET_TOKENS: int = 200_000

# ---- Grading model -----------------------------------------------------------

# DECISION: Gemini 2.5 Flash — multimodal, long-context, fast, cost-effective.
# Matches the model already configured in the existing grading pipeline.
GEMINI_MODEL: str = "gemini-2.5-flash"

# ---- Tier 2 (Vector fallback) ------------------------------------------------

TIER2_TOP_K: int = 6  # chunks returned after reranking
TIER2_CANDIDATE_LIMIT: int = 20  # candidates before reranking

# ---- Reference-Assignment linking --------------------------------------------

# DECISION: Use the full subject reference set for all assignments in a subject.
# The data model links references to subjects, not directly to assignments.
# Future work: add an assignment_reference_materials join table for fine-grained
# scoping (tracked as open question in implementation plan).
USE_SUBJECT_WIDE_REFERENCES: bool = True
