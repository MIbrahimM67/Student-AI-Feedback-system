"""
GradeWise v3 — Pydantic models.

The FeedbackReport schema is the contract between the grading pipeline and
the rest of the app. It is Pydantic-validated at Step 9 of the pipeline —
anything that doesn't conform is either repaired or marked failed.
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


# ---- Feedback report (strict pipeline output) --------------------------------

class RubricScore(BaseModel):
    criterion: str
    score: float
    maxScore: float
    confidence: float = Field(ge=0.0, le=1.0)
    justification: str
    citations: list[str] = Field(default_factory=list)
    # "needs_review" when confidence is low or Specialist/Judge disagree
    status: Literal["graded", "needs_review"] = "graded"


class FeedbackReport(BaseModel):
    overallScore: float
    maxScore: float
    status: Literal["pass", "fail", "needs_review"]
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    suggestions: list[str]
    rubricScores: list[RubricScore]
    finalComments: str


# ---- User profiles -----------------------------------------------------------

class UserProfile(BaseModel):
    uid: str
    org_id: str
    email: str
    display_name: str | None = None
    photo_url: str | None = None
    role: Literal["student", "instructor", "admin"]
    faculty_status: Literal["none", "pending", "approved", "rejected"] = "none"
    pro_status: Literal["inactive", "active", "revoked"] = "inactive"
    warning_count: int = 0
    blocked_until: str | None = None
    created_at: str
    updated_at: str


# ---- Subject / Reference / Assignment ----------------------------------------

class SubjectOut(BaseModel):
    id: str
    code: str | None
    title: str
    description: str | None
    level: str | None
    language: str
    kb_status: Literal["empty", "indexing", "ready"]
    reference_count: int
    assignment_count: int
    created_at: str


class ReferenceOut(BaseModel):
    id: str
    subject_id: str
    title: str
    type: str
    file_url: str
    index_status: Literal["pending", "chunking", "embedded", "failed"]
    chunk_count: int
    created_at: str


class AssignmentOut(BaseModel):
    id: str
    subject_id: str
    title: str
    plagiarism_enabled: bool
    version: int
    created_at: str


# ---- Batch -------------------------------------------------------------------

class BatchOut(BaseModel):
    id: str
    status: Literal["uploaded", "processing", "completed", "failed"]
    total_files: int
    processed_files: int
    approved_count: int
    needs_review_count: int
    export_excel_url: str | None
    export_zip_url: str | None
    created_at: str
