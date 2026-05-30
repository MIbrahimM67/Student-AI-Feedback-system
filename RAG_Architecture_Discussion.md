# RAG Architecture Discussion — GradeWise AI Feedback System

Prepared for academic review. This document compares our current Retrieval-Augmented Generation pipeline
with an alternative approach (Vectorless RAG) proposed for evaluation.

---

## 1. Current System: Traditional Hybrid RAG

### How It Works

```
Reference Document (PDF/DOCX/Image)
        ↓
   [Step 1] OCR + Text Extraction
   (PyMuPDF for PDFs, Tesseract for images/handwritten)
        ↓
   [Step 2] Chunking
   (512-token windows, 64-token overlap)
        ↓
   [Step 3] Concept Extraction per Chunk
   (Utility LLM → extracts key concepts, stored in a knowledge graph)
        ↓
   [Step 4] Embedding
   (BGE-M3 multilingual dense embedding model)
        ↓
   [Step 5] Stored in pgvector (PostgreSQL extension)
        ↓ ──── [ This happens at query/grading time ] ────
        ↓
   [Step 6] Query Embedding
   (Student submission text is embedded with same BGE-M3 model)
        ↓
   [Step 7] Cosine Similarity Search
   (pgvector retrieves top-20 most similar chunks from the subject's knowledge base)
        ↓
   [Step 8] Cross-Encoder Reranking
   (BGE Reranker re-scores candidates, keeps top-6)
        ↓
   [Step 9] Top-K Chunks → LLM Context Window
   (Grading LLM uses retrieved chunks as rubric context)
        ↓
   AI Feedback + Score
```

### Technology Stack
| Component | Technology |
|---|---|
| OCR / Text Extraction | PyMuPDF, python-docx, Tesseract |
| Chunking | Custom token-aware splitter (512 tokens, 64 overlap) |
| Embedding Model | BGE-M3 (multilingual, 1024-dim vectors) |
| Vector Database | pgvector (PostgreSQL extension) |
| Similarity Search | Cosine distance (`<=>` operator) |
| Reranker | BGE Reranker (cross-encoder) |
| Grading LLM | Gemini 2.0 Flash / Gemini 2.5 Flash |
| Knowledge Graph | Custom PostgreSQL relational tables (concepts, relationships) |

### Expected Performance

**Strengths:**
- ✅ Semantic search is content-agnostic — works on any text regardless of document structure
- ✅ BGE-M3 is multilingual — supports submissions in multiple languages
- ✅ Reranking significantly improves precision (cross-encoder is more accurate than cosine similarity alone)
- ✅ Already integrated with our PostgreSQL database — no separate vector DB infrastructure needed
- ✅ Handles unstructured documents well (scanned notes, mixed-content PDFs)

**Weaknesses / Limitations:**
- ❌ **Embedding latency**: Every new reference document must be embedded before it can be queried (takes seconds to minutes depending on document size)
- ❌ **Chunking loses structural context**: A 512-token chunk from the middle of a textbook chapter has no knowledge of the chapter title, section heading, or surrounding context
- ❌ **Images not directly searchable**: Images in reference materials (diagrams, figures, tables) must be OCR'd first. If OCR fails or the image is a diagram with no text, it is effectively invisible to the RAG pipeline
- ❌ **Top-K may miss the mark**: Cosine similarity finds semantically similar text, but "similar" is not always "relevant for grading". A student answer about recursion might retrieve chunks about trees because both share vocabulary
- ❌ **Storage overhead**: Embedding vectors (1024 floats × 4 bytes = ~4KB per chunk) accumulate quickly with many reference materials
- ❌ **Reranker adds ~200-400ms latency** at grading time

**Expected Accuracy for Our Use Case:**
- Good for text-heavy reference materials (lecture notes, textbooks, papers)
- Moderate for mixed content (depends on OCR quality for image regions)
- The reranker provides a meaningful accuracy boost over cosine-only retrieval

---

## 2. Proposed Alternative: Vectorless RAG

> Concept proposed by the development team for evaluation.

### Core Idea

Instead of converting documents into undifferentiated chunks and searching by vector similarity, Vectorless RAG builds a **structured hierarchical index** of the document first, and then uses **intelligent query routing** to navigate that index like a tree to find precise sections — no embeddings, no vector database.

```
Reference Document (PDF/DOCX)
        ↓
   [Step 1] Structured Index Construction
   (Parse document headings, sections, subsections → build a tree structure)
   Example: Chapter 3 → Section 3.2 → "Recursion" → paragraph list
        ↓
   [Step 2] Store Index in Database
   (Hierarchical table: section_title, parent_id, content, page_range)
        ↓ ──── [ This happens at query/grading time ] ────
        ↓
   [Step 3] Query Routing
   (LLM reads the index tree's top level and decides which branch to explore)
        ↓
   [Step 4] Hierarchical Navigation
   (LLM or rule-based system drills down through section → subsection → paragraph)
        ↓
   [Step 5] Precise Section Retrieval
   (Returns the exact section/paragraph — not a random chunk)
        ↓
   [Step 6] LLM uses retrieved section as grading context
        ↓
   AI Feedback + Score
```

### Expected Performance

**Strengths:**
- ✅ **No embedding cost or latency**: Indexing is purely structural — parse headings and sections, done
- ✅ **No vector database needed**: Standard relational database tables are sufficient
- ✅ **Context-preserving**: Retrieved content includes section title, parent chapter, surrounding structure — not a decontextualized chunk
- ✅ **Deterministic and explainable**: You can trace exactly which section was used for grading
- ✅ **Fast retrieval**: Tree navigation is O(depth) — typically 3-4 hops for a textbook, far faster than cosine search over thousands of vectors
- ✅ **Lower infrastructure cost**: No need for pgvector, embedding API calls, or reranker model

**Weaknesses / Limitations:**
- ❌ **Requires well-structured documents**: Works best with PDFs that have proper headings (H1, H2, H3) or DOCX with Heading styles. Scanned PDFs with no heading structure would have a flat, unusable index
- ❌ **Images still require OCR preprocessing**: The structural index only helps with text. Diagrams and figures remain a challenge unless paired with a vision model to generate text descriptions at index time
- ❌ **Query routing accuracy**: The LLM must correctly decide which branch of the index tree to navigate. If the query is ambiguous or the document structure is unusual, it may navigate to the wrong section
- ❌ **Does not handle unstructured reference materials**: A dump of lecture notes with no headings, or a handwritten PDF, would produce a very shallow/useless index
- ❌ **Cross-section queries are harder**: If the answer to a question spans multiple sections of a document, the hierarchical navigation may only retrieve one

---

## 3. Side-by-Side Comparison for Our Use Case

| Criterion | Current Hybrid RAG | Vectorless RAG |
|---|---|---|
| **Speed (indexing)** | Slow (embed every chunk) | Fast (parse structure only) |
| **Speed (retrieval)** | ~400-800ms (search + rerank) | ~50-150ms (tree navigation) |
| **Accuracy on structured textbooks** | Good | Excellent |
| **Accuracy on unstructured notes** | Good | Poor |
| **Accuracy on scanned/image-heavy PDFs** | Moderate (OCR dependent) | Poor (requires OCR + structure) |
| **Handles mixed content (text + images)** | Moderate | Poor without vision preprocessing |
| **Infrastructure cost** | Higher (vectors, reranker) | Lower |
| **Explainability** | Low (why this chunk?) | High (which section, why) |
| **Multilingual support** | ✅ BGE-M3 is multilingual | Depends on LLM router language |

---

## 4. Recommendation for Discussion

Given that GradeWise reference materials include:
- Textbooks and lecture notes (structured)
- Slides and model answers (semi-structured)
- Scanned documents and handwritten notes (unstructured)
- Images embedded in PDFs (visual content)

A **hybrid strategy** may be optimal:

> **Use Vectorless RAG for well-structured documents** (detected by presence of headings/TOC), and **fall back to the current vector-based pipeline for unstructured or image-heavy materials**.

This would give us the speed and precision of Vectorless RAG for the majority of academic textbooks and slides, while retaining robustness for edge cases.

**Open Question for Professor:** Is the primary evaluation criterion retrieval accuracy, retrieval speed, or system explainability for academic integrity purposes?

---

*Document prepared by GradeWise development team — May 2026.*
