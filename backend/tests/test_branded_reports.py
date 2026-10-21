"""PDF feedback regression checks: GradeWise palette, glyphs, and sandbox I/O."""
import fitz

from app.services.report_service import report_service


def _all_text(pdf: bytes) -> str:
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        assert len(doc) >= 1
        return "\n".join(p.get_text() for p in doc)


def test_branded_pdf_renders_without_unsupported_black_dot_glyphs():
    sample = report_service.generate_student_pdf_bytes(
        report_data={
            "score": 8, "max_score": 10, "student_feedback":
            "Strengths: clear diagram • valid process — improves each step → conclusion.",
            "per_criterion": {"knowledge": 8},
            "criteria_notes": {"knowledge": {
                "evidence": "Answered 8 questions • cited 2 examples",
                "deduction_reason": "Missed key point — justified.",
            }},
            "strengths": ["Explained ● relevant concepts"],
            "weaknesses": ["Missing ✓ citation"],
        },
        student_name="Sample Student", assignment_title="Software Design",
        assignment_type="text", file_name="sample.pdf",
    )
    txt = _all_text(sample)
    assert "GRADEWISE" in txt
    assert "RUBRIC EVALUATION" in txt
    assert "Explained - relevant concepts" in txt
    assert "\u2022" not in txt
    assert "\ufffd" not in txt
    with fitz.open(stream=sample, filetype="pdf") as doc:
        shapes = doc[0].get_drawings()
        assert any(
            any(abs(x - c) < 0.03 for x, c in zip(shape.get("fill") or (), (0.082, 0.082, 0.082)))
            for shape in shapes
        ), "GradeWise charcoal header not present"


def test_legacy_code_pdf_includes_real_input_stdout_and_stderr():
    legacy = (
        "=== Test Case: Example ===\nStatus: EXECUTED (exit code 0)\n"
        "Input:\n4 5\nOutput:\n9\nStderr:\n"
    )
    pdf = report_service.generate_student_pdf_bytes(
        {"score": 10, "max_score": 10, "sandbox_logs": legacy},
        "Coder", assignment_type="coding", file_name="solution.py",
    )
    txt = _all_text(pdf)
    assert "SANDBOX EXECUTION LOGS" in txt
    assert "Example" in txt
    assert "4 5" in txt
    assert "9" in txt
    assert "Stderr" in txt


def test_structured_code_pdf_shows_each_execution_test_and_telemetry():
    pdf = report_service.generate_student_pdf_bytes(
        {"score": 3, "max_score": 5, "sandbox_logs": [
            {
                "name": "sample", "input": "12\n", "stdout": "24\n",
                "stderr": "", "exitCode": 0, "durationMs": 85,
                "status": "executed",
            },
            {
                "name": "edge", "input": "FAIL_INPUT", "stdout": "",
                "stderr": "RuntimeError: crash", "exitCode": 1,
                "durationMs": 104, "status": "execution_failed",
            },
        ]},
        "Coder", assignment_type="coding",
    )
    txt = _all_text(pdf)
    for token in ("SANDBOX EXECUTION LOGS", "TEST 1", "TEST 2",
                  "Input (stdin)", "Output (stdout)", "Errors (stderr)",
                  "12", "24", "FAIL_INPUT", "RuntimeError: crash", "85 ms", "104 ms"):
        assert token in txt, (token, txt[-1200:])


def test_long_console_logs_paginate_without_reportlab_layout_failure():
    pdf = report_service.generate_student_pdf_bytes(
        {"score": 4, "max_score": 10,
         "sandbox_logs": [{"name": "large", "input": "x\n" * 120,
                           "stdout": "output line\n" * 500,
                           "stderr": "warning\n" * 40,
                           "exitCode": 0, "durationMs": 123}]},
        "Coder", assignment_type="coding",
    )
    assert len(pdf) > 2000
    assert "SANDBOX EXECUTION LOGS" in _all_text(pdf)
