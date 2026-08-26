import os
import io
import html
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

try:
    from app.config import settings
except ImportError:
    try:
        from backend.app.config import settings
    except ImportError:
        settings = None

logger = logging.getLogger("report_service")


def _clean_text(val: Any) -> str:
    """Safely escape and clean strings for ReportLab Paragraphs."""
    if val is None:
        return ""
    text = str(val).strip()
    # Escape XML entities for ReportLab XML parser
    return html.escape(text)


class ReportService:
    def generate_student_pdf_bytes(
        self,
        report_data: Dict[str, Any],
        student_name: str,
        assignment_type: str = "text",
        file_name: str = "",
        assignment_title: str = "",
    ) -> bytes:
        """
        Generates a beautifully typeset PDF feedback report in memory and returns bytes.
        """
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )
        story = []

        styles = getSampleStyleSheet()

        # Theme Colors
        navy = colors.HexColor("#0F172A")
        indigo = colors.HexColor("#3B82F6")
        indigo_dark = colors.HexColor("#1E3A8A")
        emerald = colors.HexColor("#059669")
        rose = colors.HexColor("#DC2626")
        amber = colors.HexColor("#D97706")
        light_slate = colors.HexColor("#F8FAFC")
        border_color = colors.HexColor("#CBD5E1")
        text_dark = colors.HexColor("#1E293B")
        text_muted = colors.HexColor("#64748B")

        # Custom text styles
        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading1'],
            fontSize=18,
            leading=22,
            textColor=navy,
            fontName='Helvetica-Bold',
        )
        subtitle_style = ParagraphStyle(
            'ReportSubtitle',
            parent=styles['Normal'],
            fontSize=9,
            leading=12,
            textColor=text_muted,
            fontName='Helvetica',
        )
        h2_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontSize=11,
            leading=14,
            textColor=indigo_dark,
            fontName='Helvetica-Bold',
            spaceBefore=10,
            spaceAfter=4,
        )
        body_style = ParagraphStyle(
            'BodyText',
            parent=styles['Normal'],
            fontSize=8.5,
            leading=12,
            textColor=text_dark,
            fontName='Helvetica',
        )
        bullet_style = ParagraphStyle(
            'BulletItem',
            parent=body_style,
            leftIndent=12,
            bulletIndent=4,
            spaceAfter=3,
        )
        table_hdr = ParagraphStyle(
            'TableHdr',
            parent=styles['Normal'],
            fontSize=8,
            leading=10,
            textColor=colors.white,
            fontName='Helvetica-Bold',
        )
        table_cell = ParagraphStyle(
            'TableCell',
            parent=styles['Normal'],
            fontSize=8,
            leading=11,
            textColor=text_dark,
            fontName='Helvetica',
        )
        table_cell_bold = ParagraphStyle(
            'TableCellBold',
            parent=styles['Normal'],
            fontSize=8,
            leading=11,
            textColor=navy,
            fontName='Helvetica-Bold',
        )

        # Header Title
        story.append(Paragraph("GRADEWISE AI FEEDBACK REPORT", title_style))
        gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        story.append(Paragraph(f"Automated Multi-Stage Rubric & Evidence Assessment • Generated on {gen_time}", subtitle_style))
        story.append(Spacer(1, 6))
        story.append(HRFlowable(width="100%", thickness=1.5, color=indigo, spaceAfter=8))

        # Extract Core Scores & Verdict
        score = float(report_data.get("score") if report_data.get("score") is not None else report_data.get("overallScore", 0))
        max_score = float(report_data.get("max_score") if report_data.get("max_score") is not None else report_data.get("maxScore", 100))
        pct = (score / max_score * 100) if max_score > 0 else 0

        raw_verdict = str(report_data.get("verdict") or report_data.get("status") or "completed").upper()
        if pct >= 80:
            verdict_color = "#059669"
            verdict_label = "EXCELLENT / PASS" if "PASS" in raw_verdict or "EXCELLENT" in raw_verdict else raw_verdict
        elif pct >= 60:
            verdict_color = "#0284C7"
            verdict_label = "GOOD / SATISFACTORY"
        else:
            verdict_color = "#DC2626"
            verdict_label = "NEEDS IMPROVEMENT" if "IMPROVEMENT" in raw_verdict or "FAIL" in raw_verdict else raw_verdict

        # Metadata & Score Table
        s_name = _clean_text(student_name or "Student")
        f_name = _clean_text(file_name or report_data.get("fileName") or "submission_file")
        a_title = _clean_text(assignment_title or report_data.get("assignmentTitle") or "Assignment Submission")
        format_display = _clean_text(assignment_type.capitalize())

        meta_rows = [
            [
                Paragraph(f"<b>Student Name:</b> {s_name}", body_style),
                Paragraph("<b>Overall Score:</b>", body_style),
            ],
            [
                Paragraph(f"<b>Submission File:</b> {f_name}", body_style),
                Paragraph(f'<font size=13 color="#1E3A8A"><b>{score:.1f} / {max_score:.1f}</b></font> <font size=9 color="#64748B">({pct:.1f}%)</font>', body_style),
            ],
            [
                Paragraph(f"<b>Assignment:</b> {a_title}", body_style),
                Paragraph(f'<b>Verdict:</b> <font color="{verdict_color}"><b>{_clean_text(verdict_label)}</b></font>', body_style),
            ],
            [
                Paragraph(f"<b>Format:</b> {format_display} • <b>Tier:</b> {_clean_text(str(report_data.get('tier_used', 'agentic')).replace('_', ' ').title())}", body_style),
                Paragraph(f"<b>Integrity:</b> {_clean_text(str(report_data.get('plagiarism_similarity_score', report_data.get('plagiarismScore', 0.0))))}% Similarity", body_style),
            ],
        ]

        meta_table = Table(meta_rows, colWidths=[340, 200])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), light_slate),
            ('BACKGROUND', (1, 0), (1, -1), colors.HexColor("#EFF6FF")),
            ('BOX', (0, 0), (-1, -1), 0.5, border_color),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('PADDING', (0, 0), (-1, -1), 4.5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 10))

        # Executive Summary / Feedback
        summary_text = (
            report_data.get("student_feedback")
            or report_data.get("summary")
            or report_data.get("feedback")
            or report_data.get("instructor_brief")
            or ""
        )
        if summary_text:
            story.append(Paragraph("Executive Summary & Feedback", h2_style))
            story.append(Paragraph(_clean_text(summary_text), body_style))
            story.append(Spacer(1, 8))

        # Rubric & Criteria Breakdown Table
        per_criterion = report_data.get("per_criterion") or {}
        criteria_notes = report_data.get("criteria_notes") or {}
        rubric_scores = report_data.get("rubricScores") or []

        if per_criterion or rubric_scores:
            story.append(Paragraph("Rubric & Criteria Assessment Breakdown", h2_style))
            r_rows = [
                [
                    Paragraph("Criterion", table_hdr),
                    Paragraph("Score", table_hdr),
                    Paragraph("Evidence & Deductions", table_hdr),
                    Paragraph("Action Item", table_hdr),
                ]
            ]

            if per_criterion:
                for crit_id, raw_val in per_criterion.items():
                    c_score = raw_val.get("score", 0) if isinstance(raw_val, dict) else raw_val
                    notes = criteria_notes.get(crit_id) or (raw_val if isinstance(raw_val, dict) else {})
                    
                    crit_name = _clean_text(crit_id.replace("_", " ").title())
                    crit_score_text = f"{float(c_score):.1f} pts"

                    evidence_parts = []
                    if notes.get("evidence"):
                        evidence_parts.append(f"<b>Evidence:</b> {_clean_text(notes['evidence'])}")
                    if notes.get("deduction_reason"):
                        evidence_parts.append(f"<b>Deduction:</b> <font color='#DC2626'>{_clean_text(notes['deduction_reason'])}</font>")
                    if notes.get("note") and not notes.get("evidence"):
                        evidence_parts.append(_clean_text(notes["note"]))
                    if not evidence_parts:
                        evidence_parts.append("Evaluated according to standard rubric.")

                    action_text = _clean_text(notes.get("action") or "Maintain performance standard.")

                    r_rows.append([
                        Paragraph(crit_name, table_cell_bold),
                        Paragraph(crit_score_text, table_cell_bold),
                        Paragraph("<br/>".join(evidence_parts), table_cell),
                        Paragraph(action_text, table_cell),
                    ])
            elif rubric_scores:
                for item in rubric_scores:
                    crit_name = _clean_text(item.get("criterion", "Criterion"))
                    crit_score_text = f"{item.get('score', 0)} / {item.get('maxScore', 10)}"
                    justification = _clean_text(item.get("justification", ""))
                    r_rows.append([
                        Paragraph(crit_name, table_cell_bold),
                        Paragraph(crit_score_text, table_cell_bold),
                        Paragraph(justification, table_cell),
                        Paragraph("See detailed recommendations below.", table_cell),
                    ])

            r_tab = Table(r_rows, colWidths=[120, 65, 235, 120])
            r_tab.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), indigo_dark),
                ('BOX', (0, 0), (-1, -1), 0.5, border_color),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ('PADDING', (0, 0), (-1, -1), 4.5),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(r_tab)
            story.append(Spacer(1, 10))

        # Key Strengths
        strengths = report_data.get("strengths") or []
        if isinstance(strengths, list) and len(strengths) > 0:
            story.append(Paragraph("Key Strengths", h2_style))
            for item in strengths:
                if str(item).strip():
                    story.append(Paragraph(f"• {_clean_text(item)}", bullet_style))
            story.append(Spacer(1, 6))

        # Areas for Improvement / Weaknesses
        weaknesses = report_data.get("weaknesses") or []
        if isinstance(weaknesses, list) and len(weaknesses) > 0:
            story.append(Paragraph("Areas for Improvement", h2_style))
            for item in weaknesses:
                if str(item).strip():
                    story.append(Paragraph(f"• {_clean_text(item)}", bullet_style))
            story.append(Spacer(1, 6))

        # Actionable Next Steps / Suggestions
        suggestions = report_data.get("suggestions") or report_data.get("priority_actions") or []
        if isinstance(suggestions, list) and len(suggestions) > 0:
            story.append(Paragraph("Actionable Recommendations & Next Steps", h2_style))
            for item in suggestions:
                if str(item).strip():
                    story.append(Paragraph(f"• {_clean_text(item)}", bullet_style))
            story.append(Spacer(1, 6))

        # Code Sandbox Test Cases (for coding submissions)
        sandbox_logs = report_data.get("sandbox_logs") or report_data.get("code_execution_result") or []
        if isinstance(sandbox_logs, list) and len(sandbox_logs) > 0:
            story.append(Paragraph("Code Sandbox Test Suite Results", h2_style))
            s_rows = [
                [
                    Paragraph("Test Case", table_hdr),
                    Paragraph("Status", table_hdr),
                    Paragraph("Input", table_hdr),
                    Paragraph("Expected Output", table_hdr),
                    Paragraph("Actual Output", table_hdr),
                ]
            ]
            for i, log in enumerate(sandbox_logs):
                passed = log.get("passed", False)
                status_color = "#059669" if passed else "#DC2626"
                status_str = "PASS" if passed else "FAIL"
                s_rows.append([
                    Paragraph(f"Test #{i+1}", table_cell_bold),
                    Paragraph(f'<font color="{status_color}"><b>{status_str}</b></font>', table_cell_bold),
                    Paragraph(_clean_text(log.get("input", "")), table_cell),
                    Paragraph(_clean_text(log.get("expected_output", "")), table_cell),
                    Paragraph(_clean_text(log.get("actual_output", log.get("error", ""))), table_cell),
                ])
            s_tab = Table(s_rows, colWidths=[60, 50, 140, 145, 145])
            s_tab.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#334155")),
                ('BOX', (0, 0), (-1, -1), 0.5, border_color),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ('PADDING', (0, 0), (-1, -1), 4),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(s_tab)
            story.append(Spacer(1, 8))

        # Final Comments
        final_comments = report_data.get("finalComments") or report_data.get("score_rationale") or ""
        if final_comments and final_comments != summary_text:
            story.append(Paragraph("Evaluator Comments", h2_style))
            story.append(Paragraph(_clean_text(final_comments), body_style))
            story.append(Spacer(1, 6))

        # Build PDF
        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

    async def generate_student_pdf(
        self,
        report_data: Dict[str, Any],
        student_name: str,
        assignment_type: str,
        output_path: str,
        file_name: str = "",
        assignment_title: str = "",
    ) -> str:
        """
        Generates PDF report and writes to output_path.
        """
        logger.info(f"Generating student PDF report file for {student_name} at {output_path}...")
        try:
            pdf_bytes = self.generate_student_pdf_bytes(
                report_data=report_data,
                student_name=student_name,
                assignment_type=assignment_type,
                file_name=file_name,
                assignment_title=assignment_title,
            )
            with open(output_path, "wb") as f:
                f.write(pdf_bytes)
            logger.info("Successfully generated PDF report via ReportLab.")
            return output_path
        except Exception as e:
            logger.error(f"ReportLab PDF compilation failed: {e}. Writing markdown file fallback instead.")
            md_path = output_path.replace(".pdf", ".md")
            self._write_markdown_report(report_data, student_name, assignment_type, md_path)
            return md_path

    async def generate_batch_excel(self, batch_data: List[Dict[str, Any]], output_path: str) -> str:
        """
        Compiles batch job grades into an Excel worksheet.
        """
        logger.info(f"Generating batch Excel overview at {output_path}...")
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Batch Grades Report"

            headers = [
                "Student Name", "File Name", "Score", "Max Score", "Percentage",
                "Verdict / Status", "Strengths Summary", "Weaknesses Summary",
                "Actionable Suggestions", "Plagiarism %"
            ]
            ws.append(headers)

            header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
            header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
            align_center = Alignment(horizontal="center", vertical="center")
            align_left = Alignment(horizontal="left", vertical="center")

            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=1, column=col_idx)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = align_center

            for row_idx, record in enumerate(batch_data, start=2):
                strengths = "; ".join(record.get("strengths", [])) if isinstance(record.get("strengths"), list) else str(record.get("strengths", ""))
                weaknesses = "; ".join(record.get("weaknesses", [])) if isinstance(record.get("weaknesses"), list) else str(record.get("weaknesses", ""))
                suggestions = "; ".join(record.get("suggestions", [])) if isinstance(record.get("suggestions"), list) else str(record.get("suggestions", ""))

                score = float(record.get("score") if record.get("score") is not None else record.get("overallScore", 0))
                max_score = float(record.get("max_score") if record.get("max_score") is not None else record.get("maxScore", 100))
                pct = f"{(score / max_score * 100):.1f}%" if max_score > 0 else "0%"

                row_data = [
                    record.get("studentName", record.get("student_name", "Student")),
                    record.get("fileName", record.get("file_name", "assignment")),
                    score,
                    max_score,
                    pct,
                    str(record.get("status", record.get("verdict", "COMPLETED"))).upper(),
                    strengths,
                    weaknesses,
                    suggestions,
                    f"{record.get('plagiarismScore', record.get('plagiarism_similarity_score', 0.0))}%",
                ]
                ws.append(row_data)

                for col_idx in range(1, len(row_data) + 1):
                    cell = ws.cell(row=row_idx, column=col_idx)
                    cell.alignment = align_center if col_idx in [3, 4, 5, 6, 10] else align_left

            for col in ws.columns:
                max_len = max(len(str(cell.value or '')) for cell in col)
                col_letter = openpyxl.utils.get_column_letter(col[0].column)
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 45)

            wb.save(output_path)
            logger.info("Successfully generated Excel report via openpyxl.")
            return output_path

        except Exception as e:
            logger.error(f"Excel compilation failed: {e}. Writing standard CSV sheet instead.")
            csv_path = output_path.replace(".xlsx", ".csv")
            self._write_csv_report(batch_data, csv_path)
            return csv_path

    def _write_markdown_report(self, report_data: Dict[str, Any], student_name: str, assignment_type: str, path: str):
        content = (
            f"# AI-Powered Feedback Report\n\n"
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"**Student Name:** {student_name}\n"
            f"**Assignment Type:** {assignment_type.capitalize()}\n"
            f"**Overall Grade:** {report_data.get('score', report_data.get('overallScore', 0))}/{report_data.get('max_score', report_data.get('maxScore', 100))}\n"
            f"**Status:** {report_data.get('status', 'Completed').upper()}\n\n"
            f"## Performance Summary\n"
            f"{report_data.get('summary', report_data.get('student_feedback', ''))}\n\n"
            f"## Key Strengths\n"
        )
        for s in report_data.get("strengths", []):
            content += f"- {s}\n"

        content += "\n## Areas for Improvement\n"
        for w in report_data.get("weaknesses", []):
            content += f"- {w}\n"

        content += "\n## Actionable Suggestions\n"
        for sug in report_data.get("suggestions", []):
            content += f"- {sug}\n"

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _write_csv_report(self, batch_data: List[Dict[str, Any]], path: str):
        import csv
        headers = [
            "Student Name", "File Name", "Overall Score", "Status",
            "Strengths Summary", "Weaknesses Summary", "Suggestions Summary",
            "Plagiarism %"
        ]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for record in batch_data:
                writer.writerow([
                    record.get("studentName", record.get("student_name", "Student")),
                    record.get("fileName", record.get("file_name", "assignment")),
                    record.get("score", record.get("overallScore", 0)),
                    record.get("status", "completed").upper(),
                    "; ".join(record.get("strengths", [])) if isinstance(record.get("strengths"), list) else str(record.get("strengths", "")),
                    "; ".join(record.get("weaknesses", [])) if isinstance(record.get("weaknesses"), list) else str(record.get("weaknesses", "")),
                    "; ".join(record.get("suggestions", [])) if isinstance(record.get("suggestions"), list) else str(record.get("suggestions", "")),
                    f"{record.get('plagiarismScore', 0.0)}%",
                ])


# Initialize global instance
report_service = ReportService()
