# Thailand 2027 – Flugpreis-Suche und E-Mail-Alarm

Erweiterung zum bestehenden Bambu-Lab-Preisalarm. **Bambu-Dateien und -Workflows bleiben unverändert.**

## Reisekriterien
- **2 Erwachsene + 2 Kinder**, Economy, Ziel Bangkok (BKK).
- Abflug **06.–14.08.2027**, bevorzugt **10.08.2027**, Dauer **16–18 Kalendertage** einschließlich beider Flugtage.
- Startflughäfen **DUS, FRA, CGN, AMS**. Maximal **1 Stopp je Richtung** und **22 Stunden pro Richtung**.
- Gewichteter Score: **Preis 40 %, Reisedauer 20 %, Anfahrt 10 %, Komfort 15 %, Reisedatum 15 %**.
- E-Mail bei Gesamtpreis-Indikator ≤ **2.800 €** und Score ≥ 65 oder ≤ **3.300 €** und Score ≥ 82.
- Der Vergleichspreis bezieht sich auf **alle vier Reisenden** in der Suchmaske. Angaben zu Aufgabegepäck, Sitzplätzen und finaler Buchbarkeit gesondert verifizieren.

## Installation
1. Erstelle einen SerpApi-Zugang unter https://serpapi.com/. Die API für Google Flights unterstützt mehrere Startflughäfen und vier Reisende; siehe https://serpapi.com/google-flights-api. **SerpApi ist ein Drittanbieter und kann kostenpflichtig werden.**
2. In GitHub **Settings → Secrets and variables → Actions** zwei **Repository secrets** setzen:
   - \`SERPAPI_API_KEY\`: persönlicher SerpApi API-Key.
   - \`FLIGHT_MAIL_TO\`: E-Mail-Empfänger (mehrere Adressen mit Kommas).
   - Das bestehende \`SMTP_PASSWORD\` für den Bambu-Preisalarm wird wiederverwendet.
3. Im Reiter **Actions** den Workflow **Thailand Flugpreis-Alarm** einmal mit **Run workflow** starten.
4. Im GitHub Actions Log die Zahl der Suchanfragen und Treffer prüfen; die Datei \`fluege.json\` steckt im Artefakt \`thailand-flugbericht\`.
5. Über \`kriterien.html\` die fünf Gewichte, Wunschdaten, Flughäfen und Preise einstellen; dort **JSON herunterladen** und anschließend \`flugalarm_config.json\` im Repository mit dieser Datei ersetzen. Das Bearbeiten der HTML-Datei allein verändert den Workflow **nicht**.

## Datenquelle und Abdeckung
Die ursprünglich vorgeschlagene **Amadeus Self-Service-API wurde am 17. Juli 2026 eingestellt**. Diese Erweiterung verwendet stattdessen **SerpApi Google Flights**. Damit besteht eine Abhängigkeit von einer externen, ggf. kostenpflichtigen API. Ohne \`SERPAPI_API_KEY\` stoppt der Workflow mit einem klaren Fehler; es werden niemals fiktive Preise erzeugt.

Google Flights liefert erst die Hinflugliste und dann – mit einem \`departure_token\` – Rückflüge. Je Datums-Kombination werden **maximal zwei API-Abfragen** gemacht: Die preis-/zeitlich vielversprechendste Hinflugoption wird zur Rückflugsuche verwendet. Das spart API-Calls, kann aber günstigere alternative Hinflüge übersehen.

**Voreinstellung: 4 Datumskombinationen pro Tag**. Die 9 möglichen Abflugtage × 3 Reisedauern ergeben 27 Datumskombinationen; die Auswahl rotiert im Wochenrhythmus. **Alle vier Startflughäfen werden in einer Google-Flights-Abfrage gemeinsam angefragt**, wodurch nicht garantiert ist, dass jede einzelne Fluggesellschaft und jeder Startflughafen vollständig abgedeckt werden.

Rechnerisches Maximum: **8 API-Aufrufe/Tag ≈ 240/30 Tage** (ggf. weniger, falls keine Hinflüge zurückkommen). Das Kontingent und aktuelle Preise des API-Anbieters vor Aktivierung prüfen; 250 Suchanfragen/Monat reichen nur knapp. Je nach Tarif sind zu viele Anfragen kostenpflichtig oder werden blockiert.

## Alarm und technische Grenzen
- Flugpreise sind **Suchindikatoren**, keine garantierten Buchungspreise. Endpreis für 4 Personen einschließlich Kinderalter, Gepäck und Sitzplatzreservierungen **direkt beim Anbieter überprüfen**.
- Ermittlung der Sitzplatzgarantie ist nicht automatisiert; deshalb wird ein geschätzter Zuschlag von 190 € bei der Bewertung angesetzt. Die Anzeige kann die genauen Sitzplatzbedingungen der Airline nicht bestätigen.
- Der Preis in der E-Mail basiert auf der über die API ausgewählten **Hin-/Rückflug-Kombination**. Kinderpreise und Gepäckdetails müssen an der finalen Buchungsseite verifiziert werden.
- Bewertung enthält editierbare **Schätzwerte für die Anfahrt aus Neuss**; sie sind keine Live-Tarife.
- In der JSON-Ausgabe stehen Preis, Score, Teil-Scores, Datum und die Flugsegmente.
- Eine E-Mail wird nur bei **neuen oder mindestens 30 € günstigeren** Treffern gesendet. Der letzte Meldungszustand liegt im GitHub-Actions-Cache (nicht garantiert dauerhaft).
- GitHub Actions cron läuft ungefähr um **08:15 Uhr deutscher Zeit**, kann verspätet starten und sich bei inaktiven öffentlichen Repositories deaktivieren.
- Der Workflow verändert den bestehenden Bambu-Preisalarm nicht.

## Offline-Tests
\`\`\`bash
python -m unittest discover -s tests -p 'test_flugalarm.py' -v
\`\`\`

## Datenquellen
- https://serpapi.com/google-flights-api
- https://developers.amadeus.com/api-catalog (Hinweis zur Einstellung von Self-Service)
