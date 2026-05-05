# ADR-0002: Throttle als Defense-in-Depth-Layer

## Status

Akzeptiert (2026-05-04)

## Kontext

Im April 2026 wurde eine 32-Millionen-Token-Anomalie entdeckt (Issue #125). Der vorhandene Cost-Cap (Issue #123, 5 USD/Tag/Tenant) hatte den finanziellen Schaden begrenzt — aber erst nachdem die Kosten bereits aufgelaufen waren. Der Cost-Cap ist ein reaktiver "stop-after-cost"-Mechanismus: Er schreibt einen Throttle-Event erst wenn das Budget ueberschritten wurde.

Das Anomalie-Fenster (Zeit zwischen erstem ungewoehnlichen Call und Cap-Eingriff) kann bei aggressivem Batching trotzdem mehrere Dollar und Dutzende API-Calls umfassen. Ausserdem schutzt Cost-Cap nicht vor Rate-Abuse (viele billige Calls).

## Entscheidung

Ein zusaetzlicher Throttle-Layer wird als Defense-in-Depth eingezogen (Issue #156). Er operiert **vor** dem LLM-Call:

- **Per-Tenant-Throttle:** max. N Requests/Minute pro Tenant (konfigurierbar, Default 30 req/min)
- **Global-Throttle:** max. M Requests/Minute ueber alle Tenants (Default 200 req/min)
- **Advisory-Lock-Haertung:** Jeder Throttle-Check haelt einen Pg-Advisory-Lock fuer die Dauer der Pruefung, um TOCTOU-Race-Conditions zu vermeiden
- **Throttle-Events-Tabelle:** Jeder Block wird in `throttle_events` mit Scope, Tenant-ID und Timestamp eingetragen (Audit + Purge-Runbook)

Der Cost-Cap bleibt als zweite Verteidigungslinie erhalten.

## Konsequenzen

**Positiv:**
- "Stop-before-cost" statt "stop-after-cost" — Anomalie-Fenster deutlich kleiner
- Schutz auch gegen Rate-Abuse (billige Spam-Calls) die Cost-Cap nicht triggern wuerden
- Throttle-Events sind auditierbar und purge-faehig

**Negativ:**
- `throttle_events`-Tabelle waechst bei hohem Traffic; Purge-Runbook noetig (siehe `docs/runbooks/RUNBOOK-throttle-events-purge.md`)
- Advisory-Lock-Overhead pro LLM-Call (~1-2ms bei niedriger Contention)

**Neutral:**
- Cost-Cap-Logik unveraendert — kein Regressions-Risiko auf bestehende Cost-Alerts

## Alternativen die verworfen wurden

**Cost-Cap-Reduzierung (z.B. auf 1 USD/Tag):** Haette das Anomalie-Fenster verkleinert, aber legitime Burst-Nutzung (z.B. Wizard-Onboarding mit vielen Pipeline-Schritten) geblockt. Kundenfrustration waere das Ergebnis gewesen, nicht bessere Sicherheit.

**Redis-basiertes Rate-Limiting (Token-Bucket):** Waere schneller als Pg-Advisory-Locks, fuehrt aber eine zweite kritische Infrastrukturkomponente in den Sicherheitspfad ein. Wenn Redis kurz ausfaellt, waere kein Throttling aktiv. PostgreSQL als Single-Source-of-Truth ist robuster fuer diesen Use-Case.
