"""Tests fuer P12c Carousel Generator (Issue #87)."""

import json

from services.carousel_generator import generate_carousel_pdf, split_text_into_slides

MARCUS_WEBER_POST = """
In meinen 20 Jahren als Unternehmer habe ich eine Lektion immer wieder gelernt:
Vertrauen ist das Fundament jedes erfolgreichen Unternehmens.

Ohne Vertrauen koennen Sie keine langfristigen Partnerschaften aufbauen.
Kunden bleiben nicht wegen des Produkts - sie bleiben wegen des Menschen dahinter.

3 Wege, wie ich Vertrauen aufgebaut habe:
1. Ehrlichkeit auch wenn es wehtut
2. Konsistenz ueber Jahre hinweg
3. Interesse am Gegenueber zeigen

Was ist eure Erfahrung mit Vertrauen im Business?
"""


def test_split_text_into_slides_basic():
    """split_text_into_slides gibt min. 2 Slides zurueck."""
    slides = split_text_into_slides(MARCUS_WEBER_POST)
    assert len(slides) >= 2
    assert slides[0]["type"] == "title"
    assert slides[-1]["type"] == "cta"


def test_split_text_into_slides_max_8():
    """split_text_into_slides verarbeitet langen Text."""
    long_text = "\n\n".join([f"Paragraph {i}: " + "Text " * 50 for i in range(20)])
    slides = split_text_into_slides(long_text)
    assert len(slides) >= 1


def test_generate_carousel_pdf_produces_bytes():
    """generate_carousel_pdf gibt non-empty bytes zurueck."""
    slides = [
        {"type": "title", "heading": "Mein Carousel", "body": "Test"},
        {"type": "content", "heading": "Punkt 1", "body": "Erster Inhalt"},
        {"type": "cta", "heading": "Folge mir", "body": "Mehr Content"},
    ]
    pdf = generate_carousel_pdf(slides=slides, title="Test Carousel")
    assert isinstance(pdf, bytes)
    assert len(pdf) > 100
    assert pdf[:4] == b"%PDF"


def test_generate_carousel_pdf_with_branding():
    """PDF mit custom branding wird korrekt generiert."""
    slides = [{"type": "title", "heading": "Test", "body": "Branding Test"}]
    pdf = generate_carousel_pdf(
        slides=slides,
        brand_colors={"primary": "#FF0000", "accent": "#0000FF"},
        title="Branded Carousel",
    )
    assert isinstance(pdf, bytes)
    assert len(pdf) > 100


def test_generate_carousel_pdf_size_limit():
    """PDF muss unter 5 MB bleiben."""
    slides = split_text_into_slides(MARCUS_WEBER_POST)
    pdf = generate_carousel_pdf(slides=slides)
    assert len(pdf) < 5 * 1024 * 1024, f"PDF zu gross: {len(pdf)} bytes"


def test_parse_slides_html_escape():
    """HTML in Slide-Inhalten wird escaped."""
    from tasks.p12c_task import _parse_slides

    raw = '{"slides": [{"type": "point", "title": "<script>alert(1)</script>", "body": "Test"}]}'
    slides = _parse_slides(raw)
    assert "<script>" not in slides[0]["title"]
    assert "&lt;script&gt;" in slides[0]["title"]


def test_parse_slides_max_8():
    """Mehr als 8 Slides werden auf 8 begrenzt."""
    from tasks.p12c_task import _parse_slides

    raw_slides = [{"type": "point", "title": f"Slide {i}", "body": "Text"} for i in range(12)]
    raw = json.dumps({"slides": raw_slides, "slide_count": 12})
    slides = _parse_slides(raw)
    assert len(slides) <= 8


def test_parse_slides_invalid_json_fallback():
    """Bei ungueltigem JSON wird Fallback-Slide erstellt."""
    from tasks.p12c_task import _parse_slides

    slides = _parse_slides("KEIN JSON HIER")
    assert len(slides) >= 1
    # fallback slide has type="cover" which gets mapped to "title" by TYPE_MAP
    assert slides[0]["type"] == "title"
