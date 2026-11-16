# Bambu Lab Preisalarm

Automatischer täglicher Preischeck für im offiziellen Bambu-Lab-EU-Shop abrufbare Modellvarianten. Startet mit der Python-Standardbibliothek, ohne kostenpflichtige APIs.

## Einrichtung

1. Dateien dieses ZIP-Archivs in das öffentliche GitHub-Repository hochladen (auch den Ordner `.github/workflows`).
2. Unter **Settings → Secrets and variables → Actions → New repository secret** folgende Secrets anlegen: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`.
3. `SMTP_HOST` und `SMTP_PORT` dem E-Mail-Anbieter bzw. den Outlook-Kontoeinstellungen entnehmen. `SMTP_USER` und `MAIL_FROM` sind üblicherweise `Marcus.Huelsken@online.de`. Passwort ausschließlich als GitHub-Secret hinterlegen, nicht in Dateien oder Chat-Nachrichten.
4. Unter **Actions → Bambu Lab Preisalarm → Run workflow** einen Testlauf starten.

Die E-Mail geht an `marcus.huelsken@online.de` und `sarah.huelsken@online.de`.

## Grenzen

- Aktuell werden nur öffentliche Bambu-Lab-EU-Shop-Produktendpunkte geprüft, **keine** Drittanbieter. Nicht abrufbare Modelle werden als solche protokolliert.
- Das Script speichert einen aktuellen Bericht (JSON + HTML) in den GitHub-Actions-Artefakten. Es enthält noch **keinen historischen Preisvergleich**.
- Die GitHub-Actions-Zeitplanung basiert auf UTC. Die Vorlage läuft um 07:00 UTC: 08:00 Uhr im Winter, 09:00 Uhr im Sommer. Für ganzjährige 08:00 Uhr in Deutschland ist eine zusätzliche Zeitzonenlösung nötig.
- GitHub kann geplante Runs verzögern, außerdem können inaktiven öffentlichen Repositories geplante Workflows deaktiviert werden.
