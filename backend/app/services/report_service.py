import os
import logging
from datetime import datetime
from typing import Dict, Any, List
from backend.app.config import settings

logger = logging.getLogger("report_service")

class ReportService:
    async def generate_student_pdf(self, report_data: Dict[str, Any], student_name: str, assignment_type: str, output_path: str) -> str:
        """
        Generates a beautifully typeset PDF feedback sheet using ReportLab.
        If ReportLab is not available, compiles a stunning markdown fallback (.md) instead.
        """
        logger.info(f"Generating student report file for {student_name}...")
        
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib import colors
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            
            # Setup PDF doc template
            doc = SimpleDocTemplate(output_path, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
            story = []
            
            styles = getSampleStyleSheet()
            
            # Palette styling matching Indigo / Emerald theme
            indigo = colors.HexColor("#3F51B5")
            emerald = colors.HexColor("#00E676")
            dark_gray = colors.HexColor("#333333")
            light_gray = colors.HexColor("#F5F5F5")
            
            # Custom text styles
            title_style = ParagraphStyle(
                'ReportTitle',
                parent=styles['Heading1'],
                fontSize=22,
                leading=26,
                textColor=indigo,
                spaceAfter=15
            )
            
            subtitle_style = ParagraphStyle(
                'ReportSubtitle',
                parent=styles['Normal'],
                fontSize=11,
                leading=14,
                textColor=colors.HexColor("#666666"),
                spaceAfter=20
            )
            
            h2_style = ParagraphStyle(
                'SectionHeader',
                parent=styles['Heading2'],
                fontSize=14,
                leading=18,
                textColor=indigo,
                spaceBefore=12,
                spaceAfter=6
            )
            
            body_style = ParagraphStyle(
                'BodyText',
                parent=styles['Normal'],
                fontSize=10,
                leading=14,
                textColor=dark_gray,
                spaceAfter=8
            )

            bullet_style = ParagraphStyle(
                'BulletItem',
                parent=body_style,
                leftIndent=15,
                bulletIndent=5,
                spaceAfter=4
            )
            
            # Document Header
            story.append(Paragraph("AI-POWERED FEEDBACK REPORT", title_style))
            story.append(Paragraph(f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Student Assignment Assessment", subtitle_style))
            
            # Student Profile Table
            meta_data = [
                [Paragraph("<b>Student Name:</b>", body_style), Paragraph(student_name, body_style)],
                [Paragraph("<b>Assignment Format:</b>", body_style), Paragraph(assignment_type.capitalize(), body_style)],
                [Paragraph("<b>Overall Score:</b>", body_style), Paragraph(f"<b>{report_data.get('overallScore', 0)} / 100</b>", body_style)],
                [Paragraph("<b>Status:</b>", body_style), Paragraph(report_data.get('status', 'N/A').upper(), body_style)]
            ]
            meta_table = Table(meta_data, colWidths=[150, 350])
            meta_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), light_gray),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor("#E0E0E0")),
            ]))
            story.append(meta_table)
            story.append(Spacer(1, 15))
            
            # Performance Summary
            story.append(Paragraph("Executive Summary", h2_style))
            story.append(Paragraph(report_data.get("summary", ""), body_style))
            story.append(Spacer(1, 10))
            
            # Strengths, Weaknesses, Suggestions
            story.append(Paragraph("Key Strengths", h2_style))
            for strength in report_data.get("strengths", []):
                story.append(Paragraph(f"• {strength}", bullet_style))
            story.append(Spacer(1, 10))
            
            story.append(Paragraph("Areas for Improvement", h2_style))
            for weakness in report_data.get("weaknesses", []):
                story.append(Paragraph(f"• {weakness}", bullet_style))
            story.append(Spacer(1, 10))

            story.append(Paragraph("Actionable Suggestions", h2_style))
            for suggestion in report_data.get("suggestions", []):
                story.append(Paragraph(f"• {suggestion}", bullet_style))
            story.append(Spacer(1, 15))
            
            # Rubric Breakdown Table
            rubric_scores = report_data.get("rubricScores", [])
            if rubric_scores:
                story.append(Paragraph("Grading Rubrics Analysis", h2_style))
                rubric_header = [Paragraph("<b>Criterion</b>", body_style), Paragraph("<b>Score</b>", body_style), Paragraph("<b>Justification</b>", body_style)]
                rubric_rows = [rubric_header]
                for item in rubric_scores:
                    rubric_rows.append([
                        Paragraph(item.get("criterion", "Criterion"), body_style),
                        Paragraph(f"{item.get('score', 0)} / {item.get('maxScore', 10)}", body_style),
                        Paragraph(item.get("justification", ""), body_style)
                    ])
                
                rubric_table = Table(rubric_rows, colWidths=[130, 80, 290])
                rubric_table.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), indigo),
                    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                    ('TOPPADDING', (0,0), (-1,-1), 8),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#DDDDDD")),
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ]))
                # Patch text color for header row cells
                for i in range(3):
                    rubric_header[i].style.textColor = colors.white
                
                story.append(rubric_table)
                story.append(Spacer(1, 15))
            
            # Final Remarks
            story.append(Paragraph("Evaluator Comments", h2_style))
            story.append(Paragraph(report_data.get("finalComments", "Great work!"), body_style))
            
            # Build Document
            doc.build(story)
            logger.info("Successfully generated PDF report via ReportLab.")
            return output_path
            
        except Exception as e:
            logger.error(f"ReportLab PDF compilation failed: {e}. Writing markdown file fallback instead.")
            # Graceful Markdown Fallback (.md)
            md_path = output_path.replace(".pdf", ".md")
            self._write_markdown_report(report_data, student_name, assignment_type, md_path)
            return md_path

    async def generate_batch_excel(self, batch_data: List[Dict[str, Any]], output_path: str) -> str:
        """
        Compiles batch job grades into an Excel worksheet.
        Falls back to CSV format if openpyxl is not installed.
        """
        logger.info(f"Generating batch Excel overview at {output_path}...")
        
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Batch Grades Report"
            
            # Table Headers
            headers = [
                "Student Name", "File Name", "Overall Score", "Status",
                "Strengths Summary", "Weaknesses Summary", "Suggestions Summary",
                "Plagiarism %", "PDF Report Link"
            ]
            ws.append(headers)
            
            # Styling definitions
            header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
            header_fill = PatternFill(start_color="3F51B5", end_color="3F51B5", fill_type="solid") # Indigo fill
            align_center = Alignment(horizontal="center", vertical="center")
            align_left = Alignment(horizontal="left", vertical="center")
            
            # Apply Header Style
            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=1, column=col_idx)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = align_center
                
            # Populate grading records
            for row_idx, record in enumerate(batch_data, start=2):
                strengths = "; ".join(record.get("strengths", []))
                weaknesses = "; ".join(record.get("weaknesses", []))
                suggestions = "; ".join(record.get("suggestions", []))
                
                row_data = [
                    record.get("studentName", "Student"),
                    record.get("fileName", "assignment.pdf"),
                    record.get("overallScore", 0),
                    record.get("status", "completed").upper(),
                    strengths,
                    weaknesses,
                    suggestions,
                    f"{record.get('plagiarismScore', 0.0)}%",
                    record.get("pdfUrl", "")
                ]
                ws.append(row_data)
                
                # Apply row styling alignment
                for col_idx in range(1, len(row_data) + 1):
                    cell = ws.cell(row=row_idx, column=col_idx)
                    cell.alignment = align_center if col_idx in [3, 4, 8] else align_left
            
            # Auto-fit column widths
            for col in ws.columns:
                max_len = max(len(str(cell.value or '')) for cell in col)
                col_letter = openpyxl.utils.get_column_letter(col[0].column)
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 40)
                
            wb.save(output_path)
            logger.info("Successfully generated Excel report via openpyxl.")
            return output_path
            
        except Exception as e:
            logger.error(f"Excel compilation failed: {e}. Writing standard CSV sheet instead.")
            # CSV Fallback
            csv_path = output_path.replace(".xlsx", ".csv")
            self._write_csv_report(batch_data, csv_path)
            return csv_path

    def _write_markdown_report(self, report_data: Dict[str, Any], student_name: str, assignment_type: str, path: str):
        content = (
            f"# AI-Powered Feedback Report\n\n"
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"**Student Name:** {student_name}\n"
            f"**Assignment Type:** {assignment_type.capitalize()}\n"
            f"**Overall Grade:** {report_data.get('overallScore', 0)}/100\n"
            f"**Status:** {report_data.get('status', 'Completed').upper()}\n\n"
            f"## Performance Summary\n"
            f"{report_data.get('summary', '')}\n\n"
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
            
        content += "\n## Rubric Breakdown\n"
        content += "| Criterion | Score | Justification |\n"
        content += "| :--- | :---: | :--- |\n"
        for r in report_data.get("rubricScores", []):
            content += f"| {r.get('criterion')} | {r.get('score')}/{r.get('maxScore')} | {r.get('justification')} |\n"
            
        content += f"\n## Final Remarks\n{report_data.get('finalComments', '')}\n"
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _write_csv_report(self, batch_data: List[Dict[str, Any]], path: str):
        import csv
        headers = [
            "Student Name", "File Name", "Overall Score", "Status",
            "Strengths Summary", "Weaknesses Summary", "Suggestions Summary",
            "Plagiarism %", "PDF Report Link"
        ]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for record in batch_data:
                writer.writerow([
                    record.get("studentName", "Student"),
                    record.get("fileName", "assignment.pdf"),
                    record.get("overallScore", 0),
                    record.get("status", "completed").upper(),
                    "; ".join(record.get("strengths", [])),
                    "; ".join(record.get("weaknesses", [])),
                    "; ".join(record.get("suggestions", [])),
                    f"{record.get('plagiarismScore', 0.0)}%",
                    record.get("pdfUrl", "")
                ])

# Initialize global instance
report_service = ReportService()
