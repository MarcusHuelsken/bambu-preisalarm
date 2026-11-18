# Bambu Lab H2S Laser Full Combo 10W Preisalarm v1.3.1

Python 3.11+; keine externen Python-Abhängigkeiten. Nur H2S Laser Full Combo 10W.

- `python -m py_compile preischeck.py test_preischeck.py`
- `python -m unittest discover -p 'test_*.py' -v`
- `python preischeck.py` (echter Shopabruf, Internet erforderlich)

Die Daten werden in `output/preise.json` und `output/bericht.html` gespeichert.
Die GitHub Action startet täglich um 08:00 Uhr Europe/Berlin (zwei UTC-Crons mit Ortszeitfilter) sowie manuell.

Für E-Mail ist im Workflow die bisherige SMTP-Konfiguration erhalten. Unter GitHub Settings > Secrets and variables > Actions muss `SMTP_PASSWORD` als Secret hinterlegt sein. Andere SMTP-Werte können bei Bedarf ebenfalls in Secrets ausgelagert werden.
**Keine Passwörter oder E-Mail-Adressen in öffentliche Workflow-Dateien schreiben.**

Optional `offers.json`: JSON-Liste mit `name`, `merchant`, `link`, `price_eur`, `shipping_eur`, `discount_eur`, `available`, `verified_on` (ISO-Datum, höchstens zwei Tage alt). Nur nach realer Einzelprüfung eintragen. Fehlende Versandkosten führen zu unbekanntem Endpreis.

Shopify-Katalogwerte sind keine nachgewiesenen Checkout-Endpreise. Offline-Tests verwenden fiktive Testwerte, keine realen Marktpreise. Bei fehlenden Angeboten wird der Workflow als Fehler beendet und das Diagnoseartefakt trotzdem hochgeladen.
