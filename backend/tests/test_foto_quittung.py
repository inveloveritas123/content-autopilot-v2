"""Tests für die Foto-Rückmeldung (2026-08-17).

Hintergrund: `_process_photo` hatte sieben Ausgänge und keiner sprach mit dem
Nutzer — Louis' meistgenannte Lücke (15.08. und 17.08.2026: „Fotos bekommen
bis heute überhaupt keine Rückmeldung, weder bei Erfolg noch bei Fehler").

Diese Tests sichern beides ab: dass jeder Fall eine Antwort erzeugt, und —
wichtiger — dass die Antwort die WAHRHEIT sagt. Ein „Gespeichert" auf ein Bild,
aus dem nichts gelesen wurde, wäre die freundliche Falschauskunft, gegen die
die ganze Welle antritt.
"""

from tasks.telegram_task import _FOTO_FEHLERTEXTE, _foto_quittung

# ---------------------------------------------------------------------------
# Erfolgsfälle — die Quittung muss unterscheiden, was wirklich passiert ist
# ---------------------------------------------------------------------------


def test_text_erkannt_zeigt_auszug():
    """Fall 1: OCR hat getroffen → der Nutzer sieht, WAS erkannt wurde.

    Der Auszug ist der Punkt: nur so kann der Nutzer merken, dass die
    Erkennung danebenlag, statt es später im fertigen Post zu entdecken.
    """
    out = _foto_quittung(
        {"ocr_chars": 42, "content_text": "Umsatz plus 18 Prozent", "description": None},
        None,
    )
    assert "Umsatz plus 18 Prozent" in out
    assert "Text aus dem Bild" in out


def test_nur_beschreibung_ohne_text():
    """Fall 2: kein Text drauf, aber ein Bildinhalt — das ist kein Fehler."""
    out = _foto_quittung(
        {"ocr_chars": 0, "content_text": "", "description": "Team vor Whiteboard"},
        None,
    )
    assert "beschrieben" in out
    assert "nicht gefunden" not in out


def test_nichts_erkannt_wird_nicht_als_erfolg_verkauft():
    """⛔ Fall 3, der wichtigste: weder Text noch Beschreibung.

    Der Bot MUSS sagen, dass er nichts lesen konnte. Ein blosses
    „Gespeichert" wäre hier eine Falschauskunft — der Nutzer glaubte, sein
    Bild sei verwertet, und wunderte sich später über den Post.
    """
    out = _foto_quittung({"ocr_chars": 0, "content_text": "", "description": None}, None)
    assert "nicht gefunden" in out
    # Und er sagt, was jetzt hilft — eine Sackgasse wäre nur die halbe Antwort.
    assert "schreib mir" in out.lower()


def test_nichts_erkannt_mit_caption_erwaehnt_die_caption():
    """Wer eine Bildunterschrift mitschickt, soll wissen, dass sie zählt."""
    out = _foto_quittung({"ocr_chars": 0, "content_text": "", "description": None}, "unser Offsite")
    assert "Bildunterschrift" in out


def test_ocr_chars_ohne_inhalt_faellt_nicht_auf_fall_1():
    """Grenzfall: Zähler sagt „Text da", der Inhalt ist aber leer.

    Ohne diese Prüfung entstünde eine Quittung mit leerem Auszug —
    „Text gespeichert: ‚‛" — also sichtbarer Unsinn.
    """
    out = _foto_quittung({"ocr_chars": 17, "content_text": "   ", "description": None}, None)
    assert "nicht gefunden" in out


def test_quittung_beginnt_immer_mit_foto_symbol():
    """Wiedererkennbarkeit im Chat: alle vier Fälle sind sofort als Foto-Antwort lesbar."""
    faelle = [
        ({"ocr_chars": 5, "content_text": "abc", "description": None}, None),
        ({"ocr_chars": 0, "content_text": "", "description": "x"}, None),
        ({"ocr_chars": 0, "content_text": "", "description": None}, "caption"),
        ({"ocr_chars": 0, "content_text": "", "description": None}, None),
    ]
    for result, caption in faelle:
        assert _foto_quittung(result, caption).startswith("📸")


# ---------------------------------------------------------------------------
# Fehlerfälle — jeder Ausgang hat einen eigenen, handlungsfähigen Text
# ---------------------------------------------------------------------------


def test_jeder_fehlerpfad_hat_einen_text():
    """Die fünf Ausgänge von `_process_photo`, die schiefgehen können."""
    erwartet = {"no_photo_array", "no_file_id", "download_failed", "pipeline", "store_failed"}
    assert erwartet == set(_FOTO_FEHLERTEXTE)


def test_fehlertexte_sind_handlungsfaehig():
    """⛔ „Es hat nicht geklappt" ist wertlos, wenn der Nutzer nicht weiss, was nun.

    Jeder Text muss entweder einen nächsten Schritt nennen oder ehrlich sagen,
    dass der Fehler auf unserer Seite liegt.
    """
    for schluessel, text in _FOTO_FEHLERTEXTE.items():
        hat_handlung = any(
            wort in text.lower() for wort in ("nochmal", "versuch", "schreib", "probier", "hilft")
        )
        assert hat_handlung, f"{schluessel} nennt keinen naechsten Schritt: {text!r}"


def test_fehlertexte_ohne_technikjargon():
    """Der Empfänger ist Unternehmer, nicht Betreiber."""
    verboten = ("pipeline", "payload", "file_id", "exception", "error", "chunk", "ocr")
    for schluessel, text in _FOTO_FEHLERTEXTE.items():
        for wort in verboten:
            assert wort not in text.lower(), f"{schluessel} enthaelt Fachbegriff {wort!r}"


def test_fehlertexte_beginnen_mit_foto_symbol():
    for text in _FOTO_FEHLERTEXTE.values():
        assert text.startswith("📸")
