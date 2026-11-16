#!/usr/bin/env python3
"""Bambu Lab EU Preischeck (nur Python-Standardbibliothek).

Quellen: Shopify-Produktkatalog und Produktseiten mit JSON-LD-Fallback.
Wenn kein belastbarer EUR-Preis gefunden wird, wird KEIN Erfolg vorgetäuscht.
"""
import datetime as dt
import html
import json
import os
import re
import smtplib
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from html.parser import HTMLParser
from pathlib import Path

BASE = "https://eu.store.bambulab.com"
OUT = Path("output")
CACHE = Path(".cache/preise.json")
AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
PRINTER = re.compile(r"(?i)(?:\bA1\b|A1\s*mini|\bP1[PS]\b|\bP2S\b|\bX1(?:C|E)?\b|X1.Carbon|\bX2D\b|\bH2[SDC]\b|\bH3C\b|\bR1\b)")
EXCLUDE = re.compile(r"(?i)(nozzle|hotend|extruder|build plate|filament|refill|spool|motor|cable|toolhead|accessor|spare part|replacement|maintenance|plate|connector|adapter|kit only|laser module only)")


def fetch(url):
    request = urllib.request.Request(url, headers={
        "User-Agent": AGENT, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8", "Referer": BASE + "/de/",
    })
    with urllib.request.urlopen(request, timeout=18) as response:
        data = response.read(8_000_000)
        return data.decode("utf-8", "replace"), response.geturl()


def get_json(url):
    body, final_url = fetch(url)
    return json.loads(body), final_url


def price_eur(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(" ", "").replace(",", "."))
        if 50 <= number <= 15000:
            return round(number * 100)
    except (ValueError, TypeError):
        pass
    return None


def shopify_products():
    """Prefer public collection catalogue; do not guess individual product handles."""
    problems = []
    for prefix in ("/de", "", "/en"):
        products = []
        for page in range(1, 5):
            url = f"{BASE}{prefix}/products.json?limit=250&page={page}"
            try:
                data, _ = get_json(url)
                batch = data.get("products", []) if isinstance(data, dict) else []
                if not isinstance(batch, list):
                    raise ValueError("ungueltiges Katalogformat")
                products.extend(batch)
                if len(batch) < 250:
                    break
            except (OSError, ValueError) as exc:
                problems.append(f"{url}: {type(exc).__name__} {str(exc)[:100]}")
                break
            time.sleep(0.25)
        if products:
            print(f"Katalog geladen: {len(products)} Artikel aus {prefix or '/'}")
            return products, problems
    return [], problems


def parse_shopify(products):
    results = {}
    for product in products:
        title = str(product.get("title", ""))
        handle = str(product.get("handle", ""))
        if not PRINTER.search(title) or EXCLUDE.search(title):
            continue
        for variant in product.get("variants", []):
            if not isinstance(variant, dict):
                continue
            vt = str(variant.get("title", ""))
            name = title + (" – " + vt if vt.lower() not in ("default title", "") else "")
            if EXCLUDE.search(name):
                continue
