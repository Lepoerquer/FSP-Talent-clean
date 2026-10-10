"""PDF Generation Service for standardized FSP-Talent Candidate Profiles.

Creates a compliant, beautifully formatted PDF report containing:
- Header: «FSP-Talent Профиль кандидата»
- ФИО (Full Name)
- Confirmed Category («Backend · Middle»)
- CAT IRT Percentile rank
- FSP Federation ID & Verified status
- Skills stack with verification source (ASSESSMENT, FSP, RESUME, CLAIMED)
- Questionnaire: experience, roles, soft skills
- Salary expectations & work preferences
- QR code linking to the public verification endpoint (GET /api/v1/verify/candidates/{id})
"""

import io
import os
from datetime import datetime, timezone
from xml.sax.saxutils import escape

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

try:
    from backend.app.core.config import settings
except ImportError:
    from app.core.config import settings
from backend.app.models.candidate import CandidateProfile

_FONTS_INITIALIZED = False
_FONT_FAMILY = "Helvetica"
_FONT_FAMILY_BOLD = "Helvetica-Bold"


def _initialize_fonts() -> tuple[str, str]:
    """Finds and registers a TrueType font supporting Cyrillic."""
    global _FONTS_INITIALIZED, _FONT_FAMILY, _FONT_FAMILY_BOLD
    if _FONTS_INITIALIZED:
        return _FONT_FAMILY, _FONT_FAMILY_BOLD

    regular_font_path = None
    bold_font_path = None

    # 1. Try Matplotlib's bundled DejaVu Sans (universal cross-platform)
    try:
        import matplotlib.font_manager as fm
        regular_font_path = fm.findfont("DejaVu Sans")
        bold_font_path = fm.findfont("DejaVu Sans:weight=bold")
    except Exception:
        pass

    # 2. Windows standard system fonts
    if not regular_font_path or not os.path.exists(regular_font_path):
        win_regular = "C:\\Windows\\Fonts\\arial.ttf"
        win_bold = "C:\\Windows\\Fonts\\arialbd.ttf"
        if os.path.exists(win_regular):
            regular_font_path = win_regular
            bold_font_path = win_bold if os.path.exists(win_bold) else win_regular

    # 3. Linux common paths
    if not regular_font_path or not os.path.exists(regular_font_path):
        linux_candidates = [
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ]
        for reg, bld in linux_candidates:
            if os.path.exists(reg):
                regular_font_path = reg
                bold_font_path = bld if os.path.exists(bld) else reg
                break

    if regular_font_path and os.path.exists(regular_font_path):
        try:
            pdfmetrics.registerFont(TTFont("FSPFont", regular_font_path))
            if bold_font_path and os.path.exists(bold_font_path):
                pdfmetrics.registerFont(TTFont("FSPFont-Bold", bold_font_path))
            else:
                pdfmetrics.registerFont(TTFont("FSPFont-Bold", regular_font_path))
            _FONT_FAMILY = "FSPFont"
            _FONT_FAMILY_BOLD = "FSPFont-Bold"
        except Exception:
            _FONT_FAMILY = "Helvetica"
            _FONT_FAMILY_BOLD = "Helvetica-Bold"
    else:
        _FONT_FAMILY = "Helvetica"
        _FONT_FAMILY_BOLD = "Helvetica-Bold"

    _FONTS_INITIALIZED = True
    return _FONT_FAMILY, _FONT_FAMILY_BOLD


def _generate_qr_image(data_url: str, size_pt: float = 85.0) -> Image:
    """Generates a QR code image as a ReportLab Flowable."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=1,
    )
    qr.add_data(data_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1E3A8A", back_color="white")

    img_buffer = io.BytesIO()
    img.save(img_buffer, format="PNG")
    img_buffer.seek(0)

    return Image(img_buffer, width=size_pt, height=size_pt)


def generate_candidate_qr_png(candidate_id: str, base_url: str | None = None) -> bytes:
    """Generates PNG bytes of the candidate verification QR code pointing to public verify endpoint."""
    effective_base_url = (base_url or settings.PUBLIC_BASE_URL).rstrip("/")
    verification_url = f"{effective_base_url}/verify/candidates/{candidate_id}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(verification_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0A006B", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _map_source_name(source: str | None) -> str:
    """Human-readable description for skill confirmation sources."""
    if not source:
        return "Заявлено кандидатом"
    clean = source.upper()
    if clean in ("ASSESSMENT", "TEST"):
        return "Тестирование CAT (IRT)"
    if clean == "FSP":
        return "Соревнования ФСП"
    if clean == "RESUME":
        return "Опыт из резюме"
    return "Заявлено кандидатом"


def generate_candidate_pdf(candidate: CandidateProfile, base_url: str | None = None) -> bytes:
    """Builds and returns bytes for standardized candidate PDF profile."""
    font_reg, font_bold = _initialize_fonts()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    # Custom typography styles
    title_style = ParagraphStyle(
        "FSPTitle",
        fontName=font_bold,
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1E3A8A"),
    )
    subtitle_style = ParagraphStyle(
        "FSPSubtitle",
        fontName=font_reg,
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#4B5563"),
    )
    name_style = ParagraphStyle(
        "FSPName",
        fontName=font_bold,
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#111827"),
    )
    meta_style = ParagraphStyle(
        "FSPMeta",
        fontName=font_reg,
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#4B5563"),
    )
    section_h2 = ParagraphStyle(
        "FSPSectionH2",
        fontName=font_bold,
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=10,
        spaceAfter=6,
    )
    table_head = ParagraphStyle(
        "FSPTableHead",
        fontName=font_bold,
        fontSize=9,
        leading=12,
        textColor=colors.white,
    )
    table_cell = ParagraphStyle(
        "FSPTableCell",
        fontName=font_reg,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#1F2937"),
    )
    table_cell_bold = ParagraphStyle(
        "FSPTableCellBold",
        fontName=font_bold,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#1F2937"),
    )
    badge_green = ParagraphStyle(
        "FSPBadgeGreen",
        fontName=font_bold,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#065F46"),
    )
    badge_blue = ParagraphStyle(
        "FSPBadgeBlue",
        fontName=font_bold,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#1E40AF"),
    )
    qr_caption = ParagraphStyle(
        "FSPQRCaption",
        fontName=font_reg,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#6B7280"),
        alignment=1,  # Center
    )
    footer_style = ParagraphStyle(
        "FSPFooter",
        fontName=font_reg,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#9CA3AF"),
        alignment=1,
    )

    story = []

    # 1. Verification QR code URL (public web verification page)
    effective_base_url = (base_url or settings.PUBLIC_BASE_URL).rstrip("/")
    verification_url = f"{effective_base_url}/verify/candidates/{candidate.id}"
    qr_flowable = _generate_qr_image(verification_url, size_pt=80.0)

    # 2. Header Grid (Branding Title + QR Code box)
    cand_name = f"{candidate.first_name or ''} {candidate.last_name or ''}".strip()
    if not cand_name:
        cand_name = f"Кандидат #{candidate.id[:8]}"

    # Only a grade confirmed by the test is a category; a declared grade is shown as such
    if candidate.confirmed_grade:
        category = candidate.confirmed_category or f"{candidate.confirmed_specialization or '—'} · {candidate.confirmed_grade}"
    else:
        declared = getattr(candidate, "declared_grade", None)
        category = "Грейд не подтверждён" + (f" (заявлен {declared})" if declared else "")

    work_info = f"Город: {candidate.city or 'Не указан'}  |  Формат: {candidate.work_format or 'REMOTE'}"

    header_data = [
        [
            [
                Paragraph("FSP-Talent Профиль кандидата", title_style),
                Spacer(1, 4),
                Paragraph("Стандартизированный верифицированный профиль компетенций", subtitle_style),
                Spacer(1, 10),
                Paragraph(cand_name, name_style),
                Spacer(1, 3),
                Paragraph(f"<b>Подтвержденная категория:</b> {category}", meta_style),
                Spacer(1, 2),
                Paragraph(work_info, meta_style),
            ],
            [
                qr_flowable,
                Spacer(1, 3),
                Paragraph("Онлайн-проверка подлинности", qr_caption),
            ],
        ]
    ]

    header_table = Table(header_data, colWidths=[420, 103])
    header_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ])
    )
    story.append(header_table)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563EB"), spaceAfter=12))

    # 3. Key Metrics Cards (2x2 Grid)
    # CAT Percentile
    cat_percentile = candidate.category_percentile
    cat_theta = candidate.last_theta if candidate.last_theta is not None else 0.0

    # FSP Status
    if candidate.is_fsp_verified:
        fsp_status_text = f"Верифицирован ({candidate.fsp_id or 'ID привязан'})"
        fsp_sub = f"Балл ФСП: {candidate.fsp_score:.2f} · Достижения подтверждены"
    elif candidate.fsp_id:
        fsp_status_text = f"ID: {candidate.fsp_id} (указан кандидатом)"
        fsp_sub = "Достижения из реестра ФСП ещё не привязаны"
    else:
        fsp_status_text = "Не привязан"
        fsp_sub = "Спортивный профиль ФСП не подключен"

    # Salary expectations
    if candidate.desired_salary_min:
        type_label = " (до вычета НДФЛ / Гросс)" if (getattr(candidate, "is_gross", False) or getattr(candidate, "salary_type", "NET") == "GROSS") else " (на руки / Нетто)"
        salary_text = f"от {candidate.desired_salary_min:,} ₽{type_label}".replace(",", " ")
    else:
        salary_text = "По договорённости"

    metrics_data = [
        [
            [
                Paragraph("<b>ПОДТВЕРЖДЕННАЯ КАТЕГОРИЯ</b>", meta_style),
                Spacer(1, 2),
                Paragraph(f"<b>{category}</b>", badge_blue),
                Paragraph(f"Статус: {candidate.status or 'ACTIVELY_SEARCHING'}", meta_style),
            ],
            [
                Paragraph("<b>ПРОЦЕНТИЛЬ CAT (IRT ТЕСТ)</b>", meta_style),
                Spacer(1, 2),
                Paragraph(f"<b>{cat_percentile}-й процентиль</b>" if cat_percentile is not None
                          else "<b>Тест не пройден</b>", badge_green if cat_percentile is not None else meta_style),
                Paragraph(f"Латентный уровень θ = {cat_theta:.2f}" if cat_percentile is not None else "Оценка появится после теста",
                          meta_style),
            ],
        ],
        [
            [
                Paragraph("<b>СТАТУС В РЕЕСТРЕ ФСП</b>", meta_style),
                Spacer(1, 2),
                Paragraph(f"<b>{fsp_status_text}</b>", badge_blue if candidate.is_fsp_verified else meta_style),
                Paragraph(fsp_sub, meta_style),
            ],
            [
                Paragraph("<b>ЗАРПЛАТНЫЕ ОЖИДАНИЯ</b>", meta_style),
                Spacer(1, 2),
                Paragraph(f"<b>{salary_text}</b>", badge_green),
                Paragraph(f"Формат: {candidate.work_format or 'REMOTE'}", meta_style),
            ],
        ],
    ]

    metrics_table = Table(metrics_data, colWidths=[260, 263])
    metrics_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ])
    )
    story.append(metrics_table)
    story.append(Spacer(1, 14))

    # 4. Verified Skills Stack Section
    story.append(Paragraph("Подтвержденный стек технологий и навыков", section_h2))

    skills_rows = [
        [
            Paragraph("Технология / Навык", table_head),
            Paragraph("Источник подтверждения", table_head),
            Paragraph("Вес / Статус", table_head),
        ]
    ]

    cand_skills = list(candidate.skills or [])
    if cand_skills:
        for s in cand_skills:
            skill_name = (s.skill.name if s.skill else None) or "Навык"
            source_desc = _map_source_name(s.confirmation_source)
            is_verified = (s.confirmation_source or "").upper() in ("ASSESSMENT", "TEST", "FSP")
            status_text = "Верифицирован (1.0)" if is_verified else f"Подтверждение ({s.weight:.1f})"

            skills_rows.append([
                Paragraph(f"<b>{skill_name}</b>", table_cell_bold),
                Paragraph(source_desc, table_cell),
                Paragraph(status_text, badge_green if is_verified else table_cell),
            ])
    else:
        # Default placeholder if candidate has no specific skills in DB
        skills_rows.append([
            Paragraph("Базовые компетенции специализации", table_cell_bold),
            Paragraph("Первичное профилирование", table_cell),
            Paragraph("На верификации", table_cell),
        ])

    skills_table = Table(skills_rows, colWidths=[180, 223, 120])
    skills_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    story.append(skills_table)
    story.append(Spacer(1, 14))

    # 5. Questionnaire filled in by the candidate (self-reported, shown as such)
    questionnaire = [
        ("Опыт работы", f"{candidate.experience_years:g} лет" if candidate.experience_years is not None else None),
        ("Роли", candidate.roles),
        ("Soft-skills", candidate.soft_skills),
        ("О себе", candidate.about_me),
    ]
    questionnaire = [(label, value) for label, value in questionnaire if value]
    if questionnaire:
        story.append(Paragraph("Анкета кандидата (со слов кандидата)", section_h2))
        q_table = Table(
            [[Paragraph(f"<b>{label}</b>", table_cell_bold), Paragraph(escape(str(value)), table_cell)]
             for label, value in questionnaire],
            colWidths=[140, 383],
        )
        q_table.setStyle(
            TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ])
        )
        story.append(q_table)
        story.append(Spacer(1, 14))

    # 6. FSP Achievements section (if any)
    achievements = list(candidate.fsp_achievements or [])
    if achievements:
        story.append(Paragraph("Спортивные достижения в Федерации (ФСП)", section_h2))
        fsp_rows = [
            [
                Paragraph("Мероприятие / Дисциплина", table_head),
                Paragraph("Уровень соревнований", table_head),
                Paragraph("Результат / Разряд", table_head),
            ]
        ]
        for ach in achievements:
            fsp_rows.append([
                Paragraph(f"<b>{ach.event_name}</b><br/>{ach.discipline}", table_cell),
                Paragraph(ach.level or "Всероссийский", table_cell),
                Paragraph(f"<b>{ach.result}</b>" + (f" ({ach.sport_category})" if ach.sport_category else ""), badge_blue),
            ])

        fsp_table = Table(fsp_rows, colWidths=[240, 143, 140])
        fsp_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ])
        )
        story.append(fsp_table)
        story.append(Spacer(1, 14))

    # 7. Verification and 152-FZ Footer Notice
    now_str = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    footer_data = [
        [
            Paragraph(
                f"<b>FSP-Talent Verification ID:</b> {candidate.id}<br/>"
                "Актуальную категорию и статус проверки можно сверить по QR-коду.<br/>"
                "Обработка и передача данных осуществляется в строгом соответствии с 152-ФЗ РФ.<br/>"
                f"<i>Дата формирования отчета: {now_str}</i>",
                footer_style,
            )
        ]
    ]
    footer_table = Table(footer_data, colWidths=[523])
    footer_table.setStyle(
        TableStyle([
            ("LINEABOVE", (0, 0), (-1, -1), 1, colors.HexColor("#E2E8F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ])
    )
    story.append(footer_table)

    # Build PDF
    doc.build(story)
    return buffer.getvalue()
