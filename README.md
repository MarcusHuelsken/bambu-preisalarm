# Bambu Lab H2S Laser Full Combo 10W Preisalarm

**Projektstand: v1.3.3** · Python 3.11+ · keine externen Python-Abhängigkeiten.

Der Monitor prüft ausschließlich Angebote für den **Bambu Lab H2S Laser Full Combo 10W**. Andere Varianten (insbesondere 40W, Upgrades und einzelne Module) sollen nicht als Treffer gelten.

## Preisquellen und Grenzen

Seit v1.3.3 werden Händler-Produktseiten von **reichelt elektronik**, **IGO3D** und **Polyfab3D** geprüft. Der frühere Shopify-Katalog enthielt das gesuchte Modell bei den untersuchten Abrufen nicht. Die neue Händlererkennung muss im echten GitHub-Actions-Lauf weiter validiert werden; erfolgreiche Offline-Tests belegen keinen erfolgreichen Live-Preisabruf.

Der Monitor darf keine Versandkosten, Rabatte, Mehrwertsteuer oder Endpreise erfinden. Fehlt eine belastbare Angabe, bleibt sie unbekannt. Die angezeigten Angebote sind nicht automatisch verifizierte Checkout-Endpreise.

Optional können manuell geprüfte Händlerangebote in `offers.json` eingetragen werden: `name`, `merchant`, `link`, `price_eur`, `shipping_eur`, `discount_eur`, `available`, `verified_on` (ISO-Datum, höchstens zwei Tage alt). Unbekannte Versandkosten bedeuten: kein gesicherter Endpreis.

## Ausführen und testen

```powershell
python -m py_compile preischeck.py test_preischeck.py
python -m unittest discover -p 'test_*.py' -v
python preischeck.py
```

Der letzte Befehl führt einen echten Internetabruf aus. Diagnoseberichte werden im Ordner `output/` gespeichert. Die Namen der Berichtsdateien richten sich nach der jeweiligen Skriptversion.

Die GitHub Action in `.github/workflows/preisalarm.yml` läuft täglich um **08:00 Uhr Europe/Berlin** (zwei UTC-Zeitpläne mit Ortszeitprüfung) und kann manuell gestartet werden. Berichte werden auch bei einem fehlgeschlagenen Preisabruf als GitHub-Actions-Artefakt bereitgestellt.

## E-Mail und Secrets

Unter **GitHub → Repository → Settings → Secrets and variables → Actions** muss das Secret `SMTP_PASSWORD` hinterlegt sein. Die übrigen SMTP-Parameter sind im Workflow konfiguriert. **Niemals Passwörter oder Personal Access Tokens in Commits, Issues, Pull Requests oder Chats veröffentlichen.**

## Zusammenarbeit und Pull Requests

Das Repository wird lokal in **Visual Studio Code** verwaltet und ist mit GitHub verbunden. Der gewünschte Entwicklungsablauf ist:

1. ChatGPT erstellt Änderungen auf einem separaten Feature-Branch, ergänzt Tests und Dokumentation.
2. ChatGPT eröffnet einen Pull Request gegen `main` und beschreibt Änderungen, Tests sowie verbleibende Risiken.
3. **Der Repository-Eigentümer übernimmt Review und Merge.** ChatGPT führt keinen automatischen Merge nach `main` aus.

Für direkte GitHub-Schreibaktionen benötigt die ChatGPT-GitHub-Integration eigene Repository-Schreibrechte. Ein lokal eingerichteter `GITHUB_TOKEN` ist nicht automatisch für ChatGPT zugänglich. Eine frühere GitHub-Verbindung verweigerte Branch-Erstellung mit HTTP 403; nach erneuter Autorisierung muss der Schreibzugriff durch einen tatsächlichen Branch-/PR-Vorgang bestätigt werden.

## Versions- und Dateinamensregel

**Versionsnummern stehen nur innerhalb der Dateien**, nicht in Dateinamen. Beispielsweise bleiben `preischeck.py`, `test_preischeck.py`, `README.md` und `.github/workflows/preisalarm.yml` unverändert benannt. Git übernimmt die Versionshistorie. Bei Updates werden möglichst nur tatsächlich geänderte Dateien geliefert.

## Bekannte offene Punkte

- Live-Preisabruf für das exakte 10W-Modell zuverlässig nachweisen.
- Fehlende oder mehrdeutige Händlerpreise im Diagnosebericht verständlich ausweisen.
- Änderungen ausschließlich über Pull Requests reviewen und nach Freigabe mergen.
