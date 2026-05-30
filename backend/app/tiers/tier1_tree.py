"""
GradeWise — Tier 1: Tree Navigation.

For large documents with hierarchical structure (TOC/Headings). 
Navigates the index to find the relevant section per criterion, and loads
that section as page images.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

from app.services.llm_provider import build_llm_from_env, ChatMessage
from app.grading.types import Tier, DocumentPayload, Criterion, GradingResult, PageImage
from app.grading.grader import grade
from app.grading import config

logger = logging.getLogger(__name__)

@dataclass
class TreeIndexItem:
    level: int
    title: str
    page_start: int
    page_end: int | None = None


def build_index(path: str) -> list[TreeIndexItem]:
    """
    Build a hierarchical index from a PDF's Table of Contents.
    """
    suffix = Path(path).suffix.lower()
    if suffix != ".pdf":
        return []

    try:
        doc = fitz.open(path)
        toc = doc.get_toc()  # List of [level, title, page]
        
        index: list[TreeIndexItem] = []
        for i, entry in enumerate(toc):
            level, title, page = entry
            # PyMuPDF pages are 1-indexed here
            item = TreeIndexItem(
                level=level,
                title=title.strip(),
                page_start=page,
            )
            index.append(item)
            
        # Determine page_end for each item by looking at the next item
        # at the SAME OR HIGHER level in the hierarchy
        for i, item in enumerate(index):
            for next_item in index[i+1:]:
                if next_item.level <= item.level:
                    # Subtract 1 because the section ends before the next one starts
                    item.page_end = max(item.page_start, next_item.page_start - 1)
                    break
            if item.page_end is None:
                item.page_end = len(doc)
                
        doc.close()
        return index
    except Exception as e:
        logger.error("Failed to build TreeIndex for %s: %s", path, e)
        return []


async def navigate(index: list[TreeIndexItem], criterion: Criterion) -> list[int]:
    """
    Ask the LLM to select the most relevant section(s) from the index for this criterion.
    Returns a list of page numbers to load.
    """
    if not index:
        return []

    llm = build_llm_from_env()
    
    # Format the TOC for the LLM
    toc_text = ""
    for idx, item in enumerate(index):
        indent = "  " * (item.level - 1)
        toc_text += f"[{idx}] {indent}{item.title} (Pages {item.page_start}-{item.page_end})\n"
        
    system_prompt = (
        "You are an intelligent document router. Your job is to read the Table of Contents "
        "of a reference document and select the single most relevant section index that covers "
        "the given grading criterion.\n\n"
        "Output ONLY valid JSON matching this schema:\n"
        "{\n"
        '  "selected_index": integer\n'
        "}\n"
    )
    
    user_prompt = (
        f"=== GRADING CRITERION ===\n"
        f"ID: {criterion.id}\n"
        f"Description: {criterion.description}\n\n"
        f"=== TABLE OF CONTENTS ===\n"
        f"{toc_text}\n"
    )
    
    try:
        resp = await llm.chat(
            messages=[
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt)
            ],
            model=config.GEMINI_MODEL,  # Fast model is fine for routing
            response_format="json_object",
            temperature=0.0
        )
        
        raw = resp.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0].strip()
        data = json.loads(raw)
        selected_idx = data.get("selected_index")
        
        if selected_idx is not None and 0 <= selected_idx < len(index):
            selected = index[selected_idx]
            # Convert page range to a list of page numbers (1-indexed)
            if selected.page_end:
                return list(range(selected.page_start, selected.page_end + 1))
            else:
                return [selected.page_start]
        return []
        
    except Exception as e:
        logger.error("Tree navigation failed: %s", e)
        return []


async def grade_tier1(
    submission: DocumentPayload,
    reference_payload: DocumentPayload,
    criteria: list[Criterion]
) -> GradingResult:
    """
    Grade by navigating the reference document's tree index to load specific sections.
    """
    logger.info("Executing Tier 1 grading for %s", submission.source_path)
    
    index = build_index(reference_payload.source_path)
    if not index:
        logger.warning("Tier 1 fallback: No index found, degrading to Tier 0 behavior.")
        return await grade(
            submission=submission,
            reference_pages=reference_payload.pages,
            criteria=criteria,
            tier=Tier.TREE,
            reference_sections_used=["Fallback to Full Document"]
        )

    # 1. Navigate to find relevant pages per criterion
    pages_to_load: set[int] = set()
    sections_used = []
    
    for c in criteria:
        relevant_pages = await navigate(index, c)
        if relevant_pages:
            pages_to_load.update(relevant_pages)
            c.reference_hint = f"Refer to pages {min(relevant_pages)}-{max(relevant_pages)}."
            sections_used.append(f"{c.id}: pages {min(relevant_pages)}-{max(relevant_pages)}")
        else:
            c.reference_hint = "No specific section found."
            sections_used.append(f"{c.id}: none")

    # 2. Extract only the selected page images
    selected_page_images: list[PageImage] = []
    if pages_to_load:
        for page in reference_payload.pages:
            if page.page_number in pages_to_load:
                selected_page_images.append(page)
    else:
        # If navigation failed completely, fallback to first 5 pages or something?
        # DECISION: Safest fallback is the full document if navigation yields nothing.
        selected_page_images = reference_payload.pages
        sections_used = ["Fallback to Full Document"]

    return await grade(
        submission=submission,
        reference_pages=selected_page_images,
        criteria=criteria,
        tier=Tier.TREE,
        reference_sections_used=sections_used
    )
