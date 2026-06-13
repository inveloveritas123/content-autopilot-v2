"""Qualitätsmessung für classify_chunk() — Issue #50.

Läuft gegen echten Requesty-Router. 42 manuell gelabelte Referenz-Chunks
(Deutsch, typischer Unternehmer-Content). Misst Trefferquote und Fehlklassen.

Usage:
    cd backend
    PYTHONPATH=. python tests/eval_classify_chunk.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections import Counter, defaultdict

# ─── Referenz-Chunks (label, text) ───────────────────────────────────────────

REFERENCE = [
    # ── werte (14) ────────────────────────────────────────────────────────────
    (
        "werte",
        "Vertrauen ist für mich die Grundlage jeder Geschäftsbeziehung. Ohne Vertrauen gibt es keinen nachhaltigen Erfolg.",
    ),
    (
        "werte",
        "Ich glaube fest daran, dass Qualität langfristig immer gewinnt. Kurzfristige Abkürzungen zahlen sich nicht aus.",
    ),
    (
        "werte",
        "Ehrlichkeit ist für mich nicht verhandelbar — auch wenn sie kurzfristig unbequem ist.",
    ),
    (
        "werte",
        "Freiheit bedeutet für mich: selbst entscheiden, mit wem ich arbeite und wofür ich stehe.",
    ),
    (
        "werte",
        "Nachhaltigkeit ist kein Trend für mich, sondern Überzeugung. Ich will ein Unternehmen aufbauen, das auch in 20 Jahren noch existiert.",
    ),
    (
        "werte",
        "Für mich ist Wachstum ohne Werte nichts wert. Ich will stolz auf das sein, was ich aufgebaut habe.",
    ),
    (
        "werte",
        "Meine Mitarbeiter kommen zuerst. Wenn es denen gut geht, geht es auch meinen Kunden gut.",
    ),
    (
        "werte",
        "Ich stehe dazu, dass ich manchmal Nein sage — auch zu gutem Geld. Nicht jeder Auftrag passt zu uns.",
    ),
    ("werte", "Kontinuierliches Lernen ist für mich ein Grundprinzip. Stillstand ist Rückschritt."),
    (
        "werte",
        "Ich glaube an Transparenz gegenüber Kunden. Keine versteckten Kosten, keine schöngeredeten Probleme.",
    ),
    (
        "werte",
        "Resilienz nach dem Burnout 2020: Ich habe gelernt, dass Gesundheit vor Umsatz kommt.",
    ),
    (
        "werte",
        "Partnerschaftlichkeit auf Augenhöhe — ich will kein Dienstleister sein, sondern Partner meiner Kunden.",
    ),
    ("werte", "Mein Antrieb ist es, echten Mehrwert zu schaffen, nicht nur Rechnungen zu stellen."),
    (
        "werte",
        "Verlässlichkeit: Wenn ich etwas zusage, halte ich es. Das ist für mich selbstverständlich.",
    ),
    # ── stories (14) ──────────────────────────────────────────────────────────
    (
        "stories",
        "2018 hatte ich meinen ersten großen Kunden fast verloren, weil ich ein Versprechen nicht gehalten habe. Seitdem schreibe ich alles auf.",
    ),
    (
        "stories",
        "Ich erinnere mich noch genau: Es war ein Dienstagabend, als mir klar wurde, dass mein Geschäftsmodell nicht mehr funktioniert. Ich saß allein im Büro.",
    ),
    (
        "stories",
        "Mein bester Kunde kam durch eine Weiterempfehlung — ich hatte ihm drei Monate zuvor kostenlos geholfen, ohne eine Gegenleistung zu erwarten.",
    ),
    (
        "stories",
        "Vor zwei Jahren musste ich eine Mitarbeiterin entlassen. Das war das Schwerste, was ich je getan habe — sie war seit Gründung dabei.",
    ),
    (
        "stories",
        "Auf einer Messe in München habe ich meinen jetzigen Geschäftspartner kennengelernt. Wir haben zwei Stunden an der Kaffeebar geredet und dann sofort ein Projekt gestartet.",
    ),
    (
        "stories",
        "Ich hatte mal einen Kunden, der mich nach einem Jahr Zusammenarbeit einfach nicht mehr zurückgerufen hat. Das hat mich wochenlang beschäftigt.",
    ),
    (
        "stories",
        "Als wir unser erstes Produkt lanciert haben, haben wir 200 E-Mails in der ersten Nacht bekommen. Ich konnte nicht schlafen vor Aufregung.",
    ),
    (
        "stories",
        "Mein Vater war Handwerker und hat mir beigebracht: Ein gutes Werkzeug kauft man einmal. Das gilt auch im Digitalen.",
    ),
    (
        "stories",
        "Ich habe einmal einen Pitch gewonnen, obwohl ich das günstigste Angebot hatte. Nicht weil ich billig war, sondern weil ich die ehrlichsten Antworten gegeben habe.",
    ),
    (
        "stories",
        "Nach dem Lockdown 2020 haben wir innerhalb von zwei Wochen auf Remote umgestellt. Rückblickend war das die beste Entscheidung meiner Unternehmensgeschichte.",
    ),
    (
        "stories",
        "Ein Freund hat mich damals gefragt: Was würdest du tun, wenn du keine Angst hättest? Diese Frage hat mein Leben verändert.",
    ),
    (
        "stories",
        "Ich war 32, pleite und hatte gerade mein erstes Unternehmen geschlossen. Drei Monate später habe ich das zweite gegründet — mit mehr Klarheit als je zuvor.",
    ),
    (
        "stories",
        "Unser Team hat einmal eine Nachtschicht eingelegt, um einen Kunden zu retten. Der Kunde weint noch heute fast, wenn er davon erzählt.",
    ),
    (
        "stories",
        "Mein erster Auftrag war 400 Euro. Ich habe 20 Stunden daran gearbeitet. Aber der Kunde ist heute noch bei mir.",
    ),
    # ── konflikte (14) ────────────────────────────────────────────────────────
    (
        "konflikte",
        "Das größte Problem in meiner Branche ist, dass alle über Qualität reden, aber niemand bereit ist, dafür zu zahlen.",
    ),
    (
        "konflikte",
        "Ich kämpfe täglich gegen die Erwartung, immer erreichbar zu sein. Kunden schreiben um 23 Uhr und wundern sich, wenn ich nicht sofort antworte.",
    ),
    (
        "konflikte",
        "Der Markt wird von Billiganbietern überschwemmt, die unsere Preise kaputt machen — und die Kunden merken erst später, was sie davon haben.",
    ),
    (
        "konflikte",
        "Das Finden von gutem Personal ist mein größtes Dauerproblem. Ich verliere gute Leute an Konzerne, die 20% mehr zahlen können.",
    ),
    (
        "konflikte",
        "Was mich wirklich frustriert: Kunden, die alles versprechen und dann beim Preis zögern. Das kostet mich Zeit, die ich nicht habe.",
    ),
    (
        "konflikte",
        "Die bürokratischen Anforderungen im deutschen Markt sind erdrückend. Ich verbringe mehr Zeit mit Verwaltung als mit dem, was ich eigentlich kann.",
    ),
    (
        "konflikte",
        "Mein Konflikt: Ich will wachsen, aber nicht auf Kosten der Qualität. Das sind zwei Dinge, die sich in meiner Branche zu widersprechen scheinen.",
    ),
    (
        "konflikte",
        "Digitalisierung wird gefordert, aber wenn ich neue Tools einführe, kommt Widerstand vom Team. Das zermürbt mich manchmal.",
    ),
    (
        "konflikte",
        "Ich bin gut darin, Dinge zu starten, aber schlecht darin, sie zu beenden. Das ist mein größter unternehmerischer Blind Spot.",
    ),
    (
        "konflikte",
        "Was ich nicht verstehe: Warum wird Selbstständigkeit gesellschaftlich immer noch als riskant bewertet, obwohl Angestelltsein genauso unsicher sein kann?",
    ),
    (
        "konflikte",
        "Ich habe Angst, zu skalieren und dabei meine Unternehmenskultur zu verlieren. Das hält mich nachts wach.",
    ),
    (
        "konflikte",
        "Meine größte Reibung entsteht zwischen dem, was Kunden sagen zu wollen, und dem, was tatsächlich zu ihrem Business passt.",
    ),
    (
        "konflikte",
        "Das Paradoxon meiner Arbeit: Je besser ich werde, desto mehr werde ich für Gratis-Beratung gefragt.",
    ),
    (
        "konflikte",
        "Ich verliere manchmal Aufträge, weil ich zu direkt sage, was ich denke. Ich weiß nicht, ob ich das ändern will oder kann.",
    ),
]


async def run_eval():
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    from services.embedding_service import classify_chunk

    total = len(REFERENCE)
    correct = 0
    wrong = []
    null_count = 0
    confusion: dict[str, Counter] = defaultdict(Counter)  # confusion[true][pred] = count

    print(f"Evaluiere {total} Referenz-Chunks via classify_chunk()...\n")

    for i, (true_label, text) in enumerate(REFERENCE, 1):
        predicted = await classify_chunk(text)
        if predicted is None:
            null_count += 1
            confusion[true_label]["<null>"] += 1
            wrong.append((true_label, "<null>", text[:60]))
            print(f"[{i:02d}] true={true_label:10s} pred=<null>  ✗  {text[:50]}…")
        elif predicted == true_label:
            correct += 1
            confusion[true_label][predicted] += 1
            print(f"[{i:02d}] true={true_label:10s} pred={predicted:10s} ✓")
        else:
            confusion[true_label][predicted] += 1
            wrong.append((true_label, predicted, text[:60]))
            print(f"[{i:02d}] true={true_label:10s} pred={predicted:10s} ✗  {text[:50]}…")

    hit_rate = correct / total * 100
    null_rate = null_count / total * 100

    print("\n" + "=" * 60)
    print(f"ERGEBNIS: {correct}/{total} korrekt = {hit_rate:.1f}% Trefferquote")
    print(f"          {null_count}/{total} kein Ergebnis (null) = {null_rate:.1f}%")
    print()

    # Per-Klasse Precision/Recall
    print("── Per-Klasse ──────────────────────────────────────────")
    for label in ["werte", "stories", "konflikte"]:
        tp = confusion[label][label]
        fn = sum(v for k, v in confusion[label].items() if k != label)
        fp = sum(
            confusion[other][label] for other in ["werte", "stories", "konflikte"] if other != label
        )
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        print(
            f"  {label:12s}: precision={precision:.0%}  recall={recall:.0%}  (TP={tp}, FP={fp}, FN={fn})"
        )

    print()
    print("── Confusion Matrix ────────────────────────────────────")
    headers = ["werte", "stories", "konflikte", "<null>"]
    print(f"  {'true\\pred':12s}", "  ".join(f"{h:10s}" for h in headers))
    for label in ["werte", "stories", "konflikte"]:
        row = "  ".join(f"{confusion[label].get(h, 0):10d}" for h in headers)
        print(f"  {label:12s} {row}")

    if wrong:
        print()
        print("── Falsch klassifizierte Chunks ────────────────────────")
        for true_label, pred, preview in wrong:
            print(f"  [{true_label} → {pred}] {preview}…")

    print()
    if hit_rate >= 80:
        print(f"✅ M16 GRÜN: Trefferquote {hit_rate:.1f}% ≥ 80%")
    else:
        print(f"❌ M16 ROT: Trefferquote {hit_rate:.1f}% < 80% — Fix-Issue nötig")

    return hit_rate, confusion, wrong


if __name__ == "__main__":
    hit_rate, confusion, wrong = asyncio.run(run_eval())
    sys.exit(0 if hit_rate >= 80 else 1)
