# Bambu H2S Laser Full Combo 10W Preisalarm v1.3.2

## Zweck
Diagnose-Update für fehlgeschlagenen Live-Abruf vom 18.11.2026. Das Update behebt **nicht nachweislich** den fehlenden Live-Preis, sondern macht HTTP-Fehler und tatsächlich gelieferte Produkttitel im Workflow-Protokoll sichtbar. Es werden keine Preise erfunden.

## Installation
Die Dateien im Ordner `github-upload/` mit den **festen GitHub-Dateinamen** im Repository ersetzen. Diese festen Namen sind nötig, weil GitHub Actions `preischeck.py` und `test_preischeck.py` aufruft. Alle Release-Dateien im ZIP-Hauptordner sind zusätzlich mit `v1.3.2` gekennzeichnet.

## Test
GitHub → Actions → Bambu H2S Laser 10W Preisalarm v1.3.2 → Run workflow. Bei Fehlschlag den Schritt `Preise pruefen und E-Mail senden` öffnen. Dort stehen jetzt `DIAGNOSE` und `ABRUF-FEHLER`. Das Artefakt `h2s-laser-preisbericht_v1.3.2` enthält `preise_v1.3.2.json` und `bericht_v1.3.2.html`.

## Sicherheit und Grenzen
Nur H2S Laser Full Combo 10W. Versand unbekannt, solange nicht verifiziert. Offline-Tests beweisen keinen Live-Shopzugriff. SMTP-Konfiguration und GitHub-Secret `SMTP_PASSWORD` bleiben unverändert. Keine OpenAI API, keine zusätzlichen KI-Kosten.
