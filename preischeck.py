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
