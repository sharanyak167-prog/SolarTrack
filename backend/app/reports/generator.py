"""PDF Report Generator for SolarTrack.

Generates official college reports matching the faculty's approved format:
- Monthly tables with lines (a), (b), (c), (d), Total Consumption, and Monthly Savings.
- Cumulative metrics from project inception (18 March 2021).
- Period summary table for multi-month, six-monthly, and yearly reports.
- AI Executive Summary with numerical guardrails.
- Institutional header and signature block.
"""
from datetime import date
from decimal import Decimal
import io
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (HRFlowable, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from .ai_summary import generate_executive_summary

INCEPTION_DATE = date(2021, 3, 18)


def _fmt(val, suffix: str = "", prefix: str = "", decimals: int = 2) -> str:
    if val is None:
        return "N/A"
    try:
        d = Decimal(str(val))
        # Format with Indian numbering commas or standard
        if d == d.to_integral():
            s = f"{int(d):,}"
        else:
            s = f"{d:,.{decimals}f}"
        return f"{prefix}{s}{suffix}"
    except Exception:
        return f"{prefix}{val}{suffix}"


def generate_report_pdf(
    *,
    college_name: str = "ST JOSEPH ENGINEERING COLLEGE, VAMANJOOR, MANGALURU",
    connection_details: dict,
    start_date: date,
    end_date: date,
    months_data: list[dict],
    summary_data: dict,
    cumulative_data: Optional[dict] = None,
    include_ai_summary: bool = True,
    ai_summary_text: Optional[str] = None,
) -> bytes:
    """Generate professional PDF matching faculty's exact format and specifications."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=12,
        leading=16,
        alignment=1,  # Center
        fontName="Helvetica-Bold",
        textColor=colors.black,
    )
    inst_style = ParagraphStyle(
        "InstTitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        alignment=1,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1A365D"),
    )
    month_header_style = ParagraphStyle(
        "MonthHeader",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        fontName="Helvetica-Bold",
        textColor=colors.black,
    )
    cell_style = ParagraphStyle(
        "CellNormal",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        fontName="Helvetica",
    )
    cell_bold = ParagraphStyle(
        "CellBold",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        fontName="Helvetica-Bold",
    )
    cum_style = ParagraphStyle(
        "CumulativeText",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        fontName="Helvetica-Bold",
        textColor=colors.black,
    )
    ai_box_style = ParagraphStyle(
        "AIBox",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        fontName="Helvetica",
        textColor=colors.HexColor("#1E293B"),
    )

    story = []

    # Institution Header
    story.append(Paragraph(college_name, inst_style))
    story.append(Spacer(1, 4))

    # Title matching faculty format
    start_str = start_date.strftime("%d %B %Y")
    end_str = end_date.strftime("%d %B %Y")
    title_text = f"Details of Energy Generated from Solar Roof Top System from {start_str} to {end_str}"
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceAfter=12))

    # AI Summary if requested
    if include_ai_summary:
        if not ai_summary_text:
            ai_data = {
                "start_str": start_str,
                "end_str": end_str,
                "solar_generated": summary_data.get("total", {}).get("solar_generated"),
                "imported": summary_data.get("total", {}).get("imported"),
                "exported": summary_data.get("total", {}).get("exported"),
                "net_energy": summary_data.get("total", {}).get("net_energy"),
                "total_consumed": summary_data.get("total", {}).get("total_consumed"),
                "savings": summary_data.get("total", {}).get("savings"),
                "months_included": summary_data.get("months_included", len(months_data)),
            }
            ai_res = generate_executive_summary(ai_data)
            ai_summary_text = ai_res.get("summary", "")

        if ai_summary_text:
            summary_content = [
                Paragraph("<b>Executive Summary & Performance Analysis</b>", cell_bold),
                Spacer(1, 4),
                Paragraph(ai_summary_text.replace("\n", "<br/>"), ai_box_style),
            ]
            summary_table = Table([[summary_content]], colWidths=[520])
            summary_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#94A3B8")),
                ("PADDING", (0, 0), (-1, -1), 8),
            ]))
            story.append(summary_table)
            story.append(Spacer(1, 14))

    # Period Aggregated Summary if more than 1 month
    if len(months_data) > 1:
        tot = summary_data.get("total", {})
        agg_data = [
            [Paragraph("<b>Period Aggregated Summary</b>", cell_bold), Paragraph(f"<b>{len(months_data)} Months Total</b>", cell_bold)],
            [Paragraph("(a) Total Solar Generation", cell_style), Paragraph(f"{_fmt(tot.get('solar_generated'))} Units", cell_bold)],
            [Paragraph("(b) Total Energy Imported from MESCOM", cell_style), Paragraph(f"{_fmt(tot.get('imported'))} Units", cell_bold)],
            [Paragraph("(c) Total Exported to MESCOM", cell_style), Paragraph(f"{_fmt(tot.get('exported'))} Units", cell_bold)],
            [Paragraph("(d) Net Energy Import from MESCOM [(b)-(c)]", cell_style), Paragraph(f"{_fmt(tot.get('net_energy'))} Units", cell_bold)],
            [Paragraph("Total Electrical Energy Consumption [(a)+(d)]", cell_bold), Paragraph(f"{_fmt(tot.get('total_consumed'))} Units", cell_bold)],
            [Paragraph("Total Calculated Financial Savings", cell_bold), Paragraph(f"{_fmt(tot.get('savings'), prefix='Rs ')}", cell_bold)],
        ]
        agg_table = Table(agg_data, colWidths=[330, 190])
        agg_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ("BOX", (0, 0), (-1, -1), 1, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(agg_table)
        story.append(Spacer(1, 14))

    # Monthly Tables in Faculty's Exact Layout
    for idx, m in enumerate(months_data):
        m_label = m.get("month_label") or m.get("bill_month", "")
        # Format month title e.g. "March 2025:"
        try:
            m_date = date.fromisoformat(str(m["bill_month"]))
            m_title = f"{m_date.strftime('%B %Y')}:"
        except Exception:
            m_title = f"{m_label}:"

        e = m.get("energy", {})
        rate = m.get("rate_per_unit")
        rate_str = f"Rs {rate}" if rate is not None else "pending"

        table_data = [
            [Paragraph("(a) Solar Generation", cell_style), Paragraph(f"{_fmt(e.get('solar_generated'))} Units", cell_style)],
            [Paragraph("(b) Energy Imported from MESCOM", cell_style), Paragraph(f"{_fmt(e.get('imported'))} Units", cell_style)],
            [Paragraph("(c) Exported to MESCOM", cell_style), Paragraph(f"{_fmt(e.get('exported'))} Units", cell_style)],
            [Paragraph("(d) Net Energy Import from MESCOM [(b)-(c) ]", cell_style), Paragraph(f"{_fmt(e.get('net_energy'))} Units", cell_style)],
            [Paragraph("Total Electrical Energy Consumption [(a)+(d)]", cell_style), Paragraph(f"{_fmt(e.get('total_consumed'))} Units", cell_style)],
            [Paragraph(f"Savings (@ rate of {rate_str} per unit of energy generated from solar unit)", cell_style),
             Paragraph(f"{_fmt(e.get('savings'), prefix='Rs ')}", cell_style)],
        ]

        t = Table(table_data, colWidths=[330, 190])
        t.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("PADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))

        month_block = [
            Paragraph(m_title, month_header_style),
            Spacer(1, 3),
            t,
            Spacer(1, 10),
        ]

        # Add cumulative milestone if available for this month
        cum_units = m.get("cumulative_units")
        cum_savings = m.get("cumulative_savings")
        if cum_units is not None and cum_savings is not None:
            cum_block = [
                Paragraph(f"Total Units of Energy Generated from Solar Roof Top System (from 19th March 2021 to {m_date.strftime('%d %B %Y')}) = <b>{_fmt(cum_units)} Units</b>", cum_style),
                Paragraph(f"Total Savings in Rs = <b>{_fmt(cum_savings, prefix='Rs ')}</b>", cum_style),
                Spacer(1, 10),
            ]
            month_block.extend(cum_block)

        story.append(KeepTogether(month_block))

    # Overall Cumulative to Date
    if cumulative_data:
        c_units = cumulative_data.get("total_units")
        c_savings = cumulative_data.get("total_savings")
        if c_units and c_savings:
            cum_summary = [
                HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceAfter=8),
                Paragraph(f"Total Cumulative Units Generated (Since Inception 19 March 2021 to {end_str}) = <b>{_fmt(c_units)} Units</b>", cum_style),
                Paragraph(f"Total Cumulative Savings in Rs = <b>{_fmt(c_savings, prefix='Rs ')}</b>", cum_style),
                Spacer(1, 14),
            ]
            story.append(KeepTogether(cum_summary))

    # Signatures Footer
    sig_data = [
        [
            Paragraph("<b>Prepared by:</b><br/><br/><br/>Energy & Solar Systems Coordinator", cell_style),
            Paragraph("<b>Verified by:</b><br/><br/><br/>HOD / Faculty In-Charge", cell_style),
            Paragraph("<b>Approved by:</b><br/><br/><br/>Principal / Director", cell_style),
        ]
    ]
    sig_table = Table(sig_data, colWidths=[173, 173, 174])
    sig_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(KeepTogether([Spacer(1, 15), sig_table]))

    doc.build(story)
    return buffer.getvalue()
