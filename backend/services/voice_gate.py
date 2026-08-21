"""
Voice-Consistency-Gate — quantitativer Post-hoc-Check gegen ein Voice-Profil.

Portiert aus persona-forge (``src/persona_forge/style_gate.py`` + ``metrics.py`` +
``blocklist.py``) fuer den content-autopilot (W5-Vorarbeit; die Verdrahtung ans
Quality-Gate/``session_post_task`` erfolgt separat in W5 — dieses Modul liefert
nur die pruefbare Funktion).

Doktrin (llm_foo/content-creation/QUANTITATIVE_STYLE_GUARDRAILS.md +
ANTI_LLM_VOICE_AND_PERSONAL_BRAND.md):
  - Verifikation passiert NACH der Generierung, nie als harte Prompt-Constraint
    ("schreibe mit MTLD 85" wird verfehlt — LLMs undershooten Zahl-Constraints,
    Erfolgsrate 0.08-0.41). Die Korridore sind Mess-Latte, kein Befehl.
  - MATTR (Moving-Average TTR, Fenster ~50) ist das laengen-robuste Maß fuer
    KURZE Social-Posts — MTLD/Burrows's-Delta brauchen mehr Text als ein Post
    typischerweise hat, deshalb hier bewusst NICHT implementiert (kein
    Referenzkorpus-Fetch fuer Delta vorhanden; das ist die naechste Ausbaustufe).
  - Satzlaengen-VARIANZ zaehlt mehr als der Mittelwert (Monotonie-Indikator).
  - Der Anti-KI-Blocklist-Check ist ein Generierungs-Artefakt-Scan ("du hast
    diese Phrase geschrieben"), NIEMALS ein Detektor-Score ("ist das KI?" —
    dafuer 61% False-Positive bei Nicht-Muttersprachlern, siehe Doktrin).
  - Korridore werden aus dem P03-Voice-Profile-Dict gelesen (kanonisches
    Schema: ``satzarchitektur``, ``wortschatz``, ``vermeidungsprofil``). Das
    Schema ist bei content-autopilot ueberwiegend DESKRIPTIV (Strings/Listen,
    keine numerischen mean_min/max-Baender wie bei persona-forge) — jede
    numerische Erwartung wird deshalb best-effort aus dem vorhandenen Feld
    abgeleitet; fehlt ein Feld, wird die zugehoerige Pruefung uebersprungen
    (robust gegen ein leeres/minimales voice_profile — kein Crash).

Pure stdlib. Kein LLM, kein Netzwerk, kein DB-Zugriff — deterministisch testbar.
"""

from __future__ import annotations

import re
from statistics import mean, pstdev
from typing import Any

# ---------------------------------------------------------------------------
# Anti-KI-Blocklist (DE, 5 Kategorien) — aus
# llm_foo/content-creation/ANTI_LLM_VOICE_AND_PERSONAL_BRAND.md §2.
# Generierungs-Artefakt-Liste, kein Detektor: meldet konkrete Phrasen-Treffer.
# ---------------------------------------------------------------------------

ANTI_KI_OPENERS_CLOSERS: list[str] = [
    "Klar! Hier ist",
    "Selbstverständlich! Ich helfe gerne",
    "Tolle Frage!",
    "Ich hoffe, das hilft!",
    "Lassen Sie mich wissen, wenn Sie noch etwas brauchen",
]

ANTI_KI_HEDGING: list[str] = [
    "Es ist wichtig zu beachten, dass",
    "Es ist wichtig zu beachten",
    "Es ist erwähnenswert, dass",
    "Es ist bemerkenswert, dass",
    "Es sollte beachtet werden, dass",
    "Im Allgemeinen",
    "In vielen Fällen",
    "Es ist allgemein bekannt, dass",
    "Es lässt sich nicht leugnen, dass",
    "Es versteht sich von selbst, dass",
]

ANTI_KI_ESSAY_CONNECTORS: list[str] = [
    "Darüber hinaus",
    "Zusätzlich",
    "Des Weiteren",
    "Zusammenfassend lässt sich sagen",
    "Abschließend lässt sich sagen",
    "Insgesamt ist",
    "Im Großen und Ganzen",
    "Davon abgesehen",
]

ANTI_KI_GENERIC_OPENERS: list[str] = [
    "In der heutigen schnelllebigen Welt",
    "In der heutigen hektischen Welt",
    "In der heutigen Welt",
    "In der heutigen Zeit",
    "In einer Welt, in der",
    "Lassen Sie uns in die Welt von",
    "Lassen Sie uns eintauchen",
    "Immer mehr Menschen fragen sich",
    "Viele Experten sind sich einig, dass",
    "Als KI",
    "Als KI-Modell",
    "Als Sprachmodell",
]

# Typografie-Marker (Kategorie 5) — schwaecher belegt (2-1), deshalb NIE ein
# harter Fail: nur als Hinweis/Violation-Text gemeldet, wenn ein Cluster von
# Em-Dashes auftaucht (ein einzelner Gedankenstrich ist normales Deutsch).
_EM_DASH_CLUSTER_RE = re.compile(r"—.*—")

#: LinkedIn-Ratgeber-Floskeln — die VERBOTSLISTE AUS DEM P12-PROMPT.
#:
#: ⛔ WARUM DIESE KATEGORIE NACHGEZOGEN WURDE (2026-08-21): Die vier Listen oben
#:   jagen den CHATBOT-Ton ("Klar! Hier ist", "Tolle Frage!", "Ich hoffe, das
#:   hilft!"). P12 verbietet auf 544 Zeilen einen ANDEREN KI-Dialekt: den
#:   generischen Ratgeber-Ton, der nicht nach Assistent klingt, sondern nach
#:   Content-Marketing — und genau der landet in Posts.
#:
#:   GEMESSEN: von den 20 woertlich im P12-Prompt verbotenen Formulierungen
#:   erkannte der Detektor ZWEI. Prompt und Blocklist waren nie gegeneinander
#:   abgeglichen. Ein Post konnte damit fuenf ausdrueckliche Verbote enthalten
#:   und trotzdem als sauber gelten.
#:
#:   Quelle: content-truth/prompts/P12-post-generierung.md, Abschnitt
#:   "7. KI-Signale kompromisslos vermeiden" -> "Verbotene Formulierungen
#:   (absolut, ohne Ausnahme)". ⛔ Beim Aendern des Prompts hier nachziehen —
#:   test_anti_ki_deckt_p12_verbote() haelt die beiden Listen zusammen.
#: ⛔ NUR AM SATZANFANG eine Floskel — mitten im Satz normales Deutsch.
#:   GEGENPROBE, die das aufdeckte (2026-08-21): "Wir arbeiten grundsaetzlich
#:   anders als der Wettbewerb" und "Er hat kurz gesagt, es sei dringend" wurden
#:   als KI-Signal gemeldet. Beides sind korrekte Handwerker-Saetze. Ein Gate,
#:   das die abstraft, ist schlimmer als keins — es bestraft genau die
#:   konkrete Sprache, die P12 erreichen will.
#:   Als Signal wirken diese Woerter nur einleitend: "Grundsaetzlich: ..." /
#:   "Kurz gesagt: ...". Deshalb Positionspruefung statt Substring.
_ANTI_KI_NUR_SATZANFANG: frozenset[str] = frozenset(
    {
        "letztendlich",
        "zusammenfassend",
        "abschließend",
        "abschliessend",
        "grundsätzlich",
        "grundsaetzlich",
        "im wesentlichen",
        "kurz gesagt",
        "auf den punkt gebracht",
        "erstaunlicherweise",
        "bemerkenswerterweise",
        "nicht zu vergessen",
    }
)

ANTI_KI_LINKEDIN_RATGEBER: list[str] = [
    "Lass uns ehrlich sein",
    "Lassen Sie uns ehrlich sein",
    "Die Wahrheit ist",
    "Es ist an der Zeit",
    "Hier ist, warum",
    "Die meisten Menschen wissen nicht, dass",
    "Die meisten wissen nicht, dass",
    "Erstaunlicherweise",
    "Bemerkenswerterweise",
    "Letztendlich",
    "Zusammenfassend",
    "Abschließend",
    "Abschliessend",
    "Nicht zu vergessen",
    "Es stellt sich die Frage",
    "Grundsätzlich",
    "Grundsaetzlich",
    "Im Wesentlichen",
    "Im Kern geht es darum",
    "Hierbei gilt es zu beachten",
    "Es ist wichtig zu verstehen, dass",
    "Kurz gesagt",
    "Auf den Punkt gebracht",
]

_ANTI_KI_CATEGORIES: list[tuple[str, list[str]]] = [
    ("Eröffnungs-/Abschlussfloskeln", ANTI_KI_OPENERS_CLOSERS),
    ("Hedging/Absicherung", ANTI_KI_HEDGING),
    ("Aufsatz-Konnektoren", ANTI_KI_ESSAY_CONNECTORS),
    ("Generische Opener", ANTI_KI_GENERIC_OPENERS),
    ("LinkedIn-Ratgeber-Floskeln (P12-Verbotsliste)", ANTI_KI_LINKEDIN_RATGEBER),
]


def _find_phrase(text: str, phrase: str) -> str | None:
    """Case-/Anfuehrungszeichen-insensitive Substring-Suche.

    Normalisiert kurvige/gerade Anfuehrungszeichen + Groß-/Kleinschreibung,
    damit ein LLM-Output mit „..." statt "..." trotzdem erkannt wird.
    """

    def _norm(s: str) -> str:
        return s.replace("’", "'").replace("“", '"').replace("”", '"').lower()

    hay = _norm(text)
    needle = _norm(phrase)

    # Floskeln aus _ANTI_KI_NUR_SATZANFANG zaehlen ausschliesslich einleitend.
    # Gesucht wird deshalb JEDES Vorkommen, bis eines am Satzanfang steht —
    # `find()` allein wuerde beim ersten (legitimen) Treffer aufgeben und den
    # spaeteren echten uebersehen.
    if needle in _ANTI_KI_NUR_SATZANFANG:
        start = 0
        while True:
            idx = hay.find(needle, start)
            if idx == -1:
                return None
            davor = hay[:idx].rstrip()
            # Satzanfang: Textbeginn oder direkt nach Satzende/Zeilenumbruch.
            if not davor or davor[-1] in ".!?…:\n" or hay[:idx].endswith("\n"):
                return text[idx : idx + len(phrase)]
            start = idx + 1

    idx = hay.find(needle)
    if idx == -1:
        return None
    return text[idx : idx + len(phrase)]


def check_anti_ki_phrases(text: str) -> list[str]:
    """Scannt ``text`` gegen die DE-Anti-KI-Blocklist, gibt Treffer-Strings zurueck.

    Jeder Treffer wird als lesbare Zeile "[Kategorie] „Phrase"" gemeldet — kein
    Score, sondern die konkrete Phrase (Doktrin: Generierungs-Artefakt-Scan,
    kein Detektor).
    """
    hits: list[str] = []
    for category, phrases in _ANTI_KI_CATEGORIES:
        for phrase in phrases:
            found = _find_phrase(text, phrase)
            if found is not None:
                hits.append(f"[{category}] „{found}“")
    if _EM_DASH_CLUSTER_RE.search(text):
        hits.append(
            "[Typografie-Hinweis] mehrere Em-Dashes (—) im Post — "
            "schwaches Signal, ggf. durch Komma/Punkt ersetzen"
        )
    return hits


# ---------------------------------------------------------------------------
# Quantitative Text-Metriken — pure stdlib, Portierung aus persona-forge
# metrics.py (Doktrin: MATTR fuehrt bei kurzen Posts, TTR/Root-TTR/Log-TTR
# werden bewusst NICHT angeboten — laengenabhaengig, Vergleich ungueltig).
# ---------------------------------------------------------------------------

# Ein "Wort"-Token: Unicode-Buchstaben (inkl. Umlaute) + Ziffern, mit
# wort-internen Apostrophen/Bindestrichen ("Human-Design"). Casefolded, damit
# "Der"/"der" als ein Type zaehlen (TTR ist ein lexikalisches, kein
# orthografisches Maß).
_WORD_RE = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*", re.UNICODE)

# Satzendezeichen: . ! ? … sowie Leerzeilen als harte Trenner. Ausreichend fuer
# Social-Post-Rhythmus, kein vollstaendiger NLP-Segmenter.
_SENT_SPLIT_RE = re.compile(r"[.!?…]+|\n{2,}")


def tokenize(text: str) -> list[str]:
    """Casefoldete Wort-Tokens (Buchstaben/Ziffern, wort-interne '/- erhalten)."""
    return [m.group(0).casefold() for m in _WORD_RE.finditer(text)]


def word_count(text: str) -> int:
    """Anzahl Wort-Tokens — Nenner fuer Pro-1k-Frequenzen und Fuellwort-Ratio."""
    return len(tokenize(text))


def compute_mattr(text: str, window: int = 50) -> float:
    """Moving-Average Type-Token-Ratio (Covington & McFall 2010).

    Mittelt die TTR jedes ``window``-großen Sliding-Windows — laengen-robust,
    der Wert driftet nicht mit der Textlaenge, deshalb ueber Posts vergleichbar.
    Fuer Texte kuerzer als ``window`` degradiert es auf die einfache TTR des
    Gesamttexts (das einzig Sinnvolle ohne volles Fenster).

    Gibt 0.0 fuer leeren Text zurueck.
    """
    tokens = tokenize(text)
    n = len(tokens)
    if n == 0:
        return 0.0
    if n <= window:
        return len(set(tokens)) / n
    ratios: list[float] = []
    for i in range(n - window + 1):
        chunk = tokens[i : i + window]
        ratios.append(len(set(chunk)) / window)
    return mean(ratios)


def sentences(text: str) -> list[str]:
    """Zerlegt in Saetze (. ! ? … oder Leerzeilen-Trenner), leere entfernt."""
    return [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]


def sentence_lengths(text: str) -> list[int]:
    """Wortanzahl je Satz — die Rohreihe hinter Mittelwert/Varianz."""
    return [word_count(s) for s in sentences(text)]


def sentence_length_mean(text: str) -> float:
    """Durchschnittliche Satzlaenge in Woertern (0.0 ohne Saetze)."""
    lengths = sentence_lengths(text)
    return mean(lengths) if lengths else 0.0


def sentence_length_stdev(text: str) -> float:
    """Populations-Stdev der Satzlaenge — der Rhythmus-/Monotonie-Indikator.

    Populations- (nicht Stichproben-)Stdev, damit ein einzelner Satz 0.0 statt
    einen Domain-Error liefert.
    """
    lengths = sentence_lengths(text)
    return pstdev(lengths) if len(lengths) >= 1 else 0.0


def caps_ratio(text: str) -> float:
    """Anteil komplett großgeschriebener Wort-Tokens (Spam-/Schrei-Heuristik).

    Nimmt Tokens mit >=2 Buchstaben (Ein-Buchstaben-Abkuerzungen/Artikel wie
    "A" verzerren sonst kurze Posts). 0.0 ohne solche Tokens.
    """
    words = _WORD_RE.findall(text)
    letter_words = [w for w in words if len(w) >= 2 and any(c.isalpha() for c in w)]
    if not letter_words:
        return 0.0
    caps = sum(1 for w in letter_words if w.isupper())
    return caps / len(letter_words)


def filler_freq_per_1k(text: str, markers: list[str]) -> dict[str, float]:
    """Pro-1000-Wort-Frequenz je Marker (case-insensitive, ganzwortig).

    Mehrwort-Marker ("ich glaube") werden als Phrase gematcht. Nenner ist die
    Gesamt-Wortzahl von ``text``; leerer Text liefert 0.0 fuer jeden Marker.
    """
    tokens = tokenize(text)
    total = len(tokens)
    out: dict[str, float] = {}
    if total == 0:
        return {m: 0.0 for m in markers}
    joined = " " + " ".join(tokens) + " "
    for marker in markers:
        phrase = " " + " ".join(tokenize(marker)) + " "
        count = 0
        start = 0
        while True:
            idx = joined.find(phrase, start)
            if idx == -1:
                break
            count += 1
            start = idx + 1
        out[marker] = count / total * 1000
    return out


def compute_metrics(text: str) -> dict[str, float]:
    """Liefert das messbare Stil-Merkmal-Bundle fuer einen (kurzen) Social-Post.

    Enthaelt genau die Maße, die bei kurzer Postlaenge laengen-robust/aussage-
    kraeftig sind (Doktrin: MATTR fuehrt, MTLD/Burrows's-Delta brauchen mehr
    Text als ein Post hat und sind hier bewusst NICHT enthalten).
    """
    tokens = tokenize(text)
    n_tokens = len(tokens)
    return {
        "tokens": float(n_tokens),
        "mattr": round(compute_mattr(text, window=50), 4),
        "avg_sentence_length": round(sentence_length_mean(text), 2),
        "sentence_length_stdev": round(sentence_length_stdev(text), 2),
        "caps_ratio": round(caps_ratio(text), 4),
    }


# ---------------------------------------------------------------------------
# Voice-Consistency-Check — vergleicht Post-Metriken gegen ein P03-Voice-Profile
# ---------------------------------------------------------------------------

# Unterhalb dieser Token-Zahl laeuft MATTR auf kurzen Texten hoch (wenig
# Wiederholungsraum) — ein Ueberschreiten der oberen Korridorgrenze ist dann
# ein Mess-Artefakt, kein Stilbruch. Ein UNTERSCHREITEN (Monotonie) zaehlt
# unabhaengig von der Laenge immer als Verstoss (Doktrin: das ist der
# Fehlermodus, der zaehlt).
MATTR_STABLE_TOKENS = 500


def _as_list_of_str(value: Any) -> list[str]:
    """Best-effort: normalisiert ein P03-Feld auf eine flache String-Liste.

    ``nie_sagen``/``verbotene_woerter`` koennen Strings ODER Dicts mit
    ``item``/``grund`` enthalten (P03-kanonisch erlaubt beides, siehe
    schema_transformer.py). Nicht-String/Dict-Eintraege werden uebersprungen,
    kein Crash bei unerwarteter Form.
    """
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for entry in value:
        if isinstance(entry, str):
            s = entry.strip()
            if s:
                out.append(s)
        elif isinstance(entry, dict):
            item = entry.get("item") or entry.get("wort") or entry.get("phrase")
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
    return out


def _extract_forbidden_phrases(voice_profile: dict) -> list[str]:
    """Liest verbotene Phrasen aus vermeidungsprofil.nie_sagen +
    wortschatz.verbotene_woerter (beide best-effort, robust gegen Fehlen)."""
    phrases: list[str] = []
    vermeidung = voice_profile.get("vermeidungsprofil")
    if isinstance(vermeidung, dict):
        phrases.extend(_as_list_of_str(vermeidung.get("nie_sagen")))
    # Alt-/Alias-Feld aus v2 (vermeidungsregeln) — falls das kanonische Feld
    # fehlt, aber das rohe P03-v2-Feld direkt durchgereicht wurde.
    phrases.extend(_as_list_of_str(voice_profile.get("vermeidungsregeln")))
    wortschatz = voice_profile.get("wortschatz")
    if isinstance(wortschatz, dict):
        phrases.extend(_as_list_of_str(wortschatz.get("verbotene_woerter")))
    # Deduplizieren, Reihenfolge stabil halten.
    seen: set[str] = set()
    unique: list[str] = []
    for p in phrases:
        key = p.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def _check_forbidden_phrases(text: str, phrases: list[str]) -> list[str]:
    """Harte Verletzung: Post enthaelt eine explizit verbotene Phrase/Wort."""
    violations: list[str] = []
    for phrase in phrases:
        found = _find_phrase(text, phrase)
        if found is not None:
            violations.append(
                f"Verbotene Phrase getroffen: „{found}“ (nie_sagen/verbotene_woerter)"
            )
    return violations


def _num(value: Any) -> float | None:
    """Best-effort float-Konversion; None bei fehlendem/ungueltigem Wert."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_sentence_length_band(voice_profile: dict) -> tuple[float, float] | None:
    """Best-effort (min, max)-Korridor fuer die Ø Satzlaenge aus
    ``satzarchitektur`` bzw. optionalen numerischen Erweiterungsfeldern.

    Das kanonische content-autopilot-Schema traegt ``satzarchitektur.laenge``
    typischerweise als beschreibender String ("kurz, praegnant") statt als
    Zahlenband — ein numerischer Korridor wird deshalb NUR geprueft, wenn das
    Profil explizit ``mean_min``/``mean_max`` (oder ``min_woerter``/
    ``max_woerter``) mitliefert. Fehlt das, wird die Pruefung uebersprungen
    (kein Rateversuch aus Freitext).
    """
    satzarchitektur = voice_profile.get("satzarchitektur")
    if not isinstance(satzarchitektur, dict):
        return None
    lo = _num(satzarchitektur.get("mean_min", satzarchitektur.get("min_woerter")))
    hi = _num(satzarchitektur.get("mean_max", satzarchitektur.get("max_woerter")))
    if lo is None or hi is None:
        return None
    return (lo, hi)


def _extract_mattr_band(voice_profile: dict) -> tuple[float, float] | None:
    """Best-effort (min, max)-MATTR-Korridor aus ``wortschatz`` (falls das
    Profil eine numerische Erweiterung dafuer traegt) — analog zu
    ``_extract_sentence_length_band``: fehlt das Feld, wird uebersprungen."""
    wortschatz = voice_profile.get("wortschatz")
    if not isinstance(wortschatz, dict):
        return None
    mattr = wortschatz.get("mattr")
    if not isinstance(mattr, dict):
        return None
    lo = _num(mattr.get("min"))
    hi = _num(mattr.get("max"))
    if lo is None or hi is None:
        return None
    return (lo, hi)


def _extract_filler_limits(voice_profile: dict) -> dict[str, float]:
    """Best-effort Fuellwort-Obergrenzen (pro 1k) aus ``wortschatz.fuellwoerter``.

    ``fuellwoerter`` ist im kanonischen Schema eine reine String-Liste (keine
    Zahlen) — sie dient hier als Marker-Liste fuer die Frequenzmessung. Ein
    Limit wird nur angewendet, wenn das Profil explizit numerische Grenzen
    mitliefert (``wortschatz.fuellwoerter_max_per_1k``); sonst wird nur
    gemessen und in den Metriken ausgewiesen, ohne zu werten.
    """
    wortschatz = voice_profile.get("wortschatz")
    if not isinstance(wortschatz, dict):
        return {}
    limits = wortschatz.get("fuellwoerter_max_per_1k")
    if not isinstance(limits, dict):
        return {}
    out: dict[str, float] = {}
    for marker, limit in limits.items():
        val = _num(limit)
        if isinstance(marker, str) and val is not None:
            out[marker] = val
    return out


def check_voice_consistency(post_text: str, voice_profile: dict) -> dict:
    """Vergleicht ``post_text`` quantitativ gegen die Korridore/Erwartungen aus
    ``voice_profile`` (P03-Voice-Profile-Dict, kanonisches oder v2-Schema).

    Post-hoc-Check (Doktrin): misst den fertigen Post, urteilt NICHT ueber den
    Prompt. Robust gegen ein leeres/minimales ``voice_profile`` — jede
    Korridor-Pruefung, deren Feld fehlt, wird uebersprungen statt zu crashen;
    ein komplett leeres Profil liefert ``passed=True`` (keine Erwartungen
    hinterlegt = nichts verletzt).

    Returns:
        {
            "passed": bool,
            "score": float,          # 1.0 abzueglich 0.15 je harter Verstoss, floor 0.0
            "violations": list[str],
            "metrics": dict,         # compute_metrics(post_text) + gemessene Fuellwort-Freqs
        }
    """
    metrics = compute_metrics(post_text)
    violations: list[str] = []

    if not isinstance(voice_profile, dict):
        voice_profile = {}

    if metrics["tokens"] == 0:
        return {
            "passed": False,
            "score": 0.0,
            "violations": ["leerer Post — nichts zu messen"],
            "metrics": metrics,
        }

    n_tokens = int(metrics["tokens"])

    # 1) MATTR-Korridor (nur wenn das Profil eins traegt — best-effort).
    mattr_band = _extract_mattr_band(voice_profile)
    if mattr_band is not None:
        lo, hi = mattr_band
        mattr_val = metrics["mattr"]
        if mattr_val < lo:
            violations.append(
                f"MATTR {mattr_val:.3f} unter Korridor [{lo:.2f}, {hi:.2f}] (zu monoton)"
            )
        elif mattr_val > hi and n_tokens >= MATTR_STABLE_TOKENS:
            # Ueberschreitung bei kurzen Posts ist ein Mess-Artefakt (wenig
            # Wiederholungsraum), deshalb erst ab MATTR_STABLE_TOKENS hart.
            violations.append(
                f"MATTR {mattr_val:.3f} ueber Korridor [{lo:.2f}, {hi:.2f}] (zu gestreut)"
            )

    # 2) Satzlaengen-Korridor (Mittelwert) — nur wenn das Profil ein
    #    numerisches Band traegt.
    sl_band = _extract_sentence_length_band(voice_profile)
    if sl_band is not None:
        lo, hi = sl_band
        sl_mean = metrics["avg_sentence_length"]
        if not (lo <= sl_mean <= hi):
            violations.append(
                f"Ø Satzlänge {sl_mean:.1f} außerhalb Korridor [{lo:.0f}, {hi:.0f}] Wörter"
            )

    # 3) Fuellwort-Frequenzen — nur gewertet, wenn das Profil Obergrenzen traegt.
    filler_limits = _extract_filler_limits(voice_profile)
    if filler_limits:
        freqs = filler_freq_per_1k(post_text, list(filler_limits))
        metrics["filler_freq_per_1k"] = freqs
        for marker, limit in filler_limits.items():
            got = freqs.get(marker, 0.0)
            if got > limit:
                violations.append(f"Füllwort '{marker}' zu dicht: {got:.1f}/1k > {limit:.1f}/1k")

    # 4) Explizit verbotene Phrasen (vermeidungsprofil.nie_sagen /
    #    wortschatz.verbotene_woerter) — harte Verletzung, kein Korridor.
    forbidden = _extract_forbidden_phrases(voice_profile)
    violations.extend(_check_forbidden_phrases(post_text, forbidden))

    # 5) Anti-KI-Phrasen-Blocklist — harte Verletzung (Generierungs-Artefakt,
    #    kein Detektor-Score). Der Typografie-Hinweis (Em-Dash-Cluster) wird
    #    mitgemeldet, zaehlt aber ebenfalls als Verstoss in diesem einfachen
    #    Gate (kein separates "hints"-Feld im W4-Kontrakt dieser Funktion).
    anti_ki_hits = check_anti_ki_phrases(post_text)
    violations.extend(f"Anti-KI-Phrase: {hit}" for hit in anti_ki_hits)

    score = max(0.0, 1.0 - 0.15 * len(violations))
    return {
        "passed": len(violations) == 0,
        "score": round(score, 2),
        "violations": violations,
        "metrics": metrics,
    }
