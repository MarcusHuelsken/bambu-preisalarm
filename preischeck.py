#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bambu Lab H2S Laser Full Combo 10W price monitor, v1.3.0.

Only genuine 10W H2S Laser Full Combo variants are monitored. EU Shopify
product feed is the automatic source; additional retailer offers can be supplied
in offers.json with explicit provenance. Never invent shipping or coupons.
Python 3.11+ standard library only.
"""
VERSION = '1.3.0'
import datetime as dt
import html
import json
import os
import re
import smtplib
import ssl
import sys
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output'
CACHE = ROOT / '.cache' / 'preise.json'
STORE = 'https://bambulab-eu.myshopify.com'
PRODUCT_URL = 'https://eu.store.bambulab.com'
ENDPOINTS = ('/collections/3d-printer/products.json', '/products.json')
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; bambu-price-monitor/1.3.0)',
           'Accept': 'application/json', 'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8'}


def cents(value):
    if value is None or isinstance(value, bool):
        return None
    raw = str(value).strip()
    if not re.fullmatch(r'\d{1,5}(?:\.\d{1,2})?', raw):
        return None
    try:
        n = int((Decimal(raw) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        return n if 0 <= n <= 2_000_000 else None
    except InvalidOperation:
        return None


def target_variant(text):
    """Require H2S, Laser, Full Combo, 10 W; reject 40 W, upgrades, bundles."""
    s = re.sub(r'\s+', ' ', text.lower())
    required = (r'\bh2s\b', r'\blaser\b', r'\bfull\s*combo\b', r'\b10\s*w(?:att)?\b')
    forbidden = (r'\b40\s*w(?:att)?\b', r'\bwithout\s+laser\b',
                 r'\bohne\s+laser\b', r'\bmodule\s+only\b',
                 r'\bupgrade\s+kit\b', r'\breplacement\b')
    return all(re.search(x, s) for x in required) and not any(re.search(x, s) for x in forbidden)


def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as resp:
        raw = resp.read(6_000_001)
        if len(raw) > 6_000_000:
            raise ValueError('Response too large')
        return json.loads(raw.decode('utf-8')), resp.geturl()


def parse_shopify(data, source):
    products = data.get('products') if isinstance(data, dict) else None
    if not isinstance(products, list):
        raise ValueError('Shopify products list missing')
    result = []
    for prod in products:
        if not isinstance(prod, dict):
            continue
        title = str(prod.get('title') or '')
        handle = str(prod.get('handle') or '')
        if not re.fullmatch(r'[a-z0-9-]+', handle):
            continue
        for v in prod.get('variants') or []:
            if not isinstance(v, dict):
                continue
            variant = str(v.get('title') or '')
            full_name = title + ' – ' + variant
            if not target_variant(full_name):
                continue
            amount = cents(v.get('price'))
            if amount is None or amount < 50_000:
                continue
            vid = str(v.get('id') or '')
            link = PRODUCT_URL + '/products/' + handle
            if vid.isdigit():
                link += '?variant=' + vid
            result.append({'id': f'bambu:{handle}:{vid or variant}', 'name': full_name,
                           'merchant': 'Bambu Lab EU', 'price_cents': amount,
                           'shipping_cents': None, 'discount_cents': 0,
                           'total_cents': None, 'available': v.get('available'),
                           'laser_watts': 10, 'link': link, 'source': source,
                           'price_basis': 'EUR product catalogue; delivery and applicable promotions unverified'})
    return result


def official_offers(errors, diagnostics):
    for endpoint in ENDPOINTS:
        result = []
        for page in range(1, 5):
            url = STORE + endpoint + f'?limit=250&page={page}'
            try:
                data, final = get_json(url)
                diagnostics.append({'source': final, 'product_count': len(data.get('products', [])),
                                    'sample_titles': [str(p.get('title')) for p in data.get('products', [])[:15]]})
                result.extend(parse_shopify(data, final))
                if len(data['products']) < 250:
                    break
            except (OSError, urllib.error.URLError, ValueError, KeyError, json.JSONDecodeError) as exc:
                errors.append(f'{url}: {type(exc).__name__}: {str(exc)[:160]}')
                break
        if result:
            return result
    return []


def extra_offers(errors):
    """Optional externally verified offers; never scrape fictitious discounts.

    offers.json entries: name,merchant,link,price_eur,shipping_eur,
    discount_eur,available,verified_on. All monetary fields must be explicit.
    """
    path = ROOT / 'offers.json'
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        errors.append(f'offers.json cannot be parsed: {exc}')
        return []
    if not isinstance(data, list):
        errors.append('offers.json must contain a list')
        return []
    result = []
    for index, item in enumerate(data):
        if not isinstance(item, dict) or not target_variant(str(item.get('name') or '')):
            errors.append(f'External offer {index}: ignored; wrong model or format')
            continue
        price = cents(item.get('price_eur'))
        shipping = cents(item.get('shipping_eur'))
        discount = cents(item.get('discount_eur', 0))
        merchant = str(item.get('merchant') or '').strip()
        link = str(item.get('link') or '')
        verified = str(item.get('verified_on') or '')
        if (price is None or price < 50_000 or discount is None or
                not merchant or not link.startswith('https://') or
                not re.fullmatch(r'\d{4}-\d{2}-\d{2}', verified)):
            errors.append(f'External offer {index}: incomplete; ignored')
            continue
        today = dt.date.today()
        try:
            age = (today - dt.date.fromisoformat(verified)).days
        except ValueError:
            errors.append(f'External offer {index}: invalid date')
            continue
        if age < 0 or age > 2:
            errors.append(f'External offer {index}: unverified recently; ignored')
            continue
        if discount > price + (shipping or 0):
            errors.append(f'External offer {index}: invalid discount')
            continue
        result.append({'id': f'external:{merchant}:{link}', 'name': item['name'],
                       'merchant': merchant, 'price_cents': price,
                       'shipping_cents': shipping, 'discount_cents': discount,
                       'total_cents': (price + shipping - discount if shipping is not None else None),
                       'available': item.get('available'), 'laser_watts': 10,
                       'link': link, 'source': f'manually verified {verified}',
                       'price_basis': 'External offer entered after individual verification'})
    return result


def money(value):
    return 'unbekannt' if value is None else f'{value/100:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.') + ' €'


def previous_prices():
    try:
        data = json.loads(CACHE.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def email_report(markup, stamp):
    required = ('SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD', 'MAIL_FROM', 'MAIL_TO')
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        print('E-Mail nicht konfiguriert: ' + ', '.join(missing))
        return
    msg = EmailMessage()
    msg['From'] = os.environ['MAIL_FROM']
    msg['To'] = os.environ['MAIL_TO']
    msg['Subject'] = f'H2S Laser Full Combo 10W Preisalarm – {stamp}'
    msg.set_content('Preisbericht als HTML enthalten.')
    msg.add_alternative(markup, subtype='html')
    host = os.environ['SMTP_HOST']
    port = int(os.getenv('SMTP_PORT') or '465')
    if port == 465:
        smtp = smtplib.SMTP_SSL(host, port, timeout=30, context=ssl.create_default_context())
    elif port == 587:
        smtp = smtplib.SMTP(host, port, timeout=30)
    else:
        raise ValueError('SMTP_PORT must be 465 or 587')
    with smtp:
        if port == 587:
            smtp.starttls(context=ssl.create_default_context())
        smtp.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
        smtp.send_message(msg)
    print('E-Mail versendet')


def main():
    now = dt.datetime.now(ZoneInfo('Europe/Berlin'))
    stamp = now.strftime('%d.%m.%Y %H:%M')
    errors, diagnostics = [], []
    rows = official_offers(errors, diagnostics) + extra_offers(errors)
    rows = list({v['id']: v for v in rows}.values())
    rows.sort(key=lambda x: (x['total_cents'] is None, x['total_cents'] if x['total_cents'] is not None else x['price_cents']))
    before = previous_prices()
    for item in rows:
        previous = before.get(item['id'])
        prior_total = previous.get('total_cents') if isinstance(previous, dict) else None
        prior_product = previous.get('price_cents') if isinstance(previous, dict) else None
        current = item['total_cents']
        if isinstance(prior_total, int) and isinstance(current, int):
            item['change_cents'] = current - prior_total
            item['change_basis'] = 'Endpreis'
        elif isinstance(prior_product, int):
            item['change_cents'] = item['price_cents'] - prior_product
            item['change_basis'] = 'Geraetepreis (ohne Versand)'
        else:
            item['change_cents'] = None
            item['change_basis'] = 'noch kein Vergleich'
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'preise.json').write_text(json.dumps({'version': VERSION, 'checked_at': now.isoformat(),
        'target': 'Bambu Lab H2S Laser Full Combo 10W', 'offers': rows,
        'errors': errors, 'diagnostics': diagnostics}, ensure_ascii=False, indent=2), encoding='utf-8')
    table = []
    for r in rows:
        diff = r['change_cents']
        change = ('noch kein Vergleich' if diff is None else 'unveraendert' if diff == 0 else
                  ('gesunken ' if diff < 0 else 'gestiegen ') + money(abs(diff)))
        change += ' (' + r['change_basis'] + ')'
        cells = [r['merchant'], money(r['price_cents']), money(r['shipping_cents']),
                 money(r['discount_cents']), money(r['total_cents']), change,
                 'ja' if r['available'] is True else 'nein' if r['available'] is False else 'unbekannt']
        table.append('<tr>' + ''.join('<td>' + html.escape(str(c)) + '</td>' for c in cells)
                     + '<td><a href="' + html.escape(r['link'], quote=True) + '">Angebot</a></td></tr>')
    report = ('<h2>H2S Laser Full Combo 10W | ' + html.escape(stamp) + '</h2>'
              '<p>Ausschließlich H2S Laser Full Combo 10W. Andere Varianten ausgeschlossen. '
              'Bambu-Katalogpreise enthalten ohne separat verifizierten Versandwert KEINEN bestätigten Endpreis. '
              'Gutscheine und Cashback nur berücksichtigen, wenn für das Modell tatsächlich gültig.</p>'
              '<table border="1" cellpadding="5"><tr><th>Händler</th><th>Preis</th><th>Versand</th>'
              '<th>nachgewiesener Sofortrabatt</th><th>Endpreis</th><th>Änderung</th><th>Lieferbar</th><th>Link</th></tr>'
              + ''.join(table) + '</table>')
    if not rows:
        report += '<p><strong>Keine verlässlich identifizierten H2S-Laser-Angebote; Bericht zeigt keine erfundenen Preise.</strong></p>'
    if errors:
        report += '<p>Hinweise: ' + html.escape('; '.join(errors[:8])) + '</p>'
    (OUT / 'bericht.html').write_text('<!doctype html><html lang="de"><meta charset="utf-8"><body>' + report + '</body></html>', encoding='utf-8')
    if not rows:
        print('FEHLER: Keine H2S Laser Full Combo 10W Angebote erkannt')
        return 1
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({r['id']: {'total_cents': r['total_cents'], 'price_cents': r['price_cents']}
                                 for r in rows}, indent=2), encoding='utf-8')
    print(f'H2S Laser Full Combo 10W: {len(rows)} Angebote; davon {sum(x["total_cents"] is not None for x in rows)} mit vollständigem Endpreis')
    email_report(report, stamp)
    return 0


if __name__ == '__main__':
    sys.exit(main())
