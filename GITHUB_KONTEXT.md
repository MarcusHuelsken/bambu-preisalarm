# GitHub-Projektkontext – bambu-preisalarm

> Stand: 18. November 2026. Arbeitsnotiz für neue ChatGPT-Unterhaltungen und Mitwirkende. Bei Widersprüchen ist der aktuelle Repository- und Actions-Stand maßgeblich. Keine Zugangsdaten oder Secrets hier speichern.

## Repository und Ziel

- Repository: https://github.com/MarcusHuelsken/bambu-preisalarm
- Lokaler Arbeitsordner des Nutzers (Windows / VS Code): `C:\Projekte\bambu-preisalarm`
- Python-Preisalarm für das **Bambu H2S Laser Full Combo 10W**; verifizierte Live-Händlerpreise statt erfundener oder nicht eindeutig zuordenbarer Preise.
- Bekannte Händler: reichelt elektronik, IGO3D und Polyfab3D.
- Hauptdateien: `preischeck.py`, `test_preischeck.py`, `.github/workflows/preisalarm.yml`, `.github/workflows/codex-auto-repair.yml`, `.github/scripts/verify_live.py`.
- Versionsnummern gehören **in den Dateiinhalt**, nicht in Dateinamen.

## Gewünschte Zusammenarbeit

- **Strikt sequenziell:** immer nur den nächsten Schritt nennen; keine nachträglichen „aber vorher“-Anweisungen.
- Der Assistent übernimmt möglichst alle GitHub-Arbeiten selbst: Änderungen, Prüfungen, Branches und Pull Requests.
- **Nur der Nutzer prüft und mergt Pull Requests.** Niemals automatisch mergen.
- Keine lokalen Git-Befehle oder Secret-Werte vom Nutzer verlangen, wenn GitHub-Tools die Aufgabe übernehmen können.
- Kommunikation auf Deutsch, direkt, gerne mit etwas trockenem Humor.
- Erledigte Einstellungen nicht erneut als Aufgabe präsentieren.

## GitHub-Konfiguration (vom Nutzer bestätigt)

- `OPENAI_API_KEY` ist als GitHub Actions Secret hinterlegt; Wert niemals auslesen oder dokumentieren.
- GitHub Actions besitzt Schreibrechte und darf Pull Requests erstellen.
- Repository-Variable `ENABLE_CODEX_AUTOREPAIR` wurde zunächst auf `false` angelegt und am 18.11.2026 vom Nutzer auf **`true`** gestellt.
- Der Nutzer hat den ersten `workflow_dispatch`-Lauf manuell gestartet.

## Wichtige Pull Requests

- [PR #1](https://github.com/MarcusHuelsken/bambu-preisalarm/pull/1): README-/Automatisierungsdokumentation, bei der letzten Prüfung offen.
- [PR #2](https://github.com/MarcusHuelsken/bambu-preisalarm/pull/2): Codex-Autoreparatur und strikter Live-Preis-Verifizierer, **gemergt**.
- [PR #3](https://github.com/MarcusHuelsken/bambu-preisalarm/pull/3): Offline-Snapshots der Händlerseiten für Codex und fehlertolerante Codex-Versuche, **gemergt**.
- Entwicklungsbranch `fix/live-price-validation`: Diagnose der Preisextraktion; zuletzt sechs Unit-Tests erfolgreich, Live-Validierung gescheitert. Kein PR ohne erfolgreichen Live-Nachweis.

## Codex-Autoreparatur

Workflow: `.github/workflows/codex-auto-repair.yml`

- Manuell startbar und täglich um 09:15 UTC geplant.
- Nur aktiv bei `ENABLE_CODEX_AUTOREPAIR == 'true'`.
- Prüft Unit-Tests, den echten Preischeck und `.github/scripts/verify_live.py`.
- Codex darf nur `preischeck.py` und `test_preischeck.py` bearbeiten.
- Bis zu drei Reparaturversuche; Händlerseiten werden zuvor lokal unter `.cache/retailer-pages/` gespeichert, da das verwendete Codex-Profil keinen direkten Netzwerkzugriff erlaubt.
- Bei verifiziertem Patch soll ein separater Job einen **Review-PR** erzeugen. Kein Auto-Merge.
- Der Verifizierer verlangt mindestens ein Angebot mit `Live JSON-LD`, bekanntem Händler, Bruttopreis, HTTPS-Link und Hinweis auf das 10W-Modell. Versandkosten können unbekannt bleiben.

## Erster echter Lauf – wichtiger offener Fehler

[GitHub Actions Lauf #1 / Run 44408323860](https://github.com/MarcusHuelsken/bambu-preisalarm/actions/runs/44408323860) wurde am 18.11.2026 manuell gestartet und ist **fehlgeschlagen**.

- `repair`-Job endete laut GitHub erfolgreich, aber die Freigabe-/Patch-Schritte (`Reject unauthorized file changes`, `Export patch`, `upload-artifact`) wurden **übersprungen**.
- `publish`-Job startete trotzdem und scheiterte beim `download-artifact`, weil kein `verified-repair-patch` vorlag.
- **Bekannter Workflow-Bug:** `publish` ist allein an `needs.repair.result == 'success'` gekoppelt. Das ist zu schwach. Er muss zusätzlich nur starten, wenn wirklich ein geprüfter Patch hochgeladen wurde (z. B. über explizites Job-Output).
- **Weiterer Prüfpunkt:** Die Shell-Kommandos der Verifikationsschritte benötigen `set -e` oder eine vergleichbare strikte Fehlerbehandlung, damit ein fehlgeschlagener Unit-Test bzw. Preischeck nicht durch einen nachfolgenden erfolgreichen Befehl verdeckt wird.
- Aus dem ersten Lauf folgt **kein** bestätigter Live-Preis und **kein** erfolgreicher Reparatur-PR.
- Nächste technische Aufgabe: Fehler in eigenem Branch beheben, prüfen und Review-PR erstellen; Nutzer mergt selbst.

## Quellen / Verifikation

Diese Datei ist eine Momentaufnahme, keine automatisch aktualisierte globale ChatGPT-Memory. Neue Chats können sie über ihren GitHub-Link lesen, sofern der Zugriff verfügbar ist. Vor konkreten Änderungen immer den aktuellen Stand auf GitHub prüfen.
