#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bambu Lab EU Preisalarm, Version 1.2.3 (Python >=3.11, stdlib).

Shopify products.json exposes decimal currency amounts such as '339.00', NOT
necessarily integer cents. Prices are only accepted for an explicitly EUR shop.
"""
VERSION = '1.2.3'

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
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

OUT = Path('output')
CACHE = Path('.cache/preise.json')
STORE = 'https://bambulab-eu.myshopify.com'
SHOP = 'https://eu.store.bambulab.com'
COLLECTIONS = ('/collections/3d-printer/products.json', '/products.json')
MODELS = re.compile(r'(?i)(?<![a-z0-9])(?:a1\s*mini|a1|p1s|p1p|p2s|x1c|x1e|x1\s*carbon|h2d|h2s|h2c|x2d)(?![a-z0-9])')
EXCLUDE = re.compile(r'(?i)(nozzle|hotend|extruder|filament|refill|spool|cable|adapter|replacement|maintenance|spare part|build plate|accessor(?:y|ies)|toolhead|laser module only)')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; personal-price-check/1.2.3)',
    'Accept': 'application/json, text/html;q=0.9',
    'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
}


def get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read(7_000_000).decode('utf-8', 'replace'), response.geturl()


def cents_from_shopify(value):
    """Shopify products.json: decimal EUR units; do NOT treat '339.00' as cents."""
    if value is None or isinstance(value, bool):
        return None
    raw = str(value).strip()
    if not re.fullmatch(r'\d{1,5}(?:\.\d{1,2})?', raw):
        return None
    try:
        cents = int((Decimal(raw) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        return cents if 5_000 <= cents <= 2_000_000 else None
    except InvalidOperation:
        return None


def parse_products(data, source, diagnostics):
    products = data.get('products') if isinstance(data, dict) else None
    if not isinstance(products, list):
        raise ValueError('Keine Shopify-Produktliste gefunden')
    diagnostics.append({'url': source, 'products': len(products),
                        'sample_titles': [str(x.get('title')) for x in products[:20] if isinstance(x, dict)],
                        'sample_prices': [(str(x.get('title')), [str(v.get('price')) for v in x.get('variants', [])[:3] if isinstance(v, dict)])
                                          for x in products[:8] if isinstance(x, dict)]})
    rows = []
    for product in products:
        if not isinstance(product, dict):
            continue
        name = str(product.get('title') or '')
        if not MODELS.search(name) or EXCLUDE.search(name):
            continue
        handle = str(product.get('handle') or '')
        if not re.fullmatch('[a-z0-9-]+', handle):
            continue
        for v in product.get('variants') or []:
            if not isinstance(v, dict):
                continue
            variant = str(v.get('title') or '').strip()
            title = name + (f' – {variant}' if variant.lower() not in ('', 'default title') else '')
            if EXCLUDE.search(title):
                continue
            cents = cents_from_shopify(v.get('price'))
            if cents is None:
                continue
            variant_id = str(v.get('id') or '')
            link = f'{STORE}/products/{handle}'
            if variant_id.isdigit():
                link += f'?variant={variant_id}'
            rows.append({'id': handle + ':' + (variant_id or variant), 'name': title,
                         'price_cents': cents, 'available': v.get('available') if isinstance(v.get('available'), bool) else None,
                         'laser': 'laser' in title.lower(), 'url': link, 'source': source, 'currency': 'EUR'})
    return rows


def download_prices():
    diagnostics, failures = [], []
    for endpoint in COLLECTIONS:
        collected = []
        for page in range(1, 5):
            url = STORE + endpoint + '?limit=250&page=' + str(page)
            try:
                body, final = get(url)
                payload = json.loads(body)
                rows = parse_products(payload, final, diagnostics)
                collected.extend(rows)
                count = len(payload['products'])
                print(f'Katalog Seite {page}: {count} Produkte, {len(rows)} Druckervarianten')
                if count < 250:
                    break
            except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
                failures.append(f'{url}: {type(exc).__name__} {str(exc)[:140]}')
                break
        if collected:
            return collected, failures, diagnostics
    return [], failures, diagnostics


def money(cents):
    return f'{cents / 100:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.') + ' €'


def last_prices():
    try:
        p = json.loads(CACHE.read_text(encoding='utf-8'))
        return p if isinstance(p, dict) else {}
    except (OSError, ValueError):
        return {}


def email_report(body, timestamp):
    required = ('SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD', 'MAIL_FROM', 'MAIL_TO')
    missing = [x for x in required if not os.getenv(x)]
    if missing:
        print('E-Mail deaktiviert: GitHub-Secrets fehlen: ' + ', '.join(missing))
        return
    msg = EmailMessage()
    msg['From'] = os.environ['MAIL_FROM']
    msg['To'] = os.environ['MAIL_TO']
    msg['Subject'] = f'Bambu Lab Preisalarm v{VERSION} – {timestamp}'
    msg.set_content('Der Bambu-Lab-Preisbericht ist als HTML enthalten.')
    msg.add_alternative(body, subtype='html')
    port = int(os.getenv('SMTP_PORT') or '465')
    host = os.environ['SMTP_HOST']
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30, context=ssl.create_default_context()) as smtp:
            smtp.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
            smtp.send_message(msg)
    elif port == 587:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
            smtp.send_message(msg)
    else:
        raise ValueError('SMTP_PORT muss 465 oder 587 sein')
    print('E-Mail versendet')


def main():
    now = dt.datetime.now(ZoneInfo('Europe/Berlin'))
    time_str = now.strftime('%d.%m.%Y %H:%M')
    print(f'Bambu Lab Preisalarm v{VERSION} – {time_str}')
    products, errors, diagnostics = download_prices()
    products = sorted({p['id']: p for p in products}.values(), key=lambda p: (p['price_cents'], p['name']))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'preise.json').write_text(json.dumps({'version': VERSION, 'checked_at': now.isoformat(),
        'products': products, 'diagnostics': diagnostics, 'errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    previous = last_prices()
    table = []
    for item in products:
        old = previous.get(item['id'])
        diff = item['price_cents'] - old if type(old) is int else None
        change = ('neu erfasst' if diff is None else 'unverändert' if diff == 0 else
                  ('gesunken um ' if diff < 0 else 'gestiegen um ') + money(abs(diff)))
        values = (item['name'], money(item['price_cents']), change,
                  'ja' if item['available'] is True else 'nein' if item['available'] is False else 'unbekannt',
                  'ja' if item['laser'] else 'nicht ausgewiesen')
        table.append('<tr>' + ''.join('<td>' + html.escape(v) + '</td>' for v in values) +
                     '<td><a href="' + html.escape(item['url'], quote=True) + '">Zum Shop</a></td></tr>')
    report = (f'<h2>Bambu Lab Preisalarm v{VERSION}</h2><p>{time_str} Uhr | {len(products)} Varianten</p>'
              '<p>Quelle: offizieller Bambu-Lab-EU-Shop (Shopify). Nur Euro-Shoppreise; Endpreis inklusive Versand '
              'kann abweichen. Preisänderungen setzen vorherige gespeicherte Preise voraus.</p>'
              '<table border="1" cellpadding="5"><tr><th>Modell</th><th>Preis</th><th>Änderung</th>'
              '<th>Verfügbar</th><th>Laser</th><th>Link</th></tr>' + ''.join(table) + '</table>')
    if not products:
        report += '<p><strong>Fehler: Keine zuverlässigen Druckerpreise verfügbar. Siehe Diagnosedatei.</strong></p>'
    (OUT / 'bericht.html').write_text('<!doctype html><html lang="de"><meta charset="utf-8"><body>' + report + '</body></html>', encoding='utf-8')
    if not products:
        print('FEHLER: Keine Druckerpreise. Siehe output/preise.json')
        return 1
    print(f'Erfolg: {len(products)} Druckervarianten aus EUR-Shop')
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({x['id']: x['price_cents'] for x in products}, indent=2), encoding='utf-8')
    email_report(report, time_str)
    return 0


if __name__ == '__main__':
    sys.exit(main())
