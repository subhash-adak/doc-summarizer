import csv
import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.summary import DocumentSummary, SummaryStatus


def build_csv(results: list[DocumentSummary]) -> bytes:
    """
    Build a UTF-8 CSV report from summarization results.
    Returns raw bytes suitable for a StreamingResponse.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "File Name",
            "Status",
            "Summary",
            "Characters",
            "Chunks",
            "Processing Time (ms)",
            "Drive Link",
            "Summarized At",
        ],
        quoting=csv.QUOTE_ALL,
    )
    writer.writeheader()

    for result in results:
        writer.writerow(
            {
                "File Name": result.file.name,
                "Status": result.status.value,
                "Summary": result.summary or result.error_message or "",
                "Characters": result.char_count,
                "Chunks": result.chunk_count,
                "Processing Time (ms)": result.processing_time_ms or "",
                "Drive Link": result.file.web_view_link or "",
                "Summarized At": result.summarized_at.isoformat(),
            }
        )

    return buffer.getvalue().encode("utf-8-sig")  # BOM for Excel compatibility


def build_pdf(results: list[DocumentSummary]) -> bytes:
    """
    Build a styled PDF report using ReportLab.
    Returns raw bytes suitable for a StreamingResponse.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=colors.HexColor("#1a1a2e"),
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#666666"),
        spaceAfter=20,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#16213e"),
        spaceBefore=12,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=9,
        leading=14,
        textColor=colors.HexColor("#333333"),
    )
    error_style = ParagraphStyle(
        "Error",
        parent=body_style,
        textColor=colors.HexColor("#cc0000"),
    )

    story = []

    # Header 
    story.append(Paragraph("Document Summarization Report", title_style))
    story.append(
        Paragraph(
            f"Generated on: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} "
            f"| Documents: {len(results)}",
            subtitle_style,
        )
    )

    # Per-document summaries
    for i, result in enumerate(results, start=1):
        heading = f"File Name: <b>{result.file.name}</b>"

        if result.file.web_view_link:
            heading += (
                f' &nbsp;&nbsp;|&nbsp;&nbsp;'
                f'<a href="{result.file.web_view_link}" color="blue"><u>Link</u></a>'
            )

        story.append(Paragraph(heading, section_style))

        meta = (
            f"Status: <b>{result.status.value.title()}</b> | "
            f"Size: {result.file.size_kb or 'N/A'} KB | "
            f"Processed in: {result.processing_time_ms or '—'} ms"
        )

        story.append(Paragraph(meta, body_style))
        story.append(Spacer(1, 0.2 * cm))

        if result.summary:
            story.append(Paragraph(result.summary, body_style))
        elif result.error_message:
            story.append(Paragraph(f"Error: {result.error_message}", error_style))

        story.append(Spacer(1, 0.3 * cm))

    doc.build(story)
    return buffer.getvalue()
