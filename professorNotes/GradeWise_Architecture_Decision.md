# Architecture Decision: Scoped Grading over General RAG — GradeWise AI Feedback System

Prepared as a follow-up to the *RAG Architecture Discussion*. This document reframes the retrieval
problem around what GradeWise actually does (assignment-scoped grading), proposes a tiered **routing
ladder** instead of a single pipeline, and specifies the evaluation harness needed to decide anything
empirically rather than by taste.

---

## 1. The Reframe: This Is Not Open-Domain RAG

General-purpose RAG exists to answer an **arbitrary query** against a **large, open corpus**. That is the
problem both architectures in the prior document are engineered to solve — and it is a harder problem than
the one GradeWise has.

For any single grading event, the following are **known in advance**:

- The subject
- The assignment
- The rubric and/or model answer the submission is graded against
- The (small, bounded) set of reference material relevant to *this* assignment

The effective corpus for one grading event is therefore tiny and pre-scoped. Running a full open-domain
retrieval stack — chunk, embed, vector search, rerank — on every submission pays the tax of a problem we
do not have. **The biggest efficiency and accuracy win is recognizing that retrieval is frequently
unnecessary, and where it is necessary, it should be driven by the rubric rather than by surface
similarity of the student's text.**

> **Core principle:** Retrieval is a *fallback*, not the default. The default is to put the whole, known,
> structurally-intact reference in front of a multimodal model.

---

## 2. Proposed Architecture: The Routing Ladder

Instead of one pipeline, route each grading event to the cheapest tier that can serve it correctly.

```
Submission + Assignment ID
        ↓
   [Resolve scoped reference set for this assignment]
   (rubric, model answer, linked chapter/slides — known at setup time)
        ↓
   [Router] Measure reference size + structure
        ↓
 ┌──────────────────────────────────────────────────────────────┐
 │  TIER 0 — Context Stuffing  (reference fits in context)        │
 │  → Load entire reference (TEXT + PAGE IMAGES) into the model   │
 │  → No chunking, no embedding, no vector search, no reranker    │
 │  → Fastest, highest accuracy, fully traceable                  │
 │  → Expected to serve the MAJORITY of grading events            │
 └──────────────────────────────────────────────────────────────┘
        ↓ (reference too large for context)
 ┌──────────────────────────────────────────────────────────────┐
 │  TIER 1 — Structured Tree Navigation  (large + has headings)   │
 │  → Use hierarchical index as a MAP, not a retrieval system     │
 │  → LLM routes to the right section, then load THAT section     │
 │    whole (text + images) — back into a Tier-0-style context    │
 └──────────────────────────────────────────────────────────────┘
        ↓ (large AND unstructured: no headings, dumped notes, scans)
 ┌──────────────────────────────────────────────────────────────┐
 │  TIER 2 — Vector Fallback  (existing pipeline, upgraded)       │
 │  → Rubric-anchored retrieval (NOT student-text similarity)     │
 │  → Multimodal-aware (page images, not OCR'd text)              │
 │  → Keep BGE-M3 + reranker only for this edge case              │
 └──────────────────────────────────────────────────────────────┘
        ↓
   Grading LLM (Gemini 2.5 Flash) → AI Feedback + Score
        ↓
   [Log: tier used, reference section(s) used, criteria coverage]
   → feeds the eval harness (Section 5)
```

The three big changes versus the current system are baked into this ladder and explained below.

---

## 3. The Three Changes That Matter

### Change 1 — Tier 0: Stop retrieving when you don't need to

Gemini 2.5 Flash carries a context window on the order of one million tokens. A single assignment's
reference material — rubric, model answer, the relevant chapter or deck — is very often well under 50k
tokens. **If it fits, load all of it.** No chunking, no embedding, no similarity search, no reranker, no
vector DB round-trip.

This is not a compromise — it is strictly better on every axis that matters here:

- ✅ **Accuracy ceiling**: the model sees the entire reference with structure intact (no decontextualized
  chunks, no "this 512-token window doesn't know what chapter it's in").
- ✅ **Speed**: one model call, no retrieval round-trips.
- ✅ **Explainability**: the grading context *is* the reference. Nothing to trace through.
- ✅ **Eliminates** the indexing latency, storage overhead, and reranker latency listed as weaknesses of
  the current system.

Honest expectation: this tier serves the bulk of real grading events. Retrieval becomes the exception.

### Change 2 — Go multimodal-native; delete the OCR bottleneck

Both prior architectures list *"images require OCR"* as a weakness — while the system already runs a
**natively multimodal** model (Gemini). OCR is a lossy step that downgrades a multimodal model into a
text-only one.

**Feed page images directly to the model.** Diagrams, figures, hand-drawn graphs, chemistry mechanisms,
messy handwritten proofs — all become first-class gradeable content instead of "invisible to the
pipeline." This single change fixes the worst row in both prior weakness tables (`image-heavy / scanned`)
and removes Tesseract as a point of failure.

OCR is retained only as an optional *extraction* step where plain text is genuinely needed (e.g. building
the Tier-1 tree index), never as the path through which the model "sees" visual content.

### Change 3 — When you retrieve, anchor to the rubric, not the student's text

The current pipeline embeds the **student submission** and retrieves semantically similar chunks. This is
the root cause of the documented failure: *"a student answer about recursion retrieves chunks about trees
because both share vocabulary."* Surface similarity ≠ grading relevance.

Flip the direction:

1. At **assignment setup time** (once, not per submission), decompose the rubric into discrete criteria.
2. Retrieve reference material **per criterion** — "what does a correct answer to criterion 3 require?" —
   not per student paragraph.
3. Grade each criterion against its own anchored reference.

This is what human graders actually do, it is deterministic and explainable, and it eliminates the
vocabulary-collision failure mode at its source. It also gives you free coverage tracking: you know which
criteria were and weren't addressed.

### Document Ingestion: Render, Don't OCR

Change 2 only works if the ingestion path is correct. There are two ways a document reaches the model, and
only one preserves embedded images (screenshots, diagrams, figures). Assignment submissions routinely
contain screenshots — terminal output, code editors, UI captures, pasted graphs — so this path is not an
edge case; it is the common case.

**The failure mode to avoid:** extract the text stream and run embedded images through OCR. A screenshot of
a terminal or a diagram gets dropped or badly scraped; the visual content the student is referring to is
lost. This is the "images are invisible to the pipeline" weakness from the original document.

**The correct path:** rasterize each page to an image and send the page image to the model, so it sees the
page exactly as a human would — prose and embedded screenshot together, on the same page, in context.

Per file type:

| File type | Ingestion recipe |
|---|---|
| **PDF (any)** | Render each page to an image with PyMuPDF `page.get_pixmap()` at ~150 DPI. Send page images to Gemini. Optionally also send extracted text for text-dense pages. Alternatively, send PDF bytes directly to Gemini and let it rasterize internally. |
| **DOCX (incl. embedded screenshots)** | Convert to PDF first via headless LibreOffice (`soffice --headless --convert-to pdf`), then treat as PDF. More robust than parsing DOCX XML and reassembling layout. |
| **Standalone image (PNG/JPG)** | Send directly as an image. No OCR step. |
| **Plain text / Markdown** | Send as text. No rendering needed. |

**Resolution rule:** render at **≥150 DPI** for any page where fine text inside an image matters (code
screenshots, dense tables). A low-DPI render blurs small in-image text past the point the model can read it.
Make DPI a tunable.

**The code/terminal-screenshot exception — the one place OCR still earns its keep:** when an image contains
*code or terminal text that will be graded literally*, send the page image **and** OCR just that image
region. The image preserves layout, syntax highlighting, and visible errors; the OCR recovers the exact
characters, which matters because grading code often needs the literal text, not "it looks roughly right."
This is OCR as a *supplement*, not a replacement.

```
Document
   ↓
Is it DOCX? ──yes──→ soffice --convert-to pdf ──┐
   │ no                                          │
   ↓                                             ↓
Is it an image? ──yes──→ send image directly    PDF
   │ no                                          │
   ↓                                             ↓
Is it text/md? ──yes──→ send as text     render pages @≥150 DPI (PyMuPDF)
                                                 ↓
                                    For pages with code/terminal images:
                                    also OCR that region (literal-text grading)
                                                 ↓
                                    Send page images (+ optional text) to Gemini
```

---

## 4. Decision Table: Which Tier, When

| Reference profile | Fits in context? | Has heading structure? | Tier | Mechanism |
|---|---|---|---|---|
| Single rubric + model answer | Yes | n/a | **0** | Load whole, multimodal |
| Chapter / slide deck / paper | Yes | n/a | **0** | Load whole, multimodal |
| Full course material, structured | No | Yes | **1** | Tree-navigate → load section whole |
| Large reference, structured PDF/DOCX | No | Yes | **1** | Tree-navigate → load section whole |
| Dumped lecture notes, no headings | No | No | **2** | Rubric-anchored vector retrieval |
| Scanned / handwritten, large | No | No | **2** | Multimodal vector fallback |

The router decision is cheap: token count of the resolved reference set, plus a heading/TOC presence check
(already available from PyMuPDF / python-docx style metadata).

### How this maps onto the two prior proposals

- **Vectorless RAG** is *not* a competing system — it becomes **Tier 1's navigation aid**. Its job is to be
  the map the model uses to find the right section inside a too-large document, after which that section is
  loaded whole. This keeps the speed and explainability the team liked, without betting the product on
  documents always being well-structured.
- **The current vector pipeline** is *not* deprecated — it becomes **Tier 2**, the robustness fallback for
  genuinely unstructured / no-heading material, upgraded to be rubric-anchored and multimodal-aware.
- **Long-context (Tier 0)** is the new default that sits above both.

---

## 5. Evaluation Harness (Build This First)

> "Best results" is not a metric. Until agreement with human graders is measured, every architecture
> argument is taste, and there is no way to know whether a clever change grades *better* or merely *feels*
> more sophisticated.

### Primary metric

**Quadratic Weighted Kappa (QWK)** between AI scores and human-grader scores on a held-out set. QWK is the
standard for ordinal scoring agreement (it penalizes large disagreements more than small ones) and is the
established metric in automated-essay/short-answer scoring work. Cohen's Kappa is acceptable for
pass/fail-style rubrics.

### Secondary metrics

| Metric | What it tells you | Target direction |
|---|---|---|
| QWK vs. human graders | Scoring agreement (the headline number) | Maximize |
| Per-criterion accuracy | Where grading breaks down by rubric item | Maximize, find weak criteria |
| Feedback faithfulness | % of feedback claims traceable to reference | Maximize |
| Tier distribution | % served by Tier 0 / 1 / 2 | Diagnostic |
| p50 / p95 latency per tier | Speed under real load | Constraint, not goal |
| Cost per grading event | Infra/API cost | Constraint, not goal |

### Method

1. Assemble a **held-out set** of submissions with trusted human scores (ideally 2+ graders per item so you
   also have a human-vs-human QWK ceiling — you cannot expect the AI to beat inter-rater agreement).
2. Run the **current system** against it → baseline QWK. *Do this before changing anything.*
3. Run each proposed tier/change as an ablation against the same set.
4. Ship a change only if it improves QWK (or holds QWK while improving a constraint like latency/cost).

Treat speed and cost as **constraints to satisfy**, not objectives to maximize. A faster system that grades
worse is a worse product.

---

## 6. Suggested Migration Path

1. **Stand up the eval harness + baseline QWK.** Nothing else is decidable without this.
2. **Add Tier 0 (context stuffing) behind the router.** Measure QWK and latency vs. baseline. Expect the
   largest single jump in both accuracy and speed here.
3. **Switch the grading path to multimodal-native** (drop OCR from the "model sees content" path). Re-measure
   — expect the biggest gains on image-heavy / scanned assignments specifically.
4. **Re-anchor Tier 2 retrieval to the rubric.** Re-measure the vocabulary-collision cases.
5. **Repurpose the vectorless tree as Tier 1 navigation** for large structured documents.
6. Keep BGE-M3 + reranker **only** as Tier 2. Decommission embedding/reranking for everything Tier 0/1 now
   covers — that's where the infra savings land.

---

## 7. Open Questions

1. **Reference resolution at setup time.** Tier 0/1 depend on knowing the scoped reference set per
   assignment. How tightly is reference material currently linked to assignments in the data model? If it
   isn't, that linkage is the prerequisite work.
2. **Context budget policy.** What token threshold flips Tier 0 → Tier 1? (Recommend setting it below the
   model max to leave room for the submission, rubric, and feedback generation.)
3. **Human-grader ceiling.** Do we have multi-grader data to establish the inter-rater QWK we're aiming at?
4. **Failure escalation.** When the AI's confidence or criterion-coverage is low, do we route to human
   review? Grading has academic-integrity stakes that pure retrieval QA does not.

---

*Follow-up architecture decision — GradeWise, May 2026.*
