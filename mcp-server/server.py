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

import os
mcp_port = int(os.environ.get("MCP_PORT", "8080"))
mcp = FastMCP("content_autopilot_mcp", host="0.0.0.0", port=mcp_port)

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
        stats = data.get("stats", {})
        pipeline = data.get("pipeline", {})
        budget_exceeded = data.get("llm_budget_exceeded", False)

        lines = ["## Content Autopilot — Status\n"]

        # Budget warning takes priority
        if budget_exceeded:
            lines.append("🔴 **ACHTUNG: KI-Pipeline pausiert** — Requesty.ai Portal-Budget erschoepft.")
            lines.append("   Robert muss unter https://requesty.ai das Guthaben aufladen.\n")

        # Pipeline status
        lines.append("### Pipeline")
        lines.append(f"- **{stats.get('total_items', 0)}** Items gesamt")
        transcribed = pipeline.get("transcribed", 0)
        if transcribed > 0:
            lines.append(f"- **{transcribed}** warten auf Analyse {'(pausiert)' if budget_exceeded else ''}")
        analyzed = pipeline.get("analyzed", 0) + pipeline.get("content_ready", 0)
        if analyzed > 0:
            lines.append(f"- **{analyzed}** analysiert / content-ready")

        # Content status
        lines.append("\n### Posts")
        lines.append(f"- **{stats.get('drafts', 0)}** Entw\u00fcrfe")
        lines.append(f"- **{stats.get('approved', 0)}** freigegeben")
        lines.append(f"- **{stats.get('published', 0)}** ver\u00f6ffentlicht")

        # Guidance
        lines.append("\n### Was jetzt?")
        if budget_exceeded:
            lines.append("1. Guthaben bei requesty.ai aufladen (blockiert alles andere)")
        if stats.get("approved", 0) > 0:
            lines.append(f"- {stats['approved']} Posts sind freigegeben und k\u00f6nnen ver\u00f6ffentlicht werden")
        if stats.get("drafts", 0) > 0:
            lines.append(f"- {stats['drafts']} Entw\u00fcrfe warten auf Pr\u00fcfung → nutze `autopilot_list_ideas` oder Posts-Tab")

        return "\n".join(lines)
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
        query = {"limit": 30}
        if params.status:
            query["status"] = params.status
        if params.source_item_id:
            query["source_item_id"] = params.source_item_id
        data = await _api("GET", "/api/ideas", params=query)
        if isinstance(data, list):
            ideas = data
            total = len(data)
        elif isinstance(data, dict):
            ideas = data.get("items", data.get("ideas", []))
            total = data.get("total", len(ideas))
        else:
            ideas = []
            total = 0

        if not ideas:
            return "Keine Ideen gefunden. Nutze `autopilot_generate_ideas` um neue Ideen zu generieren."

        lines = [f"## Content-Ideen ({len(ideas)} angezeigt von {total} gesamt)\n"]
        for idea in ideas[:20]:  # Show max 20 for readability
            score = idea.get("relevance_score", 0)
            angle = idea.get("angle", "?")
            status = idea.get("status", "new")
            q_count = len(idea.get("entrepreneur_questions", []))
            answered = idea.get("answered_questions", 0)

            status_icon = {"new": "🆕", "answers_received": "✅", "content_generated": "📝", "skipped": "⏭️"}.get(status, "•")
            lines.append(f"{status_icon} **{idea.get('title', 'Unbekannt')}**")
            lines.append(f"   ID: `{idea.get('id', '')[:8]}` | Angle: {angle} | Score: {score}/10 | Fragen: {answered}/{q_count}")
            if idea.get("hook_suggestion"):
                lines.append(f"   Hook: *{idea['hook_suggestion'][:80]}...*" if len(idea['hook_suggestion']) > 80 else f"   Hook: *{idea['hook_suggestion']}*")
            lines.append("")

        if total > 20:
            lines.append(f"*... und {total - 20} weitere Ideen (nur erste 20 angezeigt). Filter mit status=new/answers_received etc.*")

        lines.append("\n---")
        lines.append("**Naechste Schritte:**")
        new_count = sum(1 for i in ideas if i.get("status") == "new")
        answered_count = sum(1 for i in ideas if i.get("status") == "answers_received")
        if answered_count > 0:
            lines.append(f"- {answered_count} Ideen haben Antworten → `autopilot_save_post` oder `dialogue_generate_post`")
        if new_count > 0:
            lines.append(f"- {new_count} neue Ideen → `autopilot_get_idea` für Details und Fragen")

        return "\n".join(lines)
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


# ── Dialogic MCP Tools ───────────────────────────────────────────────

class DialogueListInput(BaseModel):
    """Filter fuer den Dialogue-Workflow."""
    model_config = ConfigDict(str_strip_whitespace=True)
    limit: int = Field(default=10, ge=1, le=50, description="Maximale Anzahl Items")
    ready_only: bool = Field(default=True, description="Nur Items mit Analyse (bereit fuer Dialogue)")


@mcp.tool(
    name="dialogue_list_items",
    annotations={
        "title": "Dialogue-Items auflisten",
        "readOnlyHint": True,
        "idempotentHint": True,
    }
)
async def dialogue_list_items(params: DialogueListInput) -> str:
    """Liste Items die bereit fuer den Dialogue-Workflow sind.

    Zeigt analysierte Videos/Podcasts mit:
    - Einzeiligem Summary
    - Anzahl vorbereiteter smarter Fragen
    - Status: waiting_for_answers | answers_given | no_questions_yet

    WORKFLOW: dialogue_list_items → dialogue_get_context → Fragen stellen
    → dialogue_submit_answers → dialogue_generate_post

    Args:
        params: limit (max Items), ready_only (nur analysierte Items)

    Returns:
        Liste der Items mit Status und Fragen-Anzahl.
    """
    try:
        data = await _api("GET", "/api/dialogue/items", params={
            "limit": params.limit,
            "ready_only": str(params.ready_only).lower(),
        })
        return _fmt(data, "Items bereit fuer Dialogue")
    except Exception as e:
        return f"Fehler beim Laden der Dialogue-Items: {e}"


class DialogueContextInput(BaseModel):
    """Item-ID fuer Kontext-Abruf."""
    model_config = ConfigDict(str_strip_whitespace=True)
    item_id: str = Field(..., description="UUID des Items", min_length=1)


@mcp.tool(
    name="dialogue_get_context",
    annotations={
        "title": "Dialogue-Kontext laden",
        "readOnlyHint": True,
        "idempotentHint": True,
    }
)
async def dialogue_get_context(params: DialogueContextInput) -> str:
    """Vollstaendiger Kontext fuer ein Item — alles was fuer smarte Fragen und Post-Generierung benoetigt wird.

    Liefert:
    - Transkript-Auszug (500 Woerter) mit Key-Quotes
    - Analyse-Ergebnisse (Hauptthema, Insights, Hooks)
    - Vorbereitete smarte Fragen (referenzieren spezifische Transkript-Stellen)
    - Brand-Voice-Profil des Unternehmers
    - Verbotene Phrasen
    - Letzte freigegebene Posts (Stil-Referenz)

    WICHTIG: Nutze die smart_questions aus dem Kontext um Robert GEZIELT zu befragen.
    Stelle die Fragen natuerlich im Gespraech — nicht als Liste vorlesen.

    Args:
        params: Item-ID

    Returns:
        Vollstaendiger Kontext fuer den Dialogue-Workflow.
    """
    try:
        data = await _api("GET", f"/api/dialogue/items/{params.item_id}/context")
        return _fmt(data, f"Kontext: {data.get('item', {}).get('title', params.item_id)}")
    except Exception as e:
        return f"Fehler beim Laden des Kontexts: {e}"


class DialogueAnswerItem(BaseModel):
    """Einzelne Antwort auf eine Frage."""
    model_config = ConfigDict(str_strip_whitespace=True)
    question_id: str = Field(..., description="UUID der Frage aus dialogue_get_context")
    answer_text: str = Field(..., description="Roberts Antwort — moeglichst woertlich", min_length=5)


class DialogueAnswersInput(BaseModel):
    """Antworten auf smarte Fragen."""
    model_config = ConfigDict(str_strip_whitespace=True)
    item_id: str = Field(..., description="UUID des Items")
    answers: list[DialogueAnswerItem] = Field(..., description="Liste der Frage-Antwort-Paare")


@mcp.tool(
    name="dialogue_submit_answers",
    annotations={
        "title": "Antworten speichern",
        "readOnlyHint": False,
        "idempotentHint": False,
    }
)
async def dialogue_submit_answers(params: DialogueAnswersInput) -> str:
    """Speichere Roberts Antworten auf die smarten Fragen.

    WICHTIG: Speichere die Antworten WOERTLICH wie Robert sie formuliert hat.
    Nicht zusammenfassen — die Original-Stimme ist der Content.

    Nach dem Speichern: dialogue_generate_post aufrufen fuer $0-Post-Generierung.

    Args:
        params: Item-ID und Liste der Antworten (question_id + answer_text)

    Returns:
        Gespeicherte Antworten, Fortschritt und ob Post-Generierung starten kann.
    """
    try:
        data = await _api("POST", f"/api/dialogue/items/{params.item_id}/answers", json_data={
            "answers": [{"question_id": a.question_id, "answer_text": a.answer_text} for a in params.answers]
        })
        return _fmt(data, "Antworten gespeichert")
    except Exception as e:
        return f"Fehler beim Speichern der Antworten: {e}"


class DialogueGenerateInput(BaseModel):
    """Parameter fuer die Post-Generierung via Dialogue."""
    model_config = ConfigDict(str_strip_whitespace=True)
    item_id: str = Field(..., description="UUID des Items mit gespeicherten Antworten")
    format: str = Field(
        default="story",
        description="Post-Format: story | opinion | how_to | question"
    )
    use_claude_direct: bool = Field(
        default=True,
        description="True: Claude generiert direkt (kein Requesty-Call, $0 Kosten). False: Backend-LLM."
    )


@mcp.tool(
    name="dialogue_generate_post",
    annotations={
        "title": "Post generieren (via Dialogue)",
        "readOnlyHint": False,
        "idempotentHint": False,
    }
)
async def dialogue_generate_post(params: DialogueGenerateInput) -> str:
    """Generiere LinkedIn-Post aus Roberts Antworten.

    use_claude_direct=True (Standard, empfohlen):
        Gibt strukturierten Prompt zurueck — DU (Claude) generierst den Post direkt.
        Kosten: $0 (kein Requesty-Call).
        NACH dem Tool-Aufruf: Nutze den prompt_for_claude um den Post zu erstellen.

    use_claude_direct=False:
        Ruft Backend-LLM (Requesty/Haiku) auf.
        Kosten: ~$0.005 pro Post.

    Formate:
    - story: Persoenliche Geschichte mit Konflikt → Erkenntnis
    - opinion: Starke Meinung, provokante These
    - how_to: Konkrete Schritte aus Erfahrung
    - question: Oeffnet Diskussion, endet mit Frage

    Args:
        params: Item-ID, Format, use_claude_direct

    Returns:
        Bei use_claude_direct=True: prompt_for_claude (dann Post selbst generieren)
        Bei use_claude_direct=False: post_draft vom Backend
    """
    try:
        data = await _api(
            "POST",
            f"/api/dialogue/items/{params.item_id}/generate-post",
            params={"format": params.format, "use_claude_direct": str(params.use_claude_direct).lower()},
        )
        if data.get("mode") == "claude_direct":
            # Claude generates directly — return the prompt
            prompt = data.get("prompt_for_claude", "")
            context = data.get("context_summary", {})
            return (
                f"## Post-Generierung: {context.get('source', '')} [{context.get('format', '')}]\n\n"
                f"**Beantwortet:** {context.get('answered_questions', 0)} Fragen | "
                f"**Stimme:** {context.get('voice', 'Standard')}\n\n"
                f"---\n\n"
                f"### Dein Prompt:\n\n{prompt}\n\n"
                f"---\n\n"
                f"*Generiere jetzt den Post basierend auf diesem Prompt.*"
            )
        else:
            return _fmt(data, "Post generiert (Backend-LLM)")
    except Exception as e:
        return f"Fehler bei der Post-Generierung: {e}"


# ── Tool: Post direkt speichern (kein Backend-LLM nötig) ─────────────

class SaveDirectPostInput(BaseModel):
    """Fertigen Post-Text direkt speichern."""
    model_config = ConfigDict(str_strip_whitespace=True)
    content_text: str = Field(
        ...,
        description="Der fertige LinkedIn-Post-Text (von Claude geschrieben)",
        min_length=50,
    )
    title: Optional[str] = Field(
        default=None,
        description="Kurzer Titel/Überschrift für interne Übersicht (optional)",
    )
    angle: Optional[str] = Field(
        default="manual",
        description="Post-Typ: howto, meinung, story, trend, kontroverse, statistik, manual",
    )
    pillar: Optional[str] = Field(
        default=None,
        description="Content-Säule: thought_leadership, how_to, personal_story, industry_news, product_service",
    )
    channel: str = Field(default="linkedin", description="Kanal (immer linkedin)")
    idea_id: Optional[str] = Field(
        default=None,
        description="UUID der Quell-Idee (optional, verknüpft den Post mit der Idee)",
    )


@mcp.tool(
    name="autopilot_save_post",
    annotations={
        "title": "Post direkt speichern (kein LLM-Budget nötig)",
        "readOnlyHint": False,
        "idempotentHint": False,
    }
)
async def autopilot_save_post(params: SaveDirectPostInput) -> str:
    """Speichere einen von DIR (Claude) direkt geschriebenen LinkedIn-Post.

    Nutze dieses Tool wenn du einen Post selbst geschrieben hast und ihn
    im Content-Autopilot-System speichern möchtest — ohne Backend-LLM-Kosten.

    Workflow:
    1. Hole eine Idee mit autopilot_get_idea
    2. Schreibe den Post selbst basierend auf der Idee + Unternehmer-Kontext
    3. Speichere ihn mit diesem Tool
    4. Der Post erscheint als Entwurf im Posts-Tab zur Freigabe

    Args:
        params: Post-Text + optionale Metadaten

    Returns:
        Bestätigung mit Post-ID für Freigabe via autopilot_approve_post
    """
    try:
        body: dict = {
            "content_text": params.content_text,
            "angle": params.angle or "manual",
            "channel": params.channel,
        }
        if params.title:
            body["title"] = params.title
        if params.pillar:
            body["pillar"] = params.pillar
        if params.idea_id:
            body["idea_id"] = params.idea_id

        data = await _api("POST", "/api/content/save-direct", json_data=body)
        post_id = data.get("id", "")
        char_count = data.get("char_count", 0)
        return (
            f"## Post gespeichert ✅\n\n"
            f"**Post-ID**: `{post_id}`\n"
            f"**Zeichen**: {char_count} (LinkedIn-Optimum: 800–1500)\n"
            f"**Status**: Entwurf — bereit zur Freigabe\n\n"
            f"Freigeben mit: `autopilot_approve_post(content_piece_id='{post_id}')`\n\n"
            f"Oder im Posts-Tab unter https://cap.zukunftsbund.de (Port 8601) freigeben."
        )
    except Exception as e:
        return f"Fehler beim Speichern: {e}"


# ── Tool: Idee überspringen ────────────────────────────────────────────

class SkipIdeaInput(BaseModel):
    """Idee als nicht relevant markieren."""
    model_config = ConfigDict(str_strip_whitespace=True)
    idea_id: str = Field(..., description="UUID der Content-Idee", min_length=1)


@mcp.tool(
    name="autopilot_skip_idea",
    annotations={
        "title": "Idee überspringen",
        "readOnlyHint": False,
        "idempotentHint": True,
    }
)
async def autopilot_skip_idea(params: SkipIdeaInput) -> str:
    """Markiere eine Idee als übersprungen (nicht relevant / kein Post erwünscht).

    Nutze dieses Tool wenn eine Idee nicht zum Unternehmer passt oder
    nicht verarbeitet werden soll. Die Idee bleibt im System aber
    wird bei Listen-Filtern nicht mehr angezeigt.

    Args:
        params: Idee-ID

    Returns:
        Bestätigung der Statusänderung
    """
    try:
        data = await _api("PATCH", f"/api/ideas/{params.idea_id}", json_data={"status": "skipped"})
        return f"Idee übersprungen ✓ — Status: {data.get('status', 'skipped')}"
    except Exception as e:
        return f"Fehler beim Überspringen: {e}"


# ── OAuth 2.0 Client Credentials (für claude.ai Connector) ────────────

MCP_CLIENT_ID = os.getenv("MCP_CLIENT_ID", "")
MCP_CLIENT_SECRET = os.getenv("MCP_CLIENT_SECRET", "")
MCP_BEARER_TOKEN = os.getenv("MCP_BEARER_TOKEN", "")

from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
import uvicorn


async def oauth_discovery(request: Request) -> JSONResponse:
    """OAuth 2.0 Authorization Server Metadata (RFC 8414)."""
    host = request.headers.get("host", "localhost")
    # Preserve scheme from X-Forwarded-Proto header (set by Traefik)
    scheme = request.headers.get("x-forwarded-proto", "https")
    base = f"{scheme}://{host}"
    return JSONResponse({
        "issuer": base,
        "token_endpoint": f"{base}/oauth/token",
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "grant_types_supported": ["client_credentials"],
        "response_types_supported": ["token"],
        "scopes_supported": ["mcp"],
    })


async def oauth_token(request: Request) -> JSONResponse:
    """OAuth 2.0 Token Endpoint — client_credentials grant."""
    # Support both form-encoded and JSON body
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        grant_type = body.get("grant_type")
        client_id = body.get("client_id")
        client_secret = body.get("client_secret")
    else:
        form = await request.form()
        grant_type = form.get("grant_type")
        client_id = form.get("client_id")
        client_secret = form.get("client_secret")

    if grant_type != "client_credentials":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    # If no credentials configured, allow any request (open mode)
    if MCP_CLIENT_ID and MCP_CLIENT_SECRET:
        if client_id != MCP_CLIENT_ID or client_secret != MCP_CLIENT_SECRET:
            return JSONResponse({"error": "invalid_client", "error_description": "Invalid credentials"}, status_code=401)

    token = MCP_BEARER_TOKEN if MCP_BEARER_TOKEN else "open"
    return JSONResponse({
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 86400,
        "scope": "mcp",
    })


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "server": "content-autopilot-mcp"})


# ── Server starten ────────────────────────────────────────────────────

if __name__ == "__main__":
    # Build FastMCP SSE ASGI app
    mcp_asgi = mcp.sse_app()

    # Wrap with Starlette for OAuth + health endpoints
    app = Starlette(
        routes=[
            Route("/.well-known/oauth-authorization-server", oauth_discovery, methods=["GET"]),
            Route("/oauth/token", oauth_token, methods=["POST"]),
            Route("/health", health, methods=["GET"]),
            Mount("/", app=mcp_asgi),
        ],
    )

    uvicorn.run(app, host="0.0.0.0", port=mcp_port, log_level="warning")
