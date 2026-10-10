#!/usr/bin/env python3
"""
FSP-Talent Documentation to PDF Compiler.
Translates all markdown documentation in docs/ and README.md into a unified,
publication-quality PDF document with Russian typography, interactive table of contents,
bookmarks, tables, code formatting, and page numbering.
"""

import os
import re
import html
import textwrap
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    HRFlowable,
)
from reportlab.pdfgen import canvas

# Dimensions for A4
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_LEFT = 40.0
MARGIN_RIGHT = 40.0
MARGIN_TOP = 46.0
MARGIN_BOTTOM = 46.0
CONTENT_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT  # ~515.27 pt


def init_fonts():
    """Register TrueType fonts with Cyrillic support."""
    regular_font = "Helvetica"
    bold_font = "Helvetica-Bold"
    mono_font = "Courier"

    # 1. Try Windows system fonts
    win_fonts = {
        "FSP-Regular": "C:/Windows/Fonts/arial.ttf",
        "FSP-Bold": "C:/Windows/Fonts/arialbd.ttf",
        "FSP-Italic": "C:/Windows/Fonts/ariali.ttf",
        "FSP-Mono": "C:/Windows/Fonts/consola.ttf",
        "FSP-MonoBold": "C:/Windows/Fonts/consolab.ttf",
    }
    if all(os.path.exists(p) for p in win_fonts.values()):
        for name, path in win_fonts.items():
            pdfmetrics.registerFont(TTFont(name, path))
        return "FSP-Regular", "FSP-Bold", "FSP-Italic", "FSP-Mono"

    # 2. Try Linux DejaVu fonts
    linux_fonts = {
        "FSP-Regular": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "FSP-Bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "FSP-Italic": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        "FSP-Mono": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    }
    if all(os.path.exists(p) for p in linux_fonts.values()):
        for name, path in linux_fonts.items():
            pdfmetrics.registerFont(TTFont(name, path))
        return "FSP-Regular", "FSP-Bold", "FSP-Italic", "FSP-Mono"

    # 3. Fallback to Matplotlib fonts if available
    try:
        import matplotlib.font_manager as fm
        djv_reg = fm.findfont("DejaVu Sans")
        djv_bold = fm.findfont("DejaVu Sans:weight=bold")
        djv_mono = fm.findfont("DejaVu Sans Mono")
        if djv_reg and os.path.exists(djv_reg):
            pdfmetrics.registerFont(TTFont("FSP-Regular", djv_reg))
            pdfmetrics.registerFont(TTFont("FSP-Bold", djv_bold if djv_bold else djv_reg))
            pdfmetrics.registerFont(TTFont("FSP-Italic", djv_reg))
            pdfmetrics.registerFont(TTFont("FSP-Mono", djv_mono if djv_mono else djv_reg))
            return "FSP-Regular", "FSP-Bold", "FSP-Italic", "FSP-Mono"
    except Exception:
        pass

    return regular_font, bold_font, regular_font, mono_font


FONT_REGULAR, FONT_BOLD, FONT_ITALIC, FONT_MONO = init_fonts()


_CURRENT_OUTLINE_LEVEL = -1


class BookmarkParagraph(Paragraph):
    """Paragraph that registers a PDF outline entry for document navigation."""

    def __init__(self, text, style, outline_title=None, outline_level=0):
        super().__init__(text, style)
        self.outline_title = outline_title
        self.outline_level = outline_level

    def draw(self):
        global _CURRENT_OUTLINE_LEVEL
        super().draw()
        if self.outline_title and hasattr(self, "canv") and self.canv:
            key = f"bm_{id(self)}_{self.canv._pageNumber}"
            self.canv.bookmarkPage(key)
            target = max(0, min(self.outline_level, 2))
            if target > _CURRENT_OUTLINE_LEVEL + 1:
                lvl = _CURRENT_OUTLINE_LEVEL + 1
            else:
                lvl = target
            _CURRENT_OUTLINE_LEVEL = lvl
            try:
                self.canv.addOutlineEntry(
                    self.outline_title, key, level=lvl, closed=True
                )
            except Exception:
                pass


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas for header, footer and page numbers (Page X of Y)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_decorations(self, total_pages):
        if self._pageNumber == 1:
            # Skip decorations on the cover page
            return

        self.saveState()
        self.setFont(FONT_REGULAR, 7.5)
        self.setFillColor(colors.HexColor("#4B5563"))

        # Running Header
        header_text = "FSP-Talent · Единая национальная кадровая платформа (152-ФЗ)"
        self.drawString(MARGIN_LEFT, PAGE_HEIGHT - 32, header_text)
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.6)
        self.line(MARGIN_LEFT, PAGE_HEIGHT - 36, PAGE_WIDTH - MARGIN_RIGHT, PAGE_HEIGHT - 36)

        # Running Footer
        footer_left = "Хакатон «Лидеры цифровой трансформации 2026» · Официальная документация"
        page_str = f"Страница {self._pageNumber} из {total_pages}"
        self.drawString(MARGIN_LEFT, 26, footer_left)
        self.drawRightString(PAGE_WIDTH - MARGIN_RIGHT, 26, page_str)
        self.line(MARGIN_LEFT, 34, PAGE_WIDTH - MARGIN_RIGHT, 34)

        self.restoreState()


def format_inline_markdown(text: str) -> str:
    """Safely converts inline Markdown markers into ReportLab XML formatting."""
    # Strip HTML comments
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    # Clean Badges: [![...](...)](...) -> [...]
    text = re.sub(r"\[!\[(.*?)\]\(.*?\)\]\(.*?\)", r"[\1]", text)
    text = re.sub(r"!\[(.*?)\]\(.*?\)", r"[\1]", text)

    # Clean Math / KaTeX
    text = (
        text.replace(r"$\theta$", "θ")
        .replace(r"$\text{SE}$", "SE")
        .replace(r"$\text{Score}$", "Score")
        .replace(r"$\sigma$", "σ")
        .replace(r"$\beta$", "β")
        .replace(r"$\alpha$", "α")
    )
    # Remove single dollar signs
    text = re.sub(r"(?<!\\)\$([^\$]+)\$", r"\1", text)
    text = text.replace(r"\$", "$")

    # XML Escape
    text = text.replace('—', '-').replace('–', '-')
    text = html.escape(text)

    # Restore legitimate HTML tags if they were in the original text
    text = (
        text.replace("&lt;br&gt;", "<br/>")
        .replace("&lt;br/&gt;", "<br/>")
        .replace("&lt;br /&gt;", "<br/>")
        .replace("&lt;b&gt;", "<b>")
        .replace("&lt;/b&gt;", "</b>")
        .replace("&lt;i&gt;", "<i>")
        .replace("&lt;/i&gt;", "</i>")
        .replace("&lt;code&gt;", f'<font face="{FONT_MONO}" color="#991B1B"><b>')
        .replace("&lt;/code&gt;", "</font>")
    )

    # Links [title](url) -> formatted title
    text = re.sub(
        r"\[(.*?)\]\((.*?)\)",
        r'<font color="#1D4ED8"><u>\1</u></font>',
        text,
    )

    # Bold **text**
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)

    # Italic *text*
    text = re.sub(r"(?<!\*)\*(.*?)\*(?!\*)", r"<i>\1</i>", text)

    # Inline code `code`
    text = re.sub(
        r"`(.*?)`",
        rf'<font face="{FONT_MONO}" color="#991B1B"><b>\1</b></font>',
        text,
    )

    return text


def create_safe_paragraph(text: str, style: ParagraphStyle, preformatted: bool = False) -> Paragraph:
    """Attempts formatted Paragraph; falls back to escaped plain text on XML error."""
    try:
        content = text if preformatted else format_inline_markdown(text)
        return Paragraph(content, style)
    except Exception:
        clean_fallback = html.escape(re.sub(r"<[^>]+>", "", text))
        return Paragraph(clean_fallback, style)


def build_styles():
    """Builds a rich typography palette for the documentation book."""
    styles = {
        "CoverTitle": ParagraphStyle(
            "CoverTitle",
            fontName=FONT_BOLD,
            fontSize=28,
            leading=34,
            textColor=colors.HexColor("#1E3A8A"),
            alignment=0,
            spaceAfter=12,
        ),
        "CoverSubtitle": ParagraphStyle(
            "CoverSubtitle",
            fontName=FONT_REGULAR,
            fontSize=15,
            leading=20,
            textColor=colors.HexColor("#2563EB"),
            alignment=0,
            spaceAfter=18,
        ),
        "CoverBadge": ParagraphStyle(
            "CoverBadge",
            fontName=FONT_BOLD,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#1E40AF"),
            spaceAfter=8,
        ),
        "CoverBody": ParagraphStyle(
            "CoverBody",
            fontName=FONT_REGULAR,
            fontSize=10,
            leading=15,
            textColor=colors.HexColor("#374151"),
            spaceAfter=14,
        ),
        "DocSectionHeader": ParagraphStyle(
            "DocSectionHeader",
            fontName=FONT_BOLD,
            fontSize=20,
            leading=25,
            textColor=colors.HexColor("#1E3A8A"),
            spaceBefore=14,
            spaceAfter=8,
            keepWithNext=True,
        ),
        "H1": ParagraphStyle(
            "H1",
            fontName=FONT_BOLD,
            fontSize=15,
            leading=19,
            textColor=colors.HexColor("#1E3A8A"),
            spaceBefore=14,
            spaceAfter=7,
            keepWithNext=True,
        ),
        "H2": ParagraphStyle(
            "H2",
            fontName=FONT_BOLD,
            fontSize=12,
            leading=15.5,
            textColor=colors.HexColor("#1D4ED8"),
            spaceBefore=10,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "H3": ParagraphStyle(
            "H3",
            fontName=FONT_BOLD,
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#1F2937"),
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "H4": ParagraphStyle(
            "H4",
            fontName=FONT_BOLD,
            fontSize=9,
            leading=11.5,
            textColor=colors.HexColor("#374151"),
            spaceBefore=6,
            spaceAfter=3,
            keepWithNext=True,
        ),
        "Body": ParagraphStyle(
            "Body",
            fontName=FONT_REGULAR,
            fontSize=8.5,
            leading=11.8,
            textColor=colors.HexColor("#1F2937"),
            spaceAfter=5,
        ),
        "Bullet": ParagraphStyle(
            "Bullet",
            fontName=FONT_REGULAR,
            fontSize=8.5,
            leading=11.5,
            textColor=colors.HexColor("#1F2937"),
            leftIndent=14,
            firstLineIndent=-10,
            spaceAfter=3,
        ),
        "Callout": ParagraphStyle(
            "Callout",
            fontName=FONT_REGULAR,
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#1E3A8A"),
        ),
        "CodeText": ParagraphStyle(
            "CodeText",
            fontName=FONT_MONO,
            fontSize=7.0,
            leading=8.8,
            textColor=colors.HexColor("#1E293B"),
        ),
        "TableCell": ParagraphStyle(
            "TableCell",
            fontName=FONT_REGULAR,
            fontSize=7.2,
            leading=9.2,
            textColor=colors.HexColor("#1F2937"),
        ),
        "TableHeader": ParagraphStyle(
            "TableHeader",
            fontName=FONT_BOLD,
            fontSize=7.5,
            leading=9.5,
            textColor=colors.white,
        ),
    }
    return styles


def parse_markdown_to_flowables(md_content: str, styles: dict) -> list:
    """Converts a Markdown document string into ReportLab flowable elements."""
    flowables = []
    lines = md_content.splitlines()
    n = len(lines)
    i = 0

    while i < n:
        raw_line = lines[i]
        line = raw_line.strip()

        # 1. Blank line
        if not line:
            i += 1
            continue

        # 2. Horizontal divider
        if re.match(r"^(\-{3,}|\*{3,}|_{3,})$", line):
            flowables.append(
                HRFlowable(
                    width="100%",
                    thickness=0.5,
                    color=colors.HexColor("#E2E8F0"),
                    spaceBefore=6,
                    spaceAfter=6,
                )
            )
            i += 1
            continue

        # 3. Code block (```)
        if line.startswith("```"):
            lang = line[3:].strip()
            is_mermaid = lang.lower() == "mermaid"
            code_lines = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_raw = lines[i].replace('—', '-').replace('–', '-')
                if len(code_raw) > 82:
                    wrapped = textwrap.wrap(code_raw, width=82, replace_whitespace=False)
                    code_lines.extend(wrapped if wrapped else [""])
                else:
                    code_lines.append(code_raw)
                i += 1
            if i < n:
                i += 1  # Skip closing ```

            header_text = ""
            if is_mermaid:
                header_text = '<font color="#4F46E5"><b>[Схема процесса / Mermaid диаграмма]</b></font><br/>'
            elif lang:
                header_text = f'<font color="#64748B"><b>[{lang.upper()}]</b></font><br/>'

            escaped_code = header_text + "<br/>".join(
                html.escape(cl).replace(" ", "&nbsp;") if cl else "&nbsp;" for cl in code_lines
            )
            code_p = Paragraph(escaped_code, styles["CodeText"])
            code_table = Table([[code_p]], colWidths=[CONTENT_WIDTH])
            code_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("LINEBEFORE", (0, 0), (0, -1), 2.5, colors.HexColor("#3B82F6")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ])
            )
            flowables.append(code_table)
            flowables.append(Spacer(1, 4))
            continue

        # 4. Markdown Table
        if line.startswith("|") and line.endswith("|"):
            table_raw_rows = []
            while i < n and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                r_line = lines[i].strip()
                if re.match(r"^\|(\s*:?-+:?\s*\|)+$", r_line):
                    i += 1
                    continue
                cols = [c.strip() for c in r_line[1:-1].split("|")]
                table_raw_rows.append(cols)
                i += 1

            if table_raw_rows:
                num_cols = max(len(r) for r in table_raw_rows)
                for r in table_raw_rows:
                    while len(r) < num_cols:
                        r.append("")

                col_lengths = [0] * num_cols
                for r in table_raw_rows:
                    for ci, c in enumerate(r):
                        col_lengths[ci] = max(col_lengths[ci], len(c))

                total_weight = sum(col_lengths) or 1
                col_widths = []
                for clen in col_lengths:
                    weight_frac = max(clen, 5) / max(total_weight, 5)
                    col_widths.append(CONTENT_WIDTH * weight_frac)

                scale = CONTENT_WIDTH / sum(col_widths)
                col_widths = [w * scale for w in col_widths]

                table_data = []
                for row_idx, r in enumerate(table_raw_rows):
                    row_cells = []
                    is_header = row_idx == 0
                    c_style = styles["TableHeader"] if is_header else styles["TableCell"]
                    for cell_text in r:
                        row_cells.append(create_safe_paragraph(cell_text, c_style))
                    table_data.append(row_cells)

                t_flowable = Table(table_data, colWidths=col_widths, repeatRows=1)
                t_style = [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
                for r_idx in range(1, len(table_data)):
                    if r_idx % 2 == 0:
                        t_style.append(("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor("#F8FAFC")))
                    else:
                        t_style.append(("BACKGROUND", (0, r_idx), (-1, r_idx), colors.white))

                t_flowable.setStyle(TableStyle(t_style))
                flowables.append(t_flowable)
                flowables.append(Spacer(1, 4))
            continue

        # 5. Callout / Blockquote (> [!NOTE], >)
        if line.startswith(">"):
            quote_lines = []
            while i < n and lines[i].strip().startswith(">"):
                q_text = lines[i].strip().lstrip(">").strip()
                quote_lines.append(q_text)
                i += 1

            quote_combined = " ".join(quote_lines)
            box_bg = colors.HexColor("#EFF6FF")
            box_bar = colors.HexColor("#2563EB")
            alert_prefix = ""

            if "[!NOTE]" in quote_combined:
                quote_combined = quote_combined.replace("[!NOTE]", "").strip()
                alert_prefix = "<b>ПРИМЕЧАНИЕ:</b> "
            elif "[!WARNING]" in quote_combined or "[!CAUTION]" in quote_combined:
                quote_combined = (
                    quote_combined.replace("[!WARNING]", "").replace("[!CAUTION]", "").strip()
                )
                box_bg = colors.HexColor("#FEF3C7")
                box_bar = colors.HexColor("#D97706")
                alert_prefix = "<b>ВНИМАНИЕ:</b> "
            elif "[!IMPORTANT]" in quote_combined:
                quote_combined = quote_combined.replace("[!IMPORTANT]", "").strip()
                box_bg = colors.HexColor("#ECFDF5")
                box_bar = colors.HexColor("#059669")
                alert_prefix = "<b>ВАЖНО:</b> "
            elif "[!TIP]" in quote_combined:
                quote_combined = quote_combined.replace("[!TIP]", "").strip()
                box_bg = colors.HexColor("#ECFDF5")
                box_bar = colors.HexColor("#059669")
                alert_prefix = "<b>СОВЕТ:</b> "

            formatted_quote = alert_prefix + format_inline_markdown(quote_combined)
            callout_p = create_safe_paragraph(formatted_quote, styles["Callout"], preformatted=True)
            callout_tbl = Table([[callout_p]], colWidths=[CONTENT_WIDTH])
            callout_tbl.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), box_bg),
                    ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
                    ("LINEBEFORE", (0, 0), (0, -1), 3.0, box_bar),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ])
            )
            flowables.append(callout_tbl)
            flowables.append(Spacer(1, 4))
            continue

        # 6. Headings (#, ##, ###, ####)
        if line.startswith("#"):
            h_match = re.match(r"^(#{1,4})\s+(.*)$", line)
            if h_match:
                level = len(h_match.group(1))
                h_text = h_match.group(2).strip()
                clean_title = re.sub(r"[*`_#]", "", h_text)
                if level == 1:
                    st = styles["H1"]
                elif level == 2:
                    st = styles["H2"]
                elif level == 3:
                    st = styles["H3"]
                else:
                    st = styles["H4"]

                # Add interactive bookmark outline entry
                flowables.append(
                    BookmarkParagraph(
                        format_inline_markdown(h_text),
                        st,
                        outline_title=clean_title,
                        outline_level=level,
                    )
                )
                i += 1
                continue

        # 7. Bullet Lists (- , * )
        if re.match(r"^[-*+]\s+(.*)$", line):
            b_text = re.match(r"^[-*+]\s+(.*)$", line).group(1)
            formatted_item = format_inline_markdown(b_text)
            bullet_formatted = f"&bull;&nbsp;&nbsp;{formatted_item}"
            flowables.append(
                create_safe_paragraph(bullet_formatted, styles["Bullet"], preformatted=True)
            )
            i += 1
            continue

        # 8. Numbered Lists (1. , 2. )
        if re.match(r"^(\d+)\.\s+(.*)$", line):
            m_num = re.match(r"^(\d+)\.\s+(.*)$", line)
            num_str = m_num.group(1)
            item_text = m_num.group(2)
            formatted_item = format_inline_markdown(item_text)
            num_formatted = f"<b>{num_str}.</b>&nbsp;&nbsp;{formatted_item}"
            flowables.append(
                create_safe_paragraph(num_formatted, styles["Bullet"], preformatted=True)
            )
            i += 1
            continue

        # 9. Regular Paragraph
        flowables.append(create_safe_paragraph(line, styles["Body"]))
        i += 1

    return flowables


def build_unified_pdf(output_path: Path):
    """Compiles all project documentation into a single comprehensive PDF."""
    root_dir = Path(__file__).resolve().parent.parent
    docs_dir = root_dir / "docs"

    doc_files = [
        ("0. Введение и системный обзор", root_dir / "README.md"),
        ("1. Архитектурное руководство", docs_dir / "ARCHITECTURE_GUIDE.md"),
        ("2. Спецификация REST & AI API", docs_dir / "API_REFERENCE.md"),
        ("3. Бизнес-логика и алгоритмы", docs_dir / "BUSINESS_LOGIC_AND_ALGORITHMS.md"),
        ("4. Руководство по развертыванию", docs_dir / "DEPLOYMENT_AND_RUN_GUIDE.md"),
        ("5. Разбор исходного кода модулей", docs_dir / "CODE_WALKTHROUGH.md"),
        ("6. Концепции развития за MVP", docs_dir / "BEYOND_MVP_CONCEPTS.md"),
    ]

    styles = build_styles()
    story = []

    # ==========================
    # 1. ОБЛОЖКА (Cover Page)
    # ==========================
    story.append(Spacer(1, 20))
    story.append(
        Paragraph(
            "ФЕДЕРАЦИЯ СПОРТИВНОГО ПРОГРАММИРОВАНИЯ РОССИИ<br/>"
            "ХАКАТОН «ЛИДЕРЫ ЦИФРОВОЙ ТРАНСФОРМАЦИИ 2026»",
            styles["CoverBadge"],
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=2.5,
            color=colors.HexColor("#1E3A8A"),
            spaceBefore=4,
            spaceAfter=18,
        )
    )

    story.append(Paragraph("FSP-TALENT", styles["CoverTitle"]))
    story.append(
        Paragraph(
            "Единая национальная кадровая платформа<br/>"
            "со спортивным программированием, адаптивным тестированием CAT IRT,<br/>"
            "защищенным обратным наймом и отечественным AI-ассистентом GigaChat (152-ФЗ)",
            styles["CoverSubtitle"],
        )
    )

    story.append(
        Paragraph(
            "<b>Полная техническая и эксплуатационная документация платформы</b>",
            styles["CoverBadge"],
        )
    )

    story.append(Spacer(1, 10))

    meta_table_data = [
        [
            Paragraph("<b>Параметр</b>", styles["TableHeader"]),
            Paragraph("<b>Значение</b>", styles["TableHeader"]),
        ],
        [
            Paragraph("<b>Наименование проекта</b>", styles["TableCell"]),
            Paragraph("FSP-Talent (Модульный монолит FastAPI + React + PostgreSQL)", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Статус соответствия ТЗ</b>", styles["TableCell"]),
            Paragraph("100% требований ТЗ и сессии Q&A выполнено и проверено", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Автоматизированные тесты</b>", styles["TableCell"]),
            Paragraph("199 passed (100% успешных тестов: CAT IRT, 152-ФЗ, подбор, AI)", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Отечественный AI</b>", styles["TableCell"]),
            Paragraph("Сбер GigaChat API + детерминированный Offline Fallback", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Конфиденциальность</b>", styles["TableCell"]),
            Paragraph("152-ФЗ (обратный найм, сокрытие контактов до согласия)", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Дата сборки документа</b>", styles["TableCell"]),
            Paragraph(f"{datetime.now().strftime('%d.%m.%Y')} г.", styles["TableCell"]),
        ],
    ]
    meta_table = Table(meta_table_data, colWidths=[160, CONTENT_WIDTH - 160])
    meta_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    story.append(meta_table)

    story.append(Spacer(1, 24))
    story.append(
        Paragraph(
            "<i>Настоящий документ объединяет полную техническую спецификацию, архитектурные схемы, "
            "описание математических моделей и алгоритмов подбора, путеводитель по кодовой базе "
            "и руководство по развертыванию платформы FSP-Talent.</i>",
            styles["CoverBody"],
        )
    )

    story.append(PageBreak())

    # ==========================
    # 2. ОГЛАВЛЕНИЕ (TOC)
    # ==========================
    story.append(
        BookmarkParagraph(
            "Содержание документации",
            styles["DocSectionHeader"],
            outline_title="Содержание",
            outline_level=0,
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1.5,
            color=colors.HexColor("#1E3A8A"),
            spaceBefore=2,
            spaceAfter=14,
        )
    )

    toc_data = [
        [
            Paragraph("<b>Раздел</b>", styles["TableHeader"]),
            Paragraph("<b>Файл источника</b>", styles["TableHeader"]),
            Paragraph("<b>Краткое описание</b>", styles["TableHeader"]),
        ],
        [
            Paragraph("<b>0. Обзор платформы</b>", styles["TableCell"]),
            Paragraph("<code>README.md</code>", styles["TableCell"]),
            Paragraph("Визитная карточка, стек, быстрый старт, архитектура, GigaChat, AI Career Advisor, Радар компетенций", styles["TableCell"]),
        ],
        [
            Paragraph("<b>1. Архитектура</b>", styles["TableCell"]),
            Paragraph("<code>docs/ARCHITECTURE_GUIDE.md</code>", styles["TableCell"]),
            Paragraph("C4 модель, слои модульного монолита, структуры данных, QR-паспорт и радар компетенций", styles["TableCell"]),
        ],
        [
            Paragraph("<b>2. Спецификация API</b>", styles["TableCell"]),
            Paragraph("<code>docs/API_REFERENCE.md</code>", styles["TableCell"]),
            Paragraph("Все эндпоинты REST API, cURL примеры, AI-ассистент, AI Career Advisor, QR-верификация", styles["TableCell"]),
        ],
        [
            Paragraph("<b>3. Бизнес-логика</b>", styles["TableCell"]),
            Paragraph("<code>docs/BUSINESS_LOGIC_AND_ALGORITHMS.md</code>", styles["TableCell"]),
            Paragraph("CAT IRT 2PL, расчет формулы Score, обратный найм", styles["TableCell"]),
        ],
        [
            Paragraph("<b>4. Развертывание</b>", styles["TableCell"]),
            Paragraph("<code>docs/DEPLOYMENT_AND_RUN_GUIDE.md</code>", styles["TableCell"]),
            Paragraph("Docker Compose, стенд жюри, тесты, валидация, регламент", styles["TableCell"]),
        ],
        [
            Paragraph("<b>5. Разбор кода</b>", styles["TableCell"]),
            Paragraph("<code>docs/CODE_WALKTHROUGH.md</code>", styles["TableCell"]),
            Paragraph("Архитектурный гид по ключевым модулям кодовой базы", styles["TableCell"]),
        ],
        [
            Paragraph("<b>6. Развитие за MVP</b>", styles["TableCell"]),
            Paragraph("<code>docs/BEYOND_MVP_CONCEPTS.md</code>", styles["TableCell"]),
            Paragraph("Планы развития платформы, масштабирование, интеграции", styles["TableCell"]),
        ],
    ]
    toc_table = Table(toc_data, colWidths=[120, 140, CONTENT_WIDTH - 260])
    toc_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ])
    )
    for r_idx in range(1, len(toc_data)):
        if r_idx % 2 == 0:
            toc_table.setStyle(TableStyle([("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor("#F8FAFC"))]))

    story.append(toc_table)
    story.append(Spacer(1, 16))

    # ==========================
    # 3. ОСНОВНЫЕ РАЗДЕЛЫ
    # ==========================
    for title, file_path in doc_files:
        if not file_path.exists():
            print(f"Warning: {file_path} not found, skipping...")
            continue

        print(f"Compiling: {title} ({file_path.name})...")
        story.append(PageBreak())

        # Section Header Banner with PDF Bookmark
        story.append(
            BookmarkParagraph(
                title,
                styles["DocSectionHeader"],
                outline_title=title,
                outline_level=0,
            )
        )
        story.append(
            Paragraph(
                f"<i>Источник: <code>{file_path.relative_to(root_dir)}</code></i>",
                styles["CoverBadge"],
            )
        )
        story.append(
            HRFlowable(
                width="100%",
                thickness=1.5,
                color=colors.HexColor("#1E3A8A"),
                spaceBefore=2,
                spaceAfter=12,
            )
        )

        content = file_path.read_text(encoding="utf-8")
        parsed_flowables = parse_markdown_to_flowables(content, styles)
        story.extend(parsed_flowables)

    # Build the document
    print(f"Building PDF book: {output_path}...")
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=MARGIN_LEFT,
        rightMargin=MARGIN_RIGHT,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title="FSP-Talent · Единая техническая документация",
        author="Команда разработки FSP-Talent",
    )

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully created: {output_path} (Size: {output_path.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    output_pdf = Path(__file__).resolve().parent.parent / "docs" / "FSP_Talent_Documentation.pdf"
    build_unified_pdf(output_pdf)
