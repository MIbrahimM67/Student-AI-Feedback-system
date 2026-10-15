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
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, HRFlowable
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        # Helvetica cannot render nonbreaking hyphens and several symbols that
        # appear in AI feedback. The Docker image installs these Unicode fonts.
        font_dir = "/usr/share/fonts/truetype/dejavu"
        if "GradeWiseSans" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("GradeWiseSans", os.path.join(font_dir, "DejaVuSans.ttf")))
            pdfmetrics.registerFont(TTFont("GradeWiseSans-Bold", os.path.join(font_dir, "DejaVuSans-Bold.ttf")))
            pdfmetrics.registerFontFamily("GradeWiseSans", normal="GradeWiseSans", bold="GradeWiseSans-Bold")

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=42,
            leftMargin=42,
            topMargin=48,
            bottomMargin=50,
        )
        story = []
        content_width = letter[0] - doc.leftMargin - doc.rightMargin

        styles = getSampleStyleSheet()

        # Theme Colors
        charcoal = colors.HexColor("#1B1B1B")
        butter = colors.HexColor("#F2E58F")
        paper = colors.HexColor("#F7F6F2")
        silver = colors.HexColor("#EAE9E4")
        border_color = colors.HexColor("#D7D6CF")
        text_dark = colors.HexColor("#282824")
        text_muted = colors.HexColor("#65655F")
        success = colors.HexColor("#2E684A")
        danger = colors.HexColor("#A04440")

        # Custom text styles
        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading1'],
            fontSize=18,
            leading=23,
            textColor=charcoal,
            fontName='GradeWiseSans-Bold',
            spaceAfter=2,
        )
        subtitle_style = ParagraphStyle(
            'ReportSubtitle',
            parent=styles['Normal'],
            fontSize=8,
            leading=11,
            textColor=text_muted,
            fontName='GradeWiseSans',
        )
        h2_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontSize=11,
            leading=14,
            textColor=charcoal,
            fontName='GradeWiseSans-Bold',
            spaceBefore=15,
            spaceAfter=7,
            keepWithNext=False,
        )
        body_style = ParagraphStyle(
            'BodyText',
            parent=styles['Normal'],
            fontSize=9,
            leading=13.5,
            textColor=text_dark,
            fontName='GradeWiseSans',
        )
        bullet_style = ParagraphStyle(
            'BulletItem',
            parent=body_style,
            leftIndent=14,
            bulletIndent=5,
            spaceAfter=5,
        )
        table_hdr = ParagraphStyle(
            'TableHdr',
            parent=styles['Normal'],
            fontSize=8,
            leading=11,
            textColor=charcoal,
            fontName='GradeWiseSans-Bold',
        )
        table_cell = ParagraphStyle(
            'TableCell',
            parent=styles['Normal'],
            fontSize=9,
            leading=14,
            textColor=text_dark,
            fontName='GradeWiseSans',
        )
        table_cell_bold = ParagraphStyle(
            'TableCellBold',
            parent=styles['Normal'],
            fontSize=9,
            leading=14,
            textColor=charcoal,
            fontName='GradeWiseSans-Bold',
        )

        # The quiet editorial header mirrors the dark workbench and yellow controls.
        masthead = Table([[
            Paragraph('<font color="#F2E58F"><b>G /</b></font>  <font color="#F5F5F1"><b>GRADEWISE</b></font>',
                      ParagraphStyle('Brand', fontName='GradeWiseSans-Bold', fontSize=12, leading=16)),
            Paragraph('<font color="#F2E58F">ASSESSMENT REPORT</font>',
                      ParagraphStyle('Kicker', fontName='GradeWiseSans-Bold', fontSize=8, leading=12, alignment=2)),
        ]], colWidths=[content_width * .58, content_width * .42])
        masthead.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), charcoal),
            ('TOPPADDING', (0, 0), (-1, -1), 14),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
            ('LEFTPADDING', (0, 0), (-1, -1), 15),
            ('RIGHTPADDING', (0, 0), (-1, -1), 15),
        ]))
        story.append(masthead)
        story.append(Spacer(1, 17))
        story.append(Paragraph("Student feedback report", title_style))
        gen_time = datetime.now().strftime("%d %b %Y · %H:%M")
        story.append(Paragraph(f"Rubric assessment and evidence  /  Generated {gen_time}", subtitle_style))
        story.append(Spacer(1, 15))

        # Extract Core Scores & Verdict
        score = float(report_data.get("score") if report_data.get("score") is not None else report_data.get("overallScore", 0))
        max_score = float(report_data.get("max_score") if report_data.get("max_score") is not None else report_data.get("maxScore", 100))
        pct = (score / max_score * 100) if max_score > 0 else 0

        raw_verdict = str(report_data.get("verdict") or report_data.get("status") or "completed").upper()
        if pct >= 80:
            verdict_color = "#2E684A"
            verdict_label = "EXCELLENT / PASS" if "PASS" in raw_verdict or "EXCELLENT" in raw_verdict else raw_verdict
        elif pct >= 60:
            verdict_color = "#645B28"
            verdict_label = "GOOD / SATISFACTORY"
        else:
            verdict_color = "#A04440"
            verdict_label = "NEEDS IMPROVEMENT" if "IMPROVEMENT" in raw_verdict or "FAIL" in raw_verdict else raw_verdict

        # Metadata & Score Table
        s_name = _clean_text(student_name or "Student")
        f_name = _clean_text(file_name or report_data.get("fileName") or "submission_file")
        a_title = _clean_text(assignment_title or report_data.get("assignmentTitle") or "Assignment Submission")
        format_display = _clean_text(assignment_type.capitalize())
        similarity_score = report_data.get("plagiarism_similarity_score", report_data.get("plagiarismScore"))
        integrity_display = (
            f"{similarity_score}% Similarity" if similarity_score is not None
            else "Not checked"
        )

        meta_rows = [
            [
                Paragraph(f"<b>Student Name:</b> {s_name}", body_style),
                Paragraph("<b>Overall Score:</b>", body_style),
            ],
            [
                Paragraph(f"<b>Submission File:</b> {f_name}", body_style),
                Paragraph(f'<font size=16 color="#1B1B1B"><b>{score:.1f} / {max_score:.1f}</b></font> <font size=9 color="#65655F">({pct:.1f}%)</font>', body_style),
            ],
            [
                Paragraph(f"<b>Assignment:</b> {a_title}", body_style),
                Paragraph(f'<b>Verdict:</b> <font color="{verdict_color}"><b>{_clean_text(verdict_label)}</b></font>', body_style),
            ],
            [
                Paragraph(f"<b>Format:</b> {format_display} • <b>Tier:</b> {_clean_text(str(report_data.get('tier_used', 'agentic')).replace('_', ' ').title())}", body_style),
                Paragraph(f"<b>Integrity:</b> {_clean_text(integrity_display)}", body_style),
            ],
        ]

        meta_table = Table(meta_rows, colWidths=[content_width * .64, content_width * .36])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), paper),
            ('BACKGROUND', (1, 0), (1, -1), silver),
            ('LINEBELOW', (0, 0), (-1, 0), 2, butter),
            ('BOX', (0, 0), (-1, -1), 0.6, border_color),
            ('INNERGRID', (0, 0), (-1, -1), 0.35, border_color),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 12))

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

        # Full-width criterion blocks keep evidence and deductions legible on
        # letter paper. A four-column table squeezed each line into tiny type.
        per_criterion = report_data.get("per_criterion") or {}
        criteria_notes = report_data.get("criteria_notes") or {}
        rubric_scores = report_data.get("rubricScores") or []

        if per_criterion or rubric_scores:
            story.append(Paragraph("Rubric & Criteria Assessment Breakdown", h2_style))
            criterion_text = ParagraphStyle(
                "CriterionDetail", parent=body_style, fontSize=9.3,
                leading=15, leftIndent=10, rightIndent=10, spaceAfter=6,
            )
            criterion_name = ParagraphStyle(
                "CriterionName", parent=table_cell_bold, fontSize=10,
                leading=14,
            )
            def criterion_block(name, score, note, evidence, deduction, action):
                header = Table([[
                    Paragraph(_clean_text(name), criterion_name),
                    Paragraph(_clean_text(score), criterion_name),
                ]], colWidths=[content_width * .76, content_width * .24])
                header.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), butter),
                    ("BOX", (0, 0), (-1, -1), .5, border_color),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ]))
                body = []
                if note:
                    body.append(Paragraph(_clean_text(note), criterion_text))
                if evidence:
                    body.append(Paragraph(f"<b>Student evidence</b>  {_clean_text(evidence)}", criterion_text))
                if deduction:
                    body.append(Paragraph(f"<b>Reason for deduction</b>  <font color='#8C3834'>{_clean_text(deduction)}</font>", criterion_text))
                if action:
                    body.append(Paragraph(f"<b>Next step</b>  {_clean_text(action)}", criterion_text))
                if not body:
                    body.append(Paragraph("No supporting criterion notes were recorded.", criterion_text))
                story.append(KeepTogether([header, body[0]]))
                story.extend(body[1:])
                story.append(Spacer(1, 8))
            if per_criterion:
                for crit_id, raw_val in per_criterion.items():
                    c_score = raw_val.get("score", 0) if isinstance(raw_val, dict) else raw_val
                    notes = criteria_notes.get(crit_id) or (raw_val if isinstance(raw_val, dict) else {})
                    criterion_block(
                        crit_id.replace("_", " ").title(), f"{float(c_score):.1f} pts",
                        notes.get("note"), notes.get("evidence"),
                        notes.get("deduction_reason"), notes.get("action"),
                    )
            elif rubric_scores:
                for item in rubric_scores:
                    criterion_block(
                        item.get("criterion", "Criterion"),
                        f"{item.get('score', 0)} / {item.get('maxScore', 10)}",
                        None, item.get("justification"), None, None,
                    )

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

        # Show observed sandbox data. Exit code 0 means execution, not correctness.
        sandbox_logs = report_data.get("sandbox_logs") or report_data.get("code_execution_result") or []
        checks = report_data.get("code_execution_checks") or (sandbox_logs if isinstance(sandbox_logs, list) else [])
        if checks or isinstance(sandbox_logs, str) and sandbox_logs.strip():
            story.append(Paragraph("Program Execution Evidence", h2_style))
            story.append(Paragraph(
                "Inputs and outputs below were observed in the sandbox. Execution alone does not establish correctness; compare the output with the assignment and rubric.",
                subtitle_style,
            ))
            story.append(Spacer(1, 8))
        if checks:
            s_rows = [[
                Paragraph("Test / result", table_hdr),
                Paragraph("Input provided", table_hdr),
                Paragraph("Observed output / errors", table_hdr),
            ]]
            for i, log in enumerate(checks):
                if not isinstance(log, dict):
                    continue
                status = str(log.get("status") or ("Executed" if log.get("passed") else "Failed"))
                exit_code = log.get("exit_code")
                status_color = "#A04440" if "error" in status.lower() or "fail" in status.lower() else "#2E684A"
                input_text = str(log.get("input") or "[empty stdin]")[:1200]
                output_text = str(log.get("actual_output") or log.get("stdout") or "[no output]")[:1800]
                error_text = str(log.get("stderr") or log.get("error") or "")[:800]
                if error_text:
                    output_text += "\nErrors: " + error_text
                def lines(value):
                    return _clean_text(value).replace("\n", "<br/>")
                s_rows.append([
                    Paragraph(f"<b>{_clean_text(log.get('name') or f'Test {i + 1}')}</b><br/>"
                              f'<font color="{status_color}">{_clean_text(status)}</font>'
                              + (f"<br/>Exit code: {_clean_text(exit_code)}" if exit_code is not None else ""), table_cell),
                    Paragraph(lines(input_text), table_cell),
                    Paragraph(lines(output_text), table_cell),
                ])
            s_tab = Table(s_rows, colWidths=[content_width * .24, content_width * .32, content_width * .44], repeatRows=1, splitInRow=1, hAlign='LEFT')
            s_tab.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), butter),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, paper]),
                ('LINEBELOW', (0, 0), (-1, 0), 1, charcoal),
                ('BOX', (0, 0), (-1, -1), 0.5, border_color),
                ('LINEBELOW', (0, 1), (-1, -2), 0.35, border_color),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 7),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(s_tab)
            story.append(Spacer(1, 8))
        elif isinstance(sandbox_logs, str) and sandbox_logs.strip():
            # Historical reports stored the execution trace as one string.
            for block in sandbox_logs.split("\n\n"):
                if block.strip():
                    story.append(Paragraph(
                        _clean_text(block[:2800]).replace("\n", "<br/>"),
                        table_cell,
                    ))
                    story.append(Spacer(1, 7))

        # Final Comments
        final_comments = report_data.get("finalComments") or report_data.get("score_rationale") or ""
        if final_comments and final_comments != summary_text:
            story.append(Paragraph("Evaluator Comments", h2_style))
            story.append(Paragraph(_clean_text(final_comments), body_style))
            story.append(Spacer(1, 6))

        def draw_page(canvas, document):
            canvas.saveState()
            width, _ = letter
            canvas.setStrokeColor(border_color)
            canvas.setLineWidth(.6)
            canvas.line(document.leftMargin, 35, width - document.rightMargin, 35)
            canvas.setFont('GradeWiseSans-Bold', 7)
            canvas.setFillColor(charcoal)
            canvas.drawString(document.leftMargin, 23, 'GRADEWISE  /  FEEDBACK REPORT')
            canvas.setFont('GradeWiseSans', 7)
            canvas.setFillColor(text_muted)
            canvas.drawRightString(width - document.rightMargin, 23, f'PAGE {document.page}')
            canvas.restoreState()

        doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
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

