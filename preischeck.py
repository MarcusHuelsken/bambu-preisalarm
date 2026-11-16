#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bambu Lab Preisalarm – Version 1.2.0.

Erfasst öffentlich verfügbare EUR-Preise im offiziellen Bambu-Lab-EU-Shop.
Kein Preis wird aus einer Fehlerseite geschätzt. Python-Standardbibliothek.
"""

VERSION = "1.2.0"

import datetime as dt
import html
import json
import os
from pathlib import Path
import re
import smtplib
import ssl
import sys
import urllib.error
import urllib.request
from email.message import EmailMessage
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

BASE = "https://eu.store.bambulab.com"
OUT = Path("output")
CACHE = Path(".cache/preise.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}
MODEL = re.compile(r"(?i)(?:\bA1\b|A1\s*mini|\bP1[PS]\b|\bP2S\b|\bX1[CE]?\b|X1.Carbon|\bX2D\b|\bH2[SDC]\b|\bH3C\b)")
NOT_PRINTER = re.compile(r"(?i)(nozzle|hotend|extruder|build plate|filament|refill|spool|motor|cable|toolhead|accessor|spare part|replacement|maintenance|connector|adapter|laser module only|standalone laser)")


def read_url(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=22) as response:
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")
        return response.read(6_000_000).decode("utf-8", "replace")


def is_printer(name):
    return bool(MODEL.search(name)) and not bool(NOT_PRINTER.search(name))


def catalogue(errors):
    """Shopify product JSON: Preise als Cent-Betrag, keine USD->EUR-Annahme."""
    candidates = (
        f"{BASE}/collections/3d-printer/products.json?limit=250",
        f"{BASE}/collections/3d-printers/products.json?limit=250",
        f"{BASE}/de/collections/3d-printer/products.json?limit=250",
        f"{BASE}/products.json?limit=250",
        "https://bambulab-eu.myshopify.com/collections/3d-printer/products.json?limit=250",
    )
    for url in candidates:
        try:
            data = json.loads(read_url(url))
            products = data.get("products")
            if not isinstance(products, list) or not products:
                raise ValueError("Katalog leer oder ungültig")
            print(f"Katalog erreichbar: {url}, Produkte: {len(products)}")
            result = []
            for product in products:
                if not isinstance(product, dict):
                    continue
                name = str(product.get("title") or "")
                if not is_printer(name):
                    continue
                handle = str(product.get("handle") or "")
                if not handle:
                    continue
                for variant in product.get("variants") or []:
                    if not isinstance(variant, dict):
                        continue
                    raw_price = variant.get("price")
                    try:
                        # Shopify JSON values are normally numeric cent amounts.
                        cents = int(raw_price)
                    except (ValueError, TypeError):
                        continue
                    if not 5000 <= cents <= 1_500_000:
                        continue
                    variant_name = str(variant.get("title") or "")
                    label = name if variant_name.lower() in ("default title", "") else f"{name} – {variant_name}"
                    if NOT_PRINTER.search(label):
                        continue
                    variant_id = str(variant.get("id") or "")
                    product_url = f"{BASE}/en/products/{handle}"
                    if variant_id.isdigit():
                        product_url += f"?variant={variant_id}"
                    result.append({
                        "id": f"{handle}:{variant_id or variant_name}",
                        "name": label,
                        "cents": cents,
                        "available": variant.get("available"),
                        "url": product_url,
                        "laser": "laser" in label.lower(),
                        "source": url.split("?")[0],
                    })
            if result:
                return result
            errors.append(f"{url}: Keine erkannten Druckervarianten")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:90]}")
    return []


class StructuredDataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_jsonld = False
        self.parts = []
        self.blocks = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type", "").lower() == "application/ld+json":
            self.in_jsonld = True
            self.parts = []

    def handle_data(self, data):
        if self.in_jsonld:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.in_jsonld:
            self.blocks.append("".join(self.parts))
            self.in_jsonld = False


def jsonld_nodes(value):
    if isinstance(value, list):
        for entry in value:
            yield from jsonld_nodes(entry)
    elif isinstance(value, dict):
        yield value
        if "@graph" in value:
            yield from jsonld_nodes(value["@graph"])


def parse_eur(amount):
    try:
        value = float(str(amount).strip().replace(".", "").replace(",", ".")) if "," in str(amount) else float(amount)
        if 50 <= value <= 15000:
            return round(value * 100)
    except (ValueError, TypeError):
        pass
    return None


def product_page_fallback(errors):
    """Read structured product offers from known official EU product pages."""
    slugs = ("a1-mini", "a1", "p1s", "p2s", "x1-carbon", "h2s", "h2d", "h2c", "x2d")
    found = []
    for slug in slugs:
        url = f"{BASE}/en/products/{slug}"
        try:
            page = read_url(url)
            parser = StructuredDataParser()
            parser.feed(page)
            for block in parser.blocks:
                try:
                    data = json.loads(block)
                except ValueError:
                    continue
                for item in jsonld_nodes(data):
                    types = item.get("@type", [])
                    if isinstance(types, str):
                        types = [types]
                    if not any(str(t).lower() in ("product", "productgroup") for t in types):
                        continue
                    name = str(item.get("name") or slug)
                    if not is_printer(name):
                        continue
                    offers = item.get("offers") or []
                    if isinstance(offers, dict):
                        offers = [offers]
                    for n, offer in enumerate(offers):
                        if not isinstance(offer, dict) or str(offer.get("priceCurrency", "")).upper() != "EUR":
                            continue
                        cents = parse_eur(offer.get("price"))
                        if cents is None:
                            continue
                        found.append({
                            "id": f"{slug}:jsonld:{n}", "name": name,
                            "cents": cents, "available": "instock" in str(offer.get("availability", "")).lower(),
                            "url": url, "laser": "laser" in name.lower(), "source": "JSON-LD der Produktseite",
                        })
        except (OSError, ValueError) as exc:
            errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:90]}")
    return found


def euro(cents):
    return f"{cents / 100:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") + " €"


def prior_prices():
    try:
        values = json.loads(CACHE.read_text(encoding="utf-8"))
        return values if isinstance(values, dict) else {}
    except (OSError, ValueError):
        return {}


def mail_report(body, date):
    needed = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM", "MAIL_TO")
    missing = [key for key in needed if not os.getenv(key)]
    if missing:
        print("E-Mail noch nicht eingerichtet; fehlende GitHub-Secrets:", ", ".join(missing))
        return
    msg = EmailMessage()
    msg["Subject"] = f"Bambu Lab Preischeck {date} (v{VERSION})"
    msg["From"] = os.environ["MAIL_FROM"]
    msg["To"] = os.environ["MAIL_TO"]
    msg.set_content("Der HTML-Teil dieser Nachricht enthält den Bambu-Lab-Preisbericht.")
    msg.add_alternative(body, subtype="html")
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT") or "465")
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as server:
            server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            server.send_message(msg)
    elif port == 587:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls(context=ssl.create_default_context())
            server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            server.send_message(msg)
    else:
        raise ValueError("SMTP_PORT muss 465 oder 587 sein")
    print("E-Mail erfolgreich versendet.")


def main():
    print(f"Bambu Lab Preisalarm – Version {VERSION}")
    now = dt.datetime.now(ZoneInfo("Europe/Berlin"))
    date = now.strftime("%d.%m.%Y %H:%M")
    errors = []
    rows = catalogue(errors)
    if not rows:
        print("Katalog ohne verwertbare Daten; versuche Produktseiten-JSON-LD.")
        rows = product_page_fallback(errors)
    # Deduplicate by stable identity.
    products = {row["id"]: row for row in rows}
    entries = sorted(products.values(), key=lambda row: (row["cents"], row["name"]))
    previous = prior_prices()
    OUT.mkdir(parents=True, exist_ok=True)
    data = {
        "version": VERSION, "checked_at": now.isoformat(),
        "products": entries, "errors": errors,
    }
    (OUT / "preise.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tr = []
    for entry in entries:
        old = previous.get(entry["id"])
        delta = entry["cents"] - old if isinstance(old, int) else None
        change = "Erstaufnahme" if delta is None else "unverändert" if delta == 0 else (("−" if delta < 0 else "+") + euro(abs(delta)))
        availability = "ja" if entry["available"] is True else "nein" if entry["available"] is False else "unbekannt"
        cells = [entry["name"], euro(entry["cents"]), change, availability, "ja" if entry["laser"] else "nicht ausgewiesen"]
        tr.append("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in cells) + f'<td><a href="{html.escape(entry["url"], quote=True)}">Shop</a></td></tr>')
    body = (f"<h2>Bambu Lab Preisalarm – v{VERSION}</h2>"
            f"<p>Stand: {date} (Europe/Berlin). Offizieller EU-Shop. {len(entries)} Varianten mit auslesbarem EUR-Preis.</p>"
            "<p>Shoppreise sind Momentaufnahmen ohne garantierte Versandkosten. "
            "Preisänderungen sind nur mit einem gespeicherten Vorlaufwert vergleichbar. "
            "Die aktuelle GitHub-Workflow-Datei speichert den Verlauf noch nicht dauerhaft.</p>"
            "<table border='1' cellpadding='5'><tr><th>Modell/Variante</th><th>Preis</th><th>Änderung</th><th>Verfügbar</th><th>Laser</th><th>Link</th></tr>"
            + "".join(tr) + "</table>")
    if errors:
        body += "<p><strong>Quellenhinweise:</strong> " + html.escape("; ".join(errors)[:1800]) + "</p>"
    if not entries:
        body += "<p><strong>Fehler: Keine verlässlichen EUR-Preise abrufbar.</strong></p>"
    (OUT / "bericht.html").write_text("<!doctype html><html lang='de'><meta charset='utf-8'><body>" + body + "</body></html>", encoding="utf-8")
    if not entries:
        print("FEHLER: Keine EUR-Preise abrufbar; Details in output/preise.json")
        sys.exit(1)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({x["id"]: x["cents"] for x in entries}, indent=2), encoding="utf-8")
    print(f"Erfolg: {len(entries)} Varianten. Bericht in output/bericht.html")
    mail_report(body, date)


if __name__ == "__main__":
    main()
