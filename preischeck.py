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
