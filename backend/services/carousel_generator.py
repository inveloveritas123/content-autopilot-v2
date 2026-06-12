"""Carousel PDF Generator — LinkedIn Document Posts.

Generates multi-page PDFs optimized for LinkedIn carousel posts.
Each page = one slide (1080x1080px or 1080x1350px).
"""

import io
import logging
import textwrap

from reportlab.lib.colors import HexColor, white
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

# LinkedIn optimal: 1080x1080 (square) or 1080x1350 (portrait)
SLIDE_W = 1080
SLIDE_H = 1080
PAGE_SIZE = (SLIDE_W, SLIDE_H)

# ZB Brand defaults
ZB_COLORS = {
    "primary": "#0F766E",
    "accent": "#F59E0B",
    "bg": "#FFFFFF",
    "text": "#1A1A2E",
    "text_light": "#6B7280",
}


def _hex(color: str) -> HexColor:
    return HexColor(color)


def _wrap_text(text: str, max_chars: int = 40) -> list[str]:
    return textwrap.wrap(text, width=max_chars)


def generate_carousel_pdf(
    slides: list[dict],
    brand_colors: dict | None = None,
    title: str = "Carousel",
) -> bytes:
    """Generate a multi-slide PDF for LinkedIn carousel post.

    Args:
        slides: List of slide dicts with keys:
            - type: "title" | "content" | "quote" | "cta"
            - heading: str (optional)
            - body: str
            - footer: str (optional)
            - number: int (optional, slide number)
        brand_colors: Override colors (primary, accent, bg, text)
        title: PDF title metadata

    Returns:
        PDF as bytes
    """
    colors = {**ZB_COLORS, **(brand_colors or {})}
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE_SIZE)
    c.setTitle(title)

    for i, slide in enumerate(slides):
        slide_type = slide.get("type", "content")

        if slide_type == "title":
            _draw_title_slide(c, slide, colors)
        elif slide_type == "quote":
            _draw_quote_slide(c, slide, colors)
        elif slide_type == "cta":
            _draw_cta_slide(c, slide, colors)
        else:
            _draw_content_slide(c, slide, colors, i + 1, len(slides))

        c.showPage()

    c.save()
    buf.seek(0)
    return buf.read()


def _draw_title_slide(c, slide, colors):
    """Full-color title slide."""
    c.setFillColor(_hex(colors["primary"]))
    c.rect(0, 0, SLIDE_W, SLIDE_H, fill=1, stroke=0)

    # Accent bar
    c.setFillColor(_hex(colors["accent"]))
    c.rect(80, SLIDE_H - 200, 120, 6, fill=1, stroke=0)

    # Title
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 52)
    lines = _wrap_text(slide.get("heading", slide.get("body", "")), 25)
    y = SLIDE_H - 260
    for line in lines[:4]:
        c.drawString(80, y, line)
        y -= 64

    # Subtitle
    if slide.get("footer"):
        c.setFont("Helvetica", 24)
        c.setFillColor(HexColor("#FFFFFF99"))
        c.drawString(80, 120, slide["footer"])


def _draw_content_slide(c, slide, colors, num, total):
    """Standard content slide with heading + body."""
    # White background
    c.setFillColor(_hex(colors["bg"]))
    c.rect(0, 0, SLIDE_W, SLIDE_H, fill=1, stroke=0)

    # Top accent bar
    c.setFillColor(_hex(colors["primary"]))
    c.rect(0, SLIDE_H - 8, SLIDE_W, 8, fill=1, stroke=0)

    # Slide number
    c.setFillColor(_hex(colors["accent"]))
    c.setFont("Helvetica-Bold", 72)
    c.drawString(80, SLIDE_H - 140, f"{num:02d}")

    # Heading
    if slide.get("heading"):
        c.setFillColor(_hex(colors["text"]))
        c.setFont("Helvetica-Bold", 36)
        lines = _wrap_text(slide["heading"], 30)
        y = SLIDE_H - 220
        for line in lines[:2]:
            c.drawString(80, y, line)
            y -= 44

    # Body text
    c.setFillColor(_hex(colors["text"]))
    c.setFont("Helvetica", 26)
    body_lines = _wrap_text(slide.get("body", ""), 42)
    y = SLIDE_H - 360 if slide.get("heading") else SLIDE_H - 220
    for line in body_lines[:12]:
        c.drawString(80, y, line)
        y -= 36

    # Footer / page indicator
    c.setFillColor(_hex(colors["text_light"]))
    c.setFont("Helvetica", 18)
    c.drawString(80, 60, f"{num}/{total}")


def _draw_quote_slide(c, slide, colors):
    """Large quote with accent color."""
    c.setFillColor(_hex(colors["bg"]))
    c.rect(0, 0, SLIDE_W, SLIDE_H, fill=1, stroke=0)

    # Large opening quote mark
    c.setFillColor(_hex(colors["accent"]))
    c.setFont("Helvetica-Bold", 180)
    c.drawString(60, SLIDE_H - 220, "\u201c")

    # Quote text
    c.setFillColor(_hex(colors["text"]))
    c.setFont("Helvetica-Bold", 32)
    lines = _wrap_text(slide.get("body", ""), 35)
    y = SLIDE_H - 320
    for line in lines[:8]:
        c.drawString(100, y, line)
        y -= 42

    # Attribution
    if slide.get("footer"):
        c.setFillColor(_hex(colors["primary"]))
        c.setFont("Helvetica", 22)
        c.drawString(100, 100, f"— {slide['footer']}")


def _draw_cta_slide(c, slide, colors):
    """Call-to-action final slide."""
    c.setFillColor(_hex(colors["primary"]))
    c.rect(0, 0, SLIDE_W, SLIDE_H, fill=1, stroke=0)

    # CTA text
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 44)
    lines = _wrap_text(slide.get("heading", slide.get("body", "Folge fuer mehr!")), 25)
    y = SLIDE_H // 2 + 60
    for line in lines[:3]:
        c.drawString(80, y, line)
        y -= 56

    # Sub-CTA
    if slide.get("body") and slide.get("heading"):
        c.setFont("Helvetica", 26)
        c.setFillColor(HexColor("#FFFFFFCC"))
        sub_lines = _wrap_text(slide["body"], 35)
        y -= 20
        for line in sub_lines[:3]:
            c.drawString(80, y, line)
            y -= 34

    # Accent button shape
    c.setFillColor(_hex(colors["accent"]))
    c.roundRect(80, 120, 300, 60, 10, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(130, 140, slide.get("footer", "Mehr erfahren"))


def split_text_into_slides(text: str, max_chars_per_slide: int = 400) -> list[dict]:
    """Split a long text into carousel slides automatically.

    Returns slide dicts ready for generate_carousel_pdf().
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    slides = []
    # First paragraph = title slide
    slides.append({"type": "title", "heading": paragraphs[0][:120]})

    # Middle paragraphs = content slides
    for p in paragraphs[1:]:
        if len(p) > max_chars_per_slide:
            chunks = textwrap.wrap(p, width=max_chars_per_slide)
            for chunk in chunks:
                slides.append({"type": "content", "body": chunk})
        else:
            slides.append({"type": "content", "body": p})

    # CTA slide
    slides.append(
        {
            "type": "cta",
            "heading": "Hat dir das geholfen?",
            "body": "Folge mir fuer mehr Content wie diesen.",
            "footer": "Folgen",
        }
    )

    return slides
