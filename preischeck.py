#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bambu Lab EU Preisalarm v1.2.2.

Recherchiert Preise aus öffentlich abrufbaren EU-Shopdaten. Liefert immer einen
Diagnosebericht; erfindet keine Preise. Standardbibliothek, Python >= 3.11.
"""

VERSION = "1.2.2"

import datetime as dt
import html
import json
import os
import re
import smtplib
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

SHOP = "https://eu.store.bambulab.com"
OUT = Path("output")
CACHE = Path(".cache/preise.json")
MAX_BYTES = 6_000_000
MODELS = re.compile(r"(?i)\b(?:A1\s*mini|A1|P1P|P1S|P2S|X1(?:C|E)?|X1\s*Carbon|H2[SDC]|X2D)\b")
NOT_PRINTER = re.compile(
    r"(?i)(?:nozzle|hotend|extruder|build\s*plate|filament|refill|spool|"
    r"accessor|spare\s*part|replacement|cable|adapter|motor|"
    r"laser\s*module\s*only|maintenance|connector)"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}
CANDIDATES = [
    f"{SHOP}/de/collections/3d-printer/products.json?limit=250",
    f"{SHOP}/collections/3d-printer/products.json?limit=250",
    f"{SHOP}/products.json?limit=250",
    "https://bambulab-eu.myshopify.com/collections/3d-printer/products.json?limit=250",
]
SLUGS = ["a1-mini", "a1", "p1s", "p2s", "x1-carbon", "h2s", "h2d", "h2c", "x2d"]


def request_text(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=22) as response:
        content = response.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise ValueError("Antwort ist zu groß")
        return content.decode("utf-8", "replace"), response.geturl()


def model_name(title):
    return bool(MODELS.search(title)) and not bool(NOT_PRINTER.search(title))


def euro_cents_from_shopify(value):
    """Shopify /products.json traditionally returns integer minor units (cents).

    Reject non-integers because JSON forms with decimal prices are ambiguous.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        cents = value
    elif isinstance(value, str) and value.isdigit():
        cents = int(value)
    else:
        return None
    return cents if 5_000 <= cents <= 2_000_000 else None


def euro_cents_from_decimal(value):
    if isinstance(value, bool) or value is None:
        return None
    s = str(value).strip().replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        amount = float(s)
    except ValueError:
        return None
    return round(amount * 100) if 50 <= amount <= 20_000 else None


def parse_shopify(data, source, diagnostic):
    products = data.get("products") if isinstance(data, dict) else None
    if not isinstance(products, list):
        raise ValueError("JSON enthält keine Produktliste")
    diagnostic.append({"source": source, "count": len(products), "titles": [str(p.get("title", ""))[:90] for p in products[:15] if isinstance(p, dict)]})
    entries = []
    for prod in products:
        if not isinstance(prod, dict):
            continue
        title = str(prod.get("title") or "")
        if not model_name(title):
            continue
        handle = str(prod.get("handle") or "")
        variants = prod.get("variants")
        if not handle or not isinstance(variants, list):
            continue
        for v in variants:
            if not isinstance(v, dict):
                continue
            variant_name = str(v.get("title") or "")
            label = title if variant_name.lower() in ("", "default title") else f"{title} – {variant_name}"
            if NOT_PRINTER.search(label):
                continue
            price = euro_cents_from_shopify(v.get("price"))
            if price is None:
                continue
            variant_id = str(v.get("id") or "")
            url = f"{SHOP}/en/products/{urllib.parse.quote(handle, safe='-')}"
            if variant_id.isdigit():
                url += f"?variant={variant_id}"
            entries.append({
                "id": f"{handle}:{variant_id or variant_name}",
                "name": label, "price_cents": price,
                "available": v.get("available") if isinstance(v.get("available"), bool) else None,
                "url": url, "laser": "laser" in label.lower(),
                "source": source,
                "currency_note": "Shopify-Preise in Minor Units; EUR über EU-Shop nicht verifizierbar, sofern Shop konvertiert",
            })
    return entries


class LDParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.chunks = []
        self.blocks = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "script" and dict(attrs).get("type", "").lower() == "application/ld+json":
            self.active = True
            self.chunks = []

    def handle_data(self, data):
        if self.active:
            self.chunks.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self.active:
            self.blocks.append("".join(self.chunks))
            self.active = False


def jsonld_nodes(v):
    if isinstance(v, list):
        for x in v:
            yield from jsonld_nodes(x)
    elif isinstance(v, dict):
        yield v
        if "@graph" in v:
            yield from jsonld_nodes(v["@graph"])


def parse_jsonld(page, url):
    parser = LDParser()
    parser.feed(page)
    result = []
    for block in parser.blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for node in jsonld_nodes(data):
            types = node.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if not any(str(t).lower() in ("product", "productgroup") for t in types):
                continue
            title = str(node.get("name") or "")
            if not model_name(title):
                continue
            offers = node.get("offers") or []
            if isinstance(offers, dict):
                offers = [offers]
            for index, offer in enumerate(offers):
                if not isinstance(offer, dict):
                    continue
                if str(offer.get("priceCurrency", "")).upper() != "EUR":
                    continue
                cents = euro_cents_from_decimal(offer.get("price"))
                if cents is None:
                    continue
                result.append({
                    "id": f"{urllib.parse.urlparse(url).path}:jsonld:{index}",
                    "name": title, "price_cents": cents, "available": (
                        True if "instock" in str(offer.get("availability", "")).lower() else None
                    ), "url": url, "laser": "laser" in title.lower(),
                    "source": "JSON-LD / EUR",
                })
    return result


def fetch_prices(errors, diagnostic):
    for url in CANDIDATES:
        try:
            raw, final_url = request_text(url)
            data = json.loads(raw)
            rows = parse_shopify(data, final_url, diagnostic)
            print(f"Katalog {final_url}: {len(rows)} Druckervarianten")
            if rows:
                return rows
        except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as e:
            errors.append(f"{url}: {type(e).__name__}: {str(e)[:140]}")
    rows = []
    for slug in SLUGS:
        url = f"{SHOP}/en/products/{slug}"
        try:
            raw, final_url = request_text(url)
            items = parse_jsonld(raw, final_url)
            rows.extend(items)
            print(f"JSON-LD {slug}: {len(items)} EUR-Angebote")
        except (urllib.error.URLError, OSError, ValueError) as e:
            errors.append(f"{url}: {type(e).__name__}: {str(e)[:140]}")
    return rows


def money(cents):
    return f"{cents / 100:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") + " €"


def load_previous():
    try:
        value = json.loads(CACHE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def send_mail(report, date):
    required = ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM", "MAIL_TO"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print("SMTP nicht konfiguriert; fehlende Secrets:", ", ".join(missing))
        return
    port = int(os.environ.get("SMTP_PORT") or "465")
    msg = EmailMessage()
    msg["Subject"] = f"Bambu Lab Preischeck {date} – Version {VERSION}"
    msg["From"] = os.environ["MAIL_FROM"]
    msg["To"] = os.environ["MAIL_TO"]
    msg.set_content("Der Preisbericht ist in der HTML-Ansicht enthalten.")
    msg.add_alternative(report, subtype="html")
    if port == 465:
        with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], port, timeout=30, context=ssl.create_default_context()) as smtp:
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
    elif port == 587:
        with smtplib.SMTP(os.environ["SMTP_HOST"], port, timeout=30) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
    else:
        raise ValueError("SMTP_PORT muss 465 oder 587 sein")
    print("E-Mail versendet.")


def main():
    now = dt.datetime.now(ZoneInfo("Europe/Berlin"))
    date = now.strftime("%d.%m.%Y %H:%M")
    print(f"Bambu Lab Preisalarm – Version {VERSION} – {date}")
    errors, diagnostic = [], []
    raw_rows = fetch_prices(errors, diagnostic)
    unique = {row["id"]: row for row in raw_rows}
    rows = sorted(unique.values(), key=lambda row: (row["price_cents"], row["name"]))
    previous = load_previous()
    OUT.mkdir(parents=True, exist_ok=True)
    record = {"version": VERSION, "checked_at": now.isoformat(), "products": rows, "errors": errors, "diagnostic": diagnostic}
    (OUT / "preise.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    body_rows = []
    for row in rows:
        old = previous.get(row["id"])
        delta = row["price_cents"] - old if isinstance(old, int) else None
        change = "Erstaufnahme" if delta is None else ("unverändert" if delta == 0 else ("↓ " if delta < 0 else "↑ ") + money(abs(delta)))
        cells = [row["name"], money(row["price_cents"]), change, "ja" if row["available"] is True else "nicht bestätigt", "ja" if row["laser"] else "nicht gekennzeichnet"]
        body_rows.append("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in cells) + f'<td><a href="{html.escape(row["url"], quote=True)}">Shop</a></td></tr>')
    report = (
        f"<h2>Bambu Lab Preisalarm – Version {VERSION}</h2><p>{date} Uhr, {len(rows)} Produktvarianten.</p>"
        "<p>Preise sind Momentaufnahmen; Versand, Vollständigkeit und lokale Währung müssen beim Händler geprüft werden. "
        "Änderungen sind nur sichtbar, wenn die Vorversion aus dem Cache verfügbar ist.</p>"
        "<table border='1' cellpadding='5'><tr><th>Modell/Variante</th><th>Preis</th><th>Änderung</th><th>Verfügbarkeit</th><th>Laser</th><th>Link</th></tr>"
        + "".join(body_rows) + "</table>"
    )
    if errors:
        report += "<h3>Technische Hinweise</h3><p>" + html.escape("; ".join(errors[:12])) + "</p>"
    if not rows:
        report += "<p><strong>FEHLER: Keine zuverlässigen EUR-Preise gefunden.</strong></p>"
    (OUT / "bericht.html").write_text("<!doctype html><html lang='de'><meta charset='utf-8'><body>" + report + "</body></html>", encoding="utf-8")
    if not rows:
        print("Keine verwertbaren Preise gefunden. Prüfe output/preise.json auf Katalogtitel und Fehlermeldungen.")
        sys.exit(1)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({row["id"]: row["price_cents"] for row in rows}, indent=2), encoding="utf-8")
    print(f"Erfolg: {len(rows)} Varianten; HTML und JSON unter output/ gespeichert.")
    send_mail(report, date)


if __name__ == "__main__":
    main()
