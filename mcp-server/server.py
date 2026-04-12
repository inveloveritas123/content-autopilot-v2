"""
Content Autopilot MCP Server — Das Kernprodukt.

Plattformunabhaengig: Funktioniert mit jedem AI-Client der MCP spricht.
- Claude Desktop / Cowork
- ChatGPT (mit MCP-Support)
- Gemini
- Jeder zukuenftiger MCP-kompatibler Client

Der Unternehmer verbindet seinen bevorzugten AI-Assistenten und hat
sofort Zugriff auf seine Content-Pipeline:
- Videos analysiert → Ideen bereit → Fragen beantworten → Posts generieren

Auth: API-Key pro Tenant (= Kunde) im Header X-API-Key.
Backend: Spricht mit dem FastAPI-Backend ueber HTTP.
"""
import json
import logging
from typing import Optional

import httpx
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# ── Server Init ───────────────────────────────────────────────────────

mcp = FastMCP("content_autopilot_mcp")

# Backend-URL wird ueber Env konfiguriert
# Primaer: BACKEND_URL (wie in docker-compose.yml)
# Fallback: CONTENT_AUTOPILOT_URL (fuer standalone-Betrieb)
import os
BACKEND_URL = os.getenv("BACKEND_URL", os.getenv("CONTENT_AUTOPILOT_URL", "http://localhost:8501"))
API_KEY = os.getenv("API_KEY", os.getenv("CONTENT_AUTOPILOT_API_KEY", ""))


async def _api(method: str, path: str, json_data: dict = None, params: dict = None) -> dict:
    """HTTP-Call an das Content-Autopilot-Backend."""
    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.request(
            method,
            f"{BACKEND_URL}{path}",
            json=json_data,
            params=params,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


def _fmt(data: dict | list, title: str = "") -> str:
    """Formatiere API-Response als lesbaren Text fuer den AI-Client."""
    if title:
        return f"## {title}\n\n```json\n{json.dumps(data, indent=2, ensure_ascii=False)}\n```"
    return json.dumps(data, indent=2, ensure_ascii=False)


# ── Tool: Dashboard / Ueberblick ──────────────────────────────────────

@mcp.tool(
    name="autopilot_dashboard",
    annotations={
        "title": "Content Autopilot Dashboard",
        "readOnlyHint": True,
        "idempotentHint": True,
    }
)
async def autopilot_dashboard() -> str:
    """Zeige den aktuellen Status: Neue Videos, wartende Ideen, offene Fragen.

    Nutze dieses Tool als Erstes, um dem Unternehmer einen Ueberblick zu geben,
    was seit dem letzten Gespraech passiert ist.

    Returns:
        Uebersicht ueber neue Videos, analysierte Items, wartende Ideen und offene Posts.
    """
    try:
        data = await _api("GET", "/api/dashboard")
        return _fmt(data, "Content Autopilot — Dein Dashboard")
    except Exception as e:
        return f"Fehler beim Laden des Dashboards: {e}"


# ── Tool: Videos / Quellen ────────────────────────────────────────────

class ListVideosInput(BaseModel):
    """Filter fuer die Video-Liste."""
    model_config = ConfigDict(str_strip_whitespace=True)
    status: Optional[str] = Field(
        default=None,
        description="Filter nach Status: new, transcribed, analyzed, ideas_generated"
    )
    limit: int = Field(default=20, ge=1, le=100, description="Maximale Anzahl Ergebnisse")


@mcp.tool(
    name="autopilot_list_videos",
    annotations={
        "title": "Videos auflisten",
        "readOnlyHint": True,
        "idempotentHint": True,
    }
)
async def autopilot_list_videos(params: ListVideosInput) -> str:
    """Liste alle analysierten Videos mit Status und Analyse-Ergebnissen.

    Zeigt Videos die transkribiert und analysiert wurden, inklusive
    Summary, Tags und Trend-Score.

    Args:
        params: Filter (status, limit)

    Returns:
        Liste der Videos mit Titel, Status und Analyse-Zusammenfassung.
    """
    try:
        query = {"limit": params.limit}
        if params.status:
            query["status"] = params.status
        data = await _api("GET", "/api/items", params=query)
        return _fmt(data, "Analysierte Videos")
    except Exception as e:
        return f"Fehler beim Laden der Videos: {e}"


# ── Tool: Content-Ideen ───────────────────────────────────────────────

class GenerateIdeasInput(BaseModel):
    """Video-ID fuer die Ideen-Generierung."""
    model_config = ConfigDict(str_strip_whitespace=True)
    item_id: str = Field(..., description="UUID des analysierten Videos", min_length=1)


@mcp.tool(
    name="autopilot_generate_ideas",
    annotations={
        "title": "Content-Ideen generieren",
        "readOnlyHint": False,
        "idempotentHint": False,
    }
)
async def autopilot_generate_ideas(params: GenerateIdeasInput) -> str:
    """Generiere 5-8 Content-Ideen aus einem analysierten Video.

    Jede Idee hat einen Angle (Meinung, How-To, Story, Kontroverse, Statistik),
    einen LinkedIn-Relevanz-Score und vorbereitete Fragen fuer den Unternehmer.

    Nutze dieses Tool nachdem ein Video analysiert wurde, um daraus Content-Ideen
    abzuleiten. Die Ideen werden in der Datenbank gespeichert.

    Args:
        params: Video-Item-ID

    Returns:
        Liste der generierten Ideen mit Titeln, Angles und Relevanz-Scores.
    """
    try:
        data = await _api("POST", f"/api/ideas/generate/{params.item_id}")
        return _fmt(data, "Neue Content-Ideen generiert")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            return "Dieses Video hat noch keine Analyse. Bitte warte bis die automatische Analyse abgeschlossen ist."
        return f"Fehler bei der Ideen-Generierung: {e.response.text}"
    except Exception as e:
        return f"Fehler bei der Ideen-Generierung: {e}"


class ListIdeasInput(BaseModel):
    """Filter fuer die Ideen-Liste."""
    model_config = ConfigDict(str_strip_whitespace=True)
    status: Optional[str] = Field(
        default=None,
        description="Filter: new, questions_sent, answers_received, content_generated, archived"
    )
    source_item_id: Optional[str] = Field(default=None, description="Filter nach Video-ID")


@mcp.tool(
    name="autopilot_list_ideas",
    annotations={
        "title": "Content-Ideen auflisten",
        "readOnlyHint": True,
        "idempotentHint": True,
    }
)
async def autopilot_list_ideas(params: ListIdeasInput) -> str:
    """Liste alle Content-Ideen, sortiert nach Relevanz.

    Zeigt Ideen mit Titel, Angle, Score und Status.
    Nutze den Status-Filter um z.B. nur Ideen zu zeigen die auf
    Antworten warten ('new') oder bereit fuer Post-Generierung sind ('answers_received').

    Args:
        params: Filter (status, source_item_id)

    Returns:
        Sortierte Liste der Ideen nach LinkedIn-Relevanz-Score.
    """
    try:
        query = {}
        if params.status:
            query["status"] = params.status
        if params.source_item_id:
            query["source_item_id"] = params.source_item_id
        data = await _api("GET", "/api/ideas", params=query)
        return _fmt(data, "Content-Ideen")
    except Exception as e:
        return f"Fehler beim Laden der Ideen: {e}"


class GetIdeaInput(BaseModel):
    """Idee-ID fuer Details."""
    model_config = ConfigDict(str_strip_whitespace=True)
    idea_id: str = Field(..., description="UUID der Content-Idee", min_length=1)


@mcp.tool(
    name="autopilot_get_idea",
    annotations={
        "title": "Idee-Details laden",
        "readOnlyHint": True,
        "idempotentHint": True,
    }
)
async def autopilot_get_idea(params: GetIdeaInput) -> str:
    """Lade alle Details einer Content-Idee: Beschreibung, Fragen, Quell-Zitate, bisherige Antworten.

    Nutze dieses Tool um die vorbereiteten Fragen zu sehen, bevor du sie
    dem Unternehmer im Gespraech stellst. Die Fragen sind so formuliert,
    dass sie persoenliche Erfahrungen und Meinungen hervorrufen.

    Args:
        params: Idee-ID

    Returns:
        Vollstaendige Idee mit Fragen, Kontext und bisherigen Antworten.
    """
    try:
        data = await _api("GET", f"/api/ideas/{params.idea_id}")
        return _fmt(data, f"Content-Idee: {data.get('title', '')}")
    except Exception as e:
        return f"Fehler beim Laden der Idee: {e}"


# ── Tool: Unternehmer-Antworten ───────────────────────────────────────

class SubmitAnswerInput(BaseModel):
    """Antwort des Unternehmers auf eine Frage."""
    model_config = ConfigDict(str_strip_whitespace=True)
    idea_id: str = Field(..., description="UUID der Content-Idee", min_length=1)
    question_index: int = Field(..., description="Index der Frage (0-basiert)", ge=0)
    question_text: str = Field(..., description="Die Frage (zur Nachvollziehbarkeit)", min_length=1)
    answer_text: str = Field(
        ...,
        description="Antwort des Unternehmers — moeglichst woertlich wie er/sie es gesagt hat",
        min_length=10,
    )


@mcp.tool(
    name="autopilot_submit_answer",
    annotations={
        "title": "Unternehmer-Antwort speichern",
        "readOnlyHint": False,
        "idempotentHint": False,
    }
)
async def autopilot_submit_answer(params: SubmitAnswerInput) -> str:
    """Speichere die Antwort des Unternehmers auf eine Frage.

    WICHTIG: Speichere die Antwort moeglichst WOERTLICH wie der Unternehmer
    sie formuliert hat. Nicht zusammenfassen oder umschreiben — die Original-Stimme
    ist entscheidend fuer authentischen Content.

    Das System trackt automatisch wieviele Fragen noch offen sind und
    aktualisiert den Status der Idee.

    Args:
        params: Idee-ID, Frage-Index, Frage-Text, Antwort-Text

    Returns:
        Fortschritt (X von Y Fragen beantwortet) und ob die Post-Generierung starten kann.
    """
    try:
        data = await _api("POST", f"/api/ideas/{params.idea_id}/answer", json_data={
            "question_index": params.question_index,
            "question_text": params.question_text,
            "answer_text": params.answer_text,
            "answer_source": "mcp_dialog",
        })
        return _fmt(data, "Antwort gespeichert")
    except Exception as e:
        return f"Fehler beim Speichern der Antwort: {e}"


# ── Tool: Post-Generierung ────────────────────────────────────────────

class GeneratePostInput(BaseModel):
    """Parameter fuer die Post-Generierung."""
    model_config = ConfigDict(str_strip_whitespace=True)
    idea_id: str = Field(..., description="UUID der Content-Idee", min_length=1)
    variants: int = Field(default=2, ge=1, le=5, description="Anzahl Post-Varianten (1-5)")


@mcp.tool(
    name="autopilot_generate_post",
    annotations={
        "title": "LinkedIn-Post generieren",
        "readOnlyHint": False,
        "idempotentHint": False,
    }
)
async def autopilot_generate_post(params: GeneratePostInput) -> str:
    """Generiere LinkedIn-Post-Varianten aus den Antworten des Unternehmers.

    Funktioniert nur wenn mindestens eine Antwort vorliegt.
    Die Posts werden aus der echten Stimme des Unternehmers erstellt —
    nicht aus dem Transkript. Die Quell-Analyse dient nur als Hintergrundkontext.

    TIPP: Zeige dem Unternehmer die Varianten und frage welche er bevorzugt.
    Dann iteriere direkt im Gespraech — Anpassungen kosten nichts extra.

    Args:
        params: Idee-ID und Anzahl gewuenschter Varianten

    Returns:
        Post-Varianten als Text, bereit fuer Review und Feinschliff.
    """
    try:
        data = await _api("POST", f"/api/ideas/{params.idea_id}/generate-post", json_data={
            "variants": params.variants,
        })
        return _fmt(data, "LinkedIn-Posts generiert")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            return "Noch keine Antworten vorhanden. Bitte stelle zuerst die Fragen und speichere die Antworten."
        return f"Fehler bei der Post-Generierung: {e.response.text}"
    except Exception as e:
        return f"Fehler bei der Post-Generierung: {e}"


# ── Tool: Post freigeben ──────────────────────────────────────────────

class ApprovePostInput(BaseModel):
    """Post-Freigabe."""
    model_config = ConfigDict(str_strip_whitespace=True)
    content_piece_id: str = Field(..., description="UUID des Content-Pieces", min_length=1)
    final_text: Optional[str] = Field(
        default=None,
        description="Optionaler finaler Text (wenn der Unternehmer Aenderungen gemacht hat)"
    )


@mcp.tool(
    name="autopilot_approve_post",
    annotations={
        "title": "Post freigeben",
        "readOnlyHint": False,
        "idempotentHint": True,
    }
)
async def autopilot_approve_post(params: ApprovePostInput) -> str:
    """Gib einen Post frei fuer die Veroeffentlichung.

    Optional kann ein ueberarbeiteter Text mitgegeben werden,
    falls der Unternehmer im Gespraech Aenderungen vorgenommen hat.

    Der Post wird im Dashboard als 'approved' markiert und kann
    von dort aus geplant/veroeffentlicht werden.

    Args:
        params: Content-Piece-ID und optionaler finaler Text

    Returns:
        Bestaetigung der Freigabe.
    """
    try:
        payload = {"status": "approved"}
        if params.final_text:
            payload["content_text"] = params.final_text
        data = await _api("PATCH", f"/api/content/{params.content_piece_id}", json_data=payload)
        return _fmt(data, "Post freigegeben")
    except Exception as e:
        return f"Fehler bei der Freigabe: {e}"


# ── Tool: Brand Voice ─────────────────────────────────────────────────

@mcp.tool(
    name="autopilot_get_voice_profile",
    annotations={
        "title": "Brand-Voice-Profil laden",
        "readOnlyHint": True,
        "idempotentHint": True,
    }
)
async def autopilot_get_voice_profile() -> str:
    """Lade das aktuelle Brand-Voice-Profil des Unternehmers.

    Zeigt Tonalitaet, Schreibstil, typische Redewendungen und Themen-Praeferenzen.
    Nutze dieses Profil um Posts im authentischen Stil des Unternehmers zu verfeinern.

    Returns:
        Brand-Voice-Profil mit Tone, Vocabulary, Favorite Phrases etc.
    """
    try:
        data = await _api("GET", "/api/tenants/me/voice-profile")
        return _fmt(data, "Brand Voice Profil")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return "Noch kein Brand-Voice-Profil vorhanden. Starte das Onboarding mit autopilot_start_onboarding."
        return f"Fehler: {e.response.text}"
    except Exception as e:
        return f"Fehler beim Laden des Voice-Profils: {e}"


class OnboardingAnswersInput(BaseModel):
    """Onboarding-Antworten fuer Brand-Voice-Profil."""
    model_config = ConfigDict(str_strip_whitespace=True)
    company_description: str = Field(..., description="Beschreibung des Unternehmens (2-3 Saetze)")
    target_audience: str = Field(..., description="Zielgruppe auf LinkedIn")
    tone_preference: str = Field(..., description="Gewuenschter Ton (locker, professionell, provokant...)")
    topics_core: str = Field(..., description="3-5 Kern-Themen fuer LinkedIn")
    role_description: str = Field(..., description="Rolle/Position des Unternehmers")
    topics_avoid: Optional[str] = Field(default=None, description="Themen/Toene die vermieden werden sollen")
    unique_perspective: Optional[str] = Field(default=None, description="Was unterscheidet die Sichtweise?")
    personal_values: Optional[str] = Field(default=None, description="Wichtige Business-Werte")


@mcp.tool(
    name="autopilot_start_onboarding",
    annotations={
        "title": "Brand-Voice-Onboarding starten",
        "readOnlyHint": False,
        "idempotentHint": False,
    }
)
async def autopilot_start_onboarding(params: OnboardingAnswersInput) -> str:
    """Erstelle ein Brand-Voice-Profil aus den Onboarding-Antworten des Unternehmers.

    Stelle dem Unternehmer die Fragen natuerlich im Gespraech und sammle
    die Antworten. Dann rufe dieses Tool mit allen Antworten auf.

    Die wichtigsten Fragen:
    1. Beschreibe dein Unternehmen wie du es einem Freund erklaeren wuerdest
    2. Wer ist deine Zielgruppe auf LinkedIn?
    3. Wie moechtest du klingen? (locker, professionell, provokant...)
    4. Ueber welche 3-5 Themen willst du hauptsaechlich posten?
    5. Wie wuerdest du deine Rolle beschreiben?

    Args:
        params: Antworten auf die Onboarding-Fragen

    Returns:
        Das erstellte Brand-Voice-Profil.
    """
    try:
        data = await _api("POST", "/api/tenants/me/voice-profile", json_data=params.model_dump(exclude_none=True))
        return _fmt(data, "Brand-Voice-Profil erstellt")
    except Exception as e:
        return f"Fehler beim Erstellen des Voice-Profils: {e}"


# ── Tool: Video-Analyse anstossen ─────────────────────────────────────

class AnalyzeVideoInput(BaseModel):
    """YouTube-URL fuer manuelle Analyse."""
    model_config = ConfigDict(str_strip_whitespace=True)
    youtube_url: str = Field(
        ...,
        description="YouTube-Video-URL (z.B. https://youtube.com/watch?v=...)",
        min_length=10,
    )


@mcp.tool(
    name="autopilot_analyze_video",
    annotations={
        "title": "Video analysieren",
        "readOnlyHint": False,
        "idempotentHint": True,
    }
)
async def autopilot_analyze_video(params: AnalyzeVideoInput) -> str:
    """Starte die Analyse eines YouTube-Videos manuell.

    Das Video wird transkribiert, analysiert und Content-Ideen werden generiert.
    Der Prozess dauert 1-2 Minuten.

    Normalerweise passiert das automatisch im Hintergrund fuer konfigurierte Kanaele.
    Nutze dieses Tool wenn der Unternehmer ein bestimmtes Video als Inspiration verwenden will.

    Args:
        params: YouTube-URL

    Returns:
        Status der gestarteten Analyse.
    """
    try:
        data = await _api("POST", "/api/sources/manual-analyze", json_data={
            "url": params.youtube_url,
        })
        return _fmt(data, "Video-Analyse gestartet")
    except Exception as e:
        return f"Fehler beim Starten der Analyse: {e}"


# ── Server starten ────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
