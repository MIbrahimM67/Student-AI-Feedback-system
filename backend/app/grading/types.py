"""
GradeWise — Shared type definitions for the Routing Ladder architecture.

These types are used across ingest/, router/, tiers/, grading/, and eval/.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Tier(str, Enum):
    CONTEXT = "tier0_context"
    TREE = "tier1_tree"
    VECTOR = "tier2_vector"
    MAP_REDUCE = "tier3_map_reduce"


@dataclass
class PageImage:
    page_number: int
    image_bytes: bytes          # PNG rendered at config.RENDER_DPI
    mime_type: str = "image/png"
    extracted_text: Optional[str] = None   # optional, for text-dense pages
    code_ocr_text: Optional[str] = None    # supplement for literal code grading


@dataclass
class DocumentPayload:
    source_path: str
    pages: list[PageImage]
    est_tokens: int
    has_structure: bool         # headings/TOC detected
    text_only: bool             # plain text/md, no rendering needed
    plain_text: Optional[str] = None


@dataclass
class Criterion:
    id: str
    description: str
    max_points: float
    reference_hint: Optional[str] = None  # filled at Tier 1/2 retrieval time


@dataclass
class GradingResult:
    score: float
    max_score: float
    per_criterion: dict[str, float]       # criterion_id -> awarded points
    feedback: str
    tier_used: Tier
    reference_sections_used: list[str]    # for explainability/logging
    latency_ms: int = 0
    est_cost_usd: float = 0.0
