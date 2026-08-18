"""PDF snapshot of a performance agreement (PC-1, ADR-010).

Deliberately reproduces the layout of the Excel scorecard staff already know
(KPI-Contracting-Investigation.md §2a): header block, then one row per KPI
under its Objective/Perspective heading with KPA · KPI · Metric · Weight and
the five target descriptors, sub-totals per objective, a grand total that must
read 1.00, the PDP list, and the signature block.

This file is what actually gets signed: `services/agreements.py` hashes the
bytes and stores the sha256 on every `AgreementSignature`, so "what did I
sign" is answerable years later. Keep it deterministic — no timestamps or
random ids inside the document body, or the same content would hash
differently on every render and re-signing could never be verified.
"""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

LEVELS = ("1", "2", "3", "4", "5")


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=13, spaceAfter=4),
        "sub": ParagraphStyle("s", parent=base["Normal"], fontSize=8, textColor=colors.HexColor("#555555")),
        "cell": ParagraphStyle("c", parent=base["BodyText"], fontSize=6.5, leading=8),
        "cellb": ParagraphStyle("cb", parent=base["BodyText"], fontSize=6.5, leading=8, fontName="Helvetica-Bold"),
        "head": ParagraphStyle("h", parent=base["BodyText"], fontSize=6.5, leading=8, fontName="Helvetica-Bold",
                               alignment=TA_CENTER, textColor=colors.white),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=10, spaceBefore=8, spaceAfter=3),
        "body": ParagraphStyle("b", parent=base["BodyText"], fontSize=8, leading=11),
    }


def _fmt_weight(weight: Decimal) -> str:
    return f"{Decimal(weight) * 100:.0f}%" if weight is not None else "—"


def _scale_labels(agreement) -> dict:
    scale = agreement.template.rating_scale or {}
    return {level: str(scale.get(level, level)) for level in LEVELS}


def render_agreement_pdf(agreement, *, stage: str) -> bytes:
    st = _styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), topMargin=12 * mm, bottomMargin=12 * mm,
        leftMargin=10 * mm, rightMargin=10 * mm,
        title=f"Individual Scorecard {agreement.period.name} — {agreement.employee.employee_number}",
        author="Sentech HCM",
    )
    employee = agreement.employee
    version = employee.current_version
    story = []

    story.append(Paragraph(f"Individual Scorecard for {agreement.period.name} Financial Year", st["title"]))
    header = [
        ["Name and Surname:", f"{employee.first_name} {employee.last_name}", "Employee number:", employee.employee_number],
        ["Division:", getattr(version.department, "name", "—") if version else "—",
         "Job Title:", (version.job_title if version else "") or "—"],
        ["Period:", f"{agreement.period.start_date:%d %b %Y} – {agreement.period.end_date:%d %b %Y}",
         "Stage / revision:", f"{stage} · rev {agreement.revision}"],
        ["Head / executive:", (
            f"{agreement.head.first_name} {agreement.head.last_name}" if agreement.head else "—"
        ), "Template:", f"{agreement.template.name} v{agreement.template_version}"],
    ]
    header_table = Table(header, colWidths=[32 * mm, 95 * mm, 32 * mm, 95 * mm])
    header_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#444444")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#444444")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    story += [header_table, Spacer(1, 5)]

    labels = _scale_labels(agreement)
    head_row = [
        Paragraph("OBJECTIVE", st["head"]), Paragraph("KPA Description", st["head"]),
        Paragraph("Key Performance Indicator", st["head"]), Paragraph("Metric", st["head"]),
        Paragraph("Weight", st["head"]),
    ] + [Paragraph(f"{level}<br/>{labels[level]}", st["head"]) for level in LEVELS]
    if stage == "final":
        head_row += [Paragraph("Rating", st["head"]), Paragraph("Score", st["head"])]

    rows = [head_row]
    spans, subtotal_rows = [], []
    elements = list(agreement.elements.all())
    current_section, section_start, section_total = None, 1, Decimal("0")

    def close_section(end_index: int):
        if current_section is None:
            return
        rows.append([
            "", "", Paragraph("SUB-TOTAL", st["cellb"]), "", Paragraph(_fmt_weight(section_total), st["cellb"]),
        ] + [""] * (len(head_row) - 5))
        subtotal_rows.append(len(rows) - 1)
        if end_index > section_start:
            spans.append(("SPAN", (0, section_start), (0, end_index - 1)))

    for element in elements:
        first_of_section = element.section_title != current_section
        if first_of_section:
            close_section(len(rows))
            current_section, section_start, section_total = element.section_title, len(rows), Decimal("0")
        section_total += element.weight or Decimal("0")
        descriptors = element.level_descriptors or {}
        row = [
            # The objective is printed once and spanned down its rows (as in the workbook).
            Paragraph(element.section_title if first_of_section else "", st["cellb"]),
            Paragraph(element.kpa_description or "", st["cell"]),
            Paragraph(element.kpi_title or "", st["cell"]),
            Paragraph(element.metric or "", st["cell"]),
            Paragraph(_fmt_weight(element.weight), st["cell"]),
        ] + [Paragraph(str(descriptors.get(level, "")), st["cell"]) for level in LEVELS]
        if stage == "final":
            row += [
                Paragraph("" if element.final_rating is None else str(element.final_rating), st["cellb"]),
                Paragraph("" if element.score is None else f"{element.score:.2f}", st["cellb"]),
            ]
        rows.append(row)
    close_section(len(rows))

    total_weight = agreement.total_weight
    total_row = ["", "", Paragraph("TOTAL", st["cellb"]), "", Paragraph(_fmt_weight(total_weight), st["cellb"])]
    total_row += [""] * (len(head_row) - 5 - (2 if stage == "final" else 0))
    if stage == "final":
        total_row += [
            "", Paragraph("" if agreement.final_score is None else f"{agreement.final_score:.2f}", st["cellb"])
        ]
    rows.append(total_row)

    widths = [26 * mm, 38 * mm, 46 * mm, 16 * mm, 13 * mm] + [26 * mm] * 5
    if stage == "final":
        widths += [12 * mm, 12 * mm]
    table = Table(rows, colWidths=widths, repeatRows=1)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#999999")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3864")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("BACKGROUND", (0, len(rows) - 1), (-1, len(rows) - 1), colors.HexColor("#dbe5f1")),
    ]
    style += [("BACKGROUND", (0, r), (-1, r), colors.HexColor("#eef2f8")) for r in subtotal_rows]
    style += spans
    table.setStyle(TableStyle(style))
    story.append(table)

    pdp_items = list(agreement.pdp_items.all())
    if pdp_items:
        pdp_rows = [[Paragraph("Business process", st["head"]), Paragraph("Courses / Training / Certificate", st["head"])]]
        pdp_rows += [
            [Paragraph(i.business_process, st["cell"]), Paragraph(i.course_or_training, st["cell"])] for i in pdp_items
        ]
        pdp_table = Table(pdp_rows, colWidths=[90 * mm, 130 * mm])
        pdp_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#999999")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3864")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story += [Paragraph("Personal Development Plan", st["h2"]), pdp_table]

    signatures = list(agreement.signatures.filter(stage=stage, revision=agreement.revision).order_by("signed_at"))
    sig_rows = [[Paragraph("Signatory", st["head"]), Paragraph("Name", st["head"]),
                 Paragraph("Signed", st["head"]), Paragraph("Method", st["head"])]]
    by_role = {s.role: s for s in signatures}
    for role, who in (("employee", employee), ("head", agreement.head)):
        signature = by_role.get(role)
        label = "Individual" if role == "employee" else "Manager (Head / executive)"
        if signature is None:
            name = f"{who.first_name} {who.last_name}" if who else "—"
            sig_rows.append([Paragraph(label, st["cellb"]), Paragraph(name, st["cell"]),
                             Paragraph("— not yet signed —", st["cell"]), Paragraph("", st["cell"])])
        else:
            name = f"{signature.signer.first_name} {signature.signer.last_name}"
            if signature.acting_for_id:
                name += f" (acting for {signature.acting_for.first_name} {signature.acting_for.last_name})"
            sig_rows.append([
                Paragraph(label, st["cellb"]), Paragraph(name, st["cell"]),
                Paragraph(f"{signature.signed_at:%Y-%m-%d %H:%M} SAST", st["cell"]),
                Paragraph(signature.get_method_display(), st["cell"]),
            ])
    sig_table = Table(sig_rows, colWidths=[45 * mm, 90 * mm, 45 * mm, 45 * mm])
    sig_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#999999")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3864")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(KeepTogether([Paragraph("Signatures", st["h2"]), sig_table]))
    story.append(Paragraph(
        "Signed electronically in the Sentech HCM. Each signature is bound to the SHA-256 hash of this exact "
        "document; the signature trail (who, when, how identity was proven) is held in the system's audit log.",
        st["sub"],
    ))

    doc.build(story)
    return buffer.getvalue()
