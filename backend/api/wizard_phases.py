"""
Wizard-Gesprächsphasen — dep-freie Konstante (Issue #44).

Diese Datei hat KEINE schweren Abhängigkeiten (kein sqlalchemy, kein fastapi)
und kann direkt in Tests importiert werden.

Board-SOLL (docs/FIGMA-SOLL-IST-MASTER.md §2.2 — verbindlich):
  1  Ankommen & Geschichte
  2  Alltag & Antrieb
  3  Expertise & Fachwissen      ← war komplett fehlend (6→8-Fix)
  4  Zielkunde
  5  Angebot, Markt & Differenzierung
  6  Vertrauen & Integrität      ← getrennt von "Abschluss" (6→8-Fix)
  7  Sprache & Stil
  8  Abschluss                   ← getrennt von "Vertrauen & Integrität" (6→8-Fix)

HINWEIS FÜR CHRIS (Content-Owner):
  Die Fragen für Phase 3 "Expertise & Fachwissen" sowie die getrennten Phasen
  6 "Vertrauen & Integrität" und 8 "Abschluss" sind fachlich sinnvolle Defaults
  im Stil des bestehenden Onboarding-Gesprächs. Finaler Wortlaut gehört Chris
  (Content-Refine nach diesem Commit). Alles als Chris-refinebare Defaults markiert.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# WIZARD_PHASES — 8 Board-Phasen in Board-Reihenfolge
# ---------------------------------------------------------------------------

WIZARD_PHASES: list[dict] = [
    # ── Phase 1: Ankommen & Geschichte ──────────────────────────────────────
    # Quelle: Master-MD "Start-Fragebogen Content v2" Phase 1 (unverändert)
    {
        "phase": 1,
        "title": "Ankommen & Geschichte",
        "goal": "Vertrauen aufbauen, echte Geschichte rausholen, erste Voice-Signale sammeln.",
        "questions": [
            {
                "id": "q1_1",
                "text": "Erzähl mal — wie bist du zu dem gekommen, was du heute machst? Nicht die offizielle Version, sondern die echte Geschichte.",
                "hints": [
                    "War das geplant oder eher Zufall?",
                    "Gab es einen Moment, wo du gedacht hast: das ist es?",
                    "Was hast du davor gemacht?",
                ],
            },
            {
                "id": "q1_2",
                "text": "Gab es einen Moment, der für dich alles verändert hat? Ein Vorher-Nachher?",
                "hints": [
                    "Das kann eine Kündigung gewesen sein, ein Gespräch, ein Projekt das schiefging...",
                ],
            },
            {
                "id": "q1_3",
                "text": "Welche Fehler hast du gemacht, über die du heute froh bist?",
                "hints": [
                    "Nicht 'Ich habe gelernt dass...' sondern konkret: 'Was genau ist passiert?'",
                ],
            },
        ],
    },
    # ── Phase 2: Alltag & Antrieb ────────────────────────────────────────────
    # Unverändert aus v1 (6 Phasen)
    {
        "phase": 2,
        "title": "Alltag & Antrieb",
        "goal": "Den echten Arbeitsalltag verstehen. Daraus entsteht Relatability im Content.",
        "questions": [
            {
                "id": "q2_1",
                "text": "Beschreib mal einen normalen Arbeitstag. Wann fängst du an, was passiert zuerst, wann ist Schluss?",
                "hints": [],
            },
            {
                "id": "q2_2",
                "text": "Vervollständige spontan (nicht nachdenken, einfach reagieren): „Den besten Teil meines Jobs finde ich: ___”",
                "hints": ["Tipp: Kein perfekter Satz nötig — Stichwörter reichen."],
                "completion_prefix": "Den besten Teil meines Jobs finde ich:",
            },
            {
                "id": "q2_3",
                "text": "Vervollständige: „Am meisten nervt mich: ___”",
                "hints": [],
                "completion_prefix": "Am meisten nervt mich:",
            },
            {
                "id": "q2_4",
                "text": "Vervollständige: „Das letzte Mal, dass ich dachte 'genau deshalb mach ich das', war als: ___”",
                "hints": [],
                "completion_prefix": "Das letzte Mal, dass ich dachte 'genau deshalb mach ich das', war als:",
            },
        ],
    },
    # ── Phase 3: Expertise & Fachwissen ─────────────────────────────────────
    # NEU (6→8-Fix, Issue #44) — war komplett fehlend.
    # CHRIS-FLAG: Fragen sind fachlich sinnvolle Defaults im Stil Phase 1/2.
    # Finaler Wortlaut gehört Chris (Content-Refine).
    {
        "phase": 3,
        "title": "Expertise & Fachwissen",
        "goal": "Tiefes Fachwissen, Kernkompetenz und echte Expertise sichtbar machen — für Authority-Content.",
        "questions": [
            {
                "id": "q3_1",
                "text": "Wofür wenden sich Leute an dich, wenn sie wirklich nicht weiter wissen?",
                "hints": [
                    "Das ist oft der Kern deiner Expertise — nicht das, was du auf der Website stehen hast.",
                    "Was ist das eine Problem, das du besser löst als fast jeder andere?",
                ],
            },
            {
                "id": "q3_2",
                "text": "Welche Fragen stellst du, die andere nicht stellen — und warum?",
                "hints": [
                    "Gibt es eine Diagnose-Frage, die du immer als erstes stellst?",
                    "Was siehst du sofort, was dein Gegenüber noch nicht sieht?",
                ],
            },
            {
                "id": "q3_3",
                "text": "Was war die schwierigste Aufgabe oder das komplexeste Problem, das du je gelöst hast?",
                "hints": [
                    "Keine Berufsbezeichnung — ein konkretes Szenario.",
                    "Was hat dich dabei überrascht?",
                ],
            },
            {
                "id": "q3_4",
                "text": "Vervollständige: „Das, was die meisten über mein Fachgebiet falsch verstehen, ist: ___”",
                "hints": [],
                "completion_prefix": "Das, was die meisten über mein Fachgebiet falsch verstehen, ist:",
            },
            {
                "id": "q3_5",
                "text": "Welche Ressourcen, Bücher oder Erfahrungen haben dein Denken am stärksten geprägt?",
                "hints": [
                    "Das kann ein Buch sein, ein Mentor, ein Projekt — oder ein Scheitern.",
                ],
            },
        ],
    },
    # ── Phase 4: Zielkunde ───────────────────────────────────────────────────
    # War Phase 3 — nach Board-Umstellung jetzt Phase 4 (unverändert)
    {
        "phase": 4,
        "title": "Zielkunde",
        "goal": "Den Kunden des Kunden so genau verstehen, dass die KI später in dessen Sprache schreiben kann.",
        "questions": [
            {
                "id": "q4_1",
                "text": "Stell dir vor, dein typischer Kunde sitzt mir gegenüber. Beschreib mir die Person — nicht die Firma, sondern den Menschen.",
                "hints": [
                    "Wie alt ungefähr? Welche Position?",
                    "Was ist dem/der wichtig? Wovon ist er/sie gestresst?",
                ],
            },
            {
                "id": "q4_2",
                "text": "Woran merkst du in den ersten 5 Minuten eines Gesprächs, ob jemand ein guter Kunde wird — oder nicht?",
                "hints": [],
            },
            {
                "id": "q4_3",
                "text": "Mit wem willst du auf keinen Fall arbeiten?",
                "hints": [],
            },
            {
                "id": "q4_4",
                "text": "Vervollständige: „Meine Kunden glauben oft, dass ___. In Wirklichkeit ist es so: ___”",
                "hints": [],
                "completion_prefix": "Meine Kunden glauben oft, dass... In Wirklichkeit ist es so:",
            },
            {
                "id": "q4_5",
                "text": "Vervollständige: „Die Frage, die mir am häufigsten gestellt wird, ist: ___”",
                "hints": [],
                "completion_prefix": "Die Frage, die mir am häufigsten gestellt wird, ist:",
            },
            {
                "id": "q4_6",
                "text": "Vervollständige: „Was meine Kunden wirklich brauchen, ist nicht ___, sondern: ___”",
                "hints": [],
                "completion_prefix": "Was meine Kunden wirklich brauchen, ist nicht..., sondern:",
            },
            {
                "id": "q4_7",
                "text": "Was ändert sich konkret für deinen Kunden, wenn er mit dir arbeitet? Vorher → Nachher.",
                "hints": [],
            },
            {
                "id": "q4_8",
                "text": "Hast du eine Erfolgsgeschichte, die du gerne erzählst?",
                "hints": [],
            },
            {
                "id": "q4_9",
                "text": "Hast du originale Zitate von Kunden — WhatsApp-Nachrichten, Bewertungen, Mails? Falls ja, gerne hier einfügen.",
                "hints": ["Falls nicht zur Hand: nach dem Wizard zusenden."],
                "required": False,
            },
        ],
    },
    # ── Phase 5: Angebot, Markt & Differenzierung ────────────────────────────
    # War Phase 4 "Angebot & Markt" — nach Board-Umstellung jetzt Phase 5
    # Titel erweitert um "& Differenzierung" (Board-konform)
    {
        "phase": 5,
        "title": "Angebot, Markt & Differenzierung",
        "goal": "Positionierung und Differenzierung verstehen — für strategischen Content.",
        "questions": [
            {
                "id": "q5_1",
                "text": "Stell dir vor, jemand auf einer Familienfeier fragt: 'Und was machst du so?' — was sagst du?",
                "hints": ["Kein Marketing-Speak — wie du es wirklich erklärst."],
            },
            {
                "id": "q5_2",
                "text": "Was ist das eigentliche Problem deiner Kunden — nicht das offensichtliche, sondern das darunter?",
                "hints": [
                    "Das offensichtliche Problem ist 'zu wenig Kunden', aber eigentlich geht es oft um Unsicherheit, fehlende Strategie, oder dass sie sich nicht trauen sichtbar zu werden.",
                ],
            },
            {
                "id": "q5_3",
                "text": "Was machst du anders als andere in deiner Branche? Nicht 'besser' — anders.",
                "hints": [],
            },
            {
                "id": "q5_4",
                "text": "Worauf legst du Wert, was anderen scheinbar egal ist?",
                "hints": [],
            },
            {
                "id": "q5_5",
                "text": "Wer sind deine Mitbewerber — und was hat dein Kunde typischerweise schon probiert, bevor er zu dir kam?",
                "hints": [],
            },
            {
                "id": "q5_6",
                "text": "Vervollständige: „Die meisten in meiner Branche machen den Fehler, dass: ___”",
                "hints": [],
                "completion_prefix": "Die meisten in meiner Branche machen den Fehler, dass:",
            },
            {
                "id": "q5_7",
                "text": "Vervollständige: „Was in meiner Branche total unterschätzt wird, ist: ___”",
                "hints": [],
                "completion_prefix": "Was in meiner Branche total unterschätzt wird, ist:",
            },
            {
                "id": "q5_8",
                "text": "Vervollständige: „Der größte Mythos in meiner Branche ist: ___”",
                "hints": [],
                "completion_prefix": "Der größte Mythos in meiner Branche ist:",
            },
            {
                "id": "q5_9",
                "text": "Vervollständige: „Wenn ich etwas an meiner Branche ändern könnte, wäre es: ___”",
                "hints": [],
                "completion_prefix": "Wenn ich etwas an meiner Branche ändern könnte, wäre es:",
            },
        ],
    },
    # ── Phase 6: Vertrauen & Integrität ─────────────────────────────────────
    # NEU als eigene Phase (6→8-Fix, Issue #44) — aus alter Phase 6 herausgetrennt.
    # CHRIS-FLAG: Fragen sind Defaults im Stil des bestehenden Onboardings.
    # Finaler Wortlaut gehört Chris (Content-Refine).
    {
        "phase": 6,
        "title": "Vertrauen & Integrität",
        "goal": "Vertrauenssignale und Haltung explizit machen — Grundlage für Authority und Trust-Content.",
        "questions": [
            {
                "id": "q6_1",
                "text": "Was könnte jemanden überzeugen, dass du weißt, wovon du sprichst?",
                "hints": [
                    "Anzahl Kunden/Projekte, Jahre Erfahrung, Zertifikate, Preise, Auftritte, Veröffentlichungen.",
                ],
            },
            {
                "id": "q6_2",
                "text": "Was ist dir in der Zusammenarbeit mit Kunden nicht verhandelbar — wo ziehst du eine klare Linie?",
                "hints": [
                    "Das zeigt Haltung und Integrität — genau das, was auf LinkedIn überzeugt.",
                ],
            },
            {
                "id": "q6_3",
                "text": "Gab es eine Situation, in der du 'Nein' gesagt hast, obwohl es dich Geld oder einen Auftrag gekostet hat?",
                "hints": [
                    "Kein Selbstlob nötig — es geht um die Erzählung hinter dem Nein.",
                ],
            },
            {
                "id": "q6_4",
                "text": "Vervollständige: „Das Wichtigste, was ich jemandem mitgeben würde, der in meiner Branche startet, ist: ___”",
                "hints": [],
                "completion_prefix": "Das Wichtigste, was ich jemandem mitgeben würde, der in meiner Branche startet, ist:",
            },
        ],
    },
    # ── Phase 7: Sprache & Stil ──────────────────────────────────────────────
    # War Phase 5 — nach Board-Umstellung jetzt Phase 7
    # IDs angepasst: q7_ statt q5_ (neue Phasennummer)
    {
        "phase": 7,
        "title": "Sprache & Stil",
        "goal": "Sprachliche Präferenzen explizit machen, um die Voice-Analyse zu ergänzen.",
        "questions": [
            {
                "id": "q7_1",
                "text": "Gibt es Wörter oder Ausdrücke, die du besonders gerne benutzt?",
                "hints": [],
            },
            {
                "id": "q7_2",
                "text": "Und welche vermeidest du bewusst?",
                "hints": [],
            },
            {
                "id": "q7_3",
                "text": "Welche Fachbegriffe benutzt deine Branche, die Außenstehende nicht kennen?",
                "hints": [],
            },
            {
                "id": "q7_4",
                "text": "Zeig mir 2–3 Posts oder Texte — von dir oder anderen — die du richtig gut findest. Was genau gefällt dir daran?",
                "hints": [
                    "Falls nicht sofort zur Hand: Links oder Screenshots nach dem Wizard zusenden."
                ],
                "required": False,
            },
            {
                "id": "q7_linkedin_posts",
                "type": "linkedin_posts",
                "required": False,
                "label": "LinkedIn-Posts als Voice-Quelle (optional)",
                "placeholder": "Füge bis zu 10 LinkedIn-Posts ein, die deinen Stil gut zeigen...",
                "help": "Deine bestehenden Posts helfen der KI, deinen Schreibstil noch präziser zu erfassen. Trenne mehrere Posts durch eine Leerzeile.",
                "max_items": 10,
                "hints": [],
            },
        ],
    },
    # ── Phase 8: Abschluss ───────────────────────────────────────────────────
    # NEU als eigene Phase (6→8-Fix, Issue #44) — aus alter Phase 6 herausgetrennt.
    # CHRIS-FLAG: Closing-Fragen sind Defaults. Finaler Wortlaut gehört Chris.
    {
        "phase": 8,
        "title": "Abschluss",
        "goal": "Den Onboarding-Call würdig abschließen und letzte offene Punkte klären.",
        "questions": [
            {
                "id": "q8_1",
                "text": "Was würdest du deinem Ich von vor 5–10 Jahren raten? Ein Satz.",
                "hints": [],
            },
            {
                "id": "q8_2",
                "text": "Gibt es etwas, das wir nicht gefragt haben, was du aber wichtig findest?",
                "hints": [],
                "required": False,
            },
            {
                "id": "q8_3",
                "text": "Abschluss-Bitte: Schick uns nach dem Wizard noch — Fotos (mit Kunden, bei der Arbeit, Alltag — Handy-Fotos sind perfekt), Beispiel-Posts die dir gefallen, und Original-Kundenzitate falls vorhanden.",
                "hints": [],
                "required": False,
                "type": "note",
            },
        ],
    },
]

# Anzahl Phasen als Konstante — kein Hardcoding von 6 oder 8 mehr nötig
WIZARD_PHASE_COUNT: int = len(WIZARD_PHASES)
