#!/usr/bin/env python3
"""Bambu H2S Laser Full Combo 10W price monitor v1.3.1 (Python 3.11+)."""
VERSION = '1.3.1'
import datetime as dt
import html
import json
import os
import re
import smtplib
import ssl
import sys
import urllib.request
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output'
CACHE = ROOT / '.cache' / 'preise.json'
STORE = 'https://bambulab-eu.myshopify.com'
PRODUCT_URL = 'https://eu.store.bambulab.com'
ENDPOINTS = ('/collections/3d-printer/products.json', '/products.json')
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; bambu-price-monitor/1.3.1)', 'Accept': 'application/json', 'Accept-Language': 'de-DE,de;q=0.9'}


def cents(value):
    if value is None or isinstance(value, bool):
        return None
    raw = str(value).strip()
    if not re.fullmatch(r'\d{1,5}(?:\.\d{1,2})?', raw):
        return None
    try:
        n = int(Decimal(raw) * 100)
        return n if 0 <= n <= 2_000_000 else None
    except InvalidOperation:
        return None


def target_variant(text):
    s = re.sub(r'\s+', ' ', text.lower())
    required = (r'\bh2s\b', r'\blaser\b', r'\bfull\s*combo\b', r'\b10\s*w(?:att)?\b')
    forbidden = (r'\b40\s*w(?:att)?\b', r'\bwithout\s+laser\b', r'\bohne\s+laser\b',
                 r'\bmodule\s+only\b', r'\bupgrade\s+kit\b', r'\breplacement\b')
    return all(re.search(p, s) for p in required) and not any(re.search(p, s) for p in forbidden)


def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read(6_000_001)
        if len(raw) > 6_000_000:
            raise ValueError('Response too large')
        return json.loads(raw.decode('utf-8')), response.geturl()


def parse_shopify(data, source):
    products = data.get('products') if isinstance(data, dict) else None
    if not isinstance(products, list):
        raise ValueError('Shopify products list missing')
    rows = []
    for product in products:
        if not isinstance(product, dict):
            continue
        title, handle = str(product.get('title') or ''), str(product.get('handle') or '')
        if not re.fullmatch(r'[a-z0-9-]+', handle):
            continue
        for variant in product.get('variants') or []:
            if not isinstance(variant, dict):
                continue
            name = title + ' – ' + str(variant.get('title') or '')
            if not target_variant(name):
                continue
            price = cents(variant.get('price'))
            if price is None or price < 50_000:
                continue
            vid = str(variant.get('id') or '')
            url = PRODUCT_URL + '/products/' + handle + ('?variant=' + vid if vid.isdigit() else '')
            rows.append({'id': f'bambu:{handle}:{vid or name}', 'name': name, 'merchant': 'Bambu Lab EU',
                         'price_cents': price, 'shipping_cents': None, 'discount_cents': 0,
                         'total_cents': None, 'available': variant.get('available'), 'laser_watts': 10,
                         'link': url, 'source': source, 'price_basis': 'EUR catalogue; shipping/promotions not verified'})
    return rows


def official_offers(errors, diagnostics):
    for endpoint in ENDPOINTS:
        found = []
        for page in range(1, 5):
            url = STORE + endpoint + f'?limit=250&page={page}'
            try:
                data, final_url = get_json(url)
                offers = parse_shopify(data, final_url)
                diagnostics.append({'source': final_url, 'product_count': len(data['products']),
                                    'matching_offers': len(offers),
                                    'sample_titles': [str(p.get('title')) for p in data['products'][:15] if isinstance(p, dict)]})
                found.extend(offers)
                if len(data['products']) < 250:
                    break
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append(f'{url}: {type(exc).__name__}: {str(exc)[:160]}')
                break
        if found:
            return found
    return []


def extra_offers(errors, today=None):
    today = today or dt.datetime.now(ZoneInfo('Europe/Berlin')).date()
    path = ROOT / 'offers.json'
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        errors.append(f'offers.json unreadable: {exc}')
        return []
    if not isinstance(data, list):
        errors.append('offers.json must be a list')
        return []
    result = []
    for i, item in enumerate(data):
        if not isinstance(item, dict) or not target_variant(str(item.get('name') or '')):
            errors.append(f'External offer {i}: wrong model/format')
            continue
        price, shipping, discount = cents(item.get('price_eur')), cents(item.get('shipping_eur')), cents(item.get('discount_eur', 0))
        merchant, link = str(item.get('merchant') or '').strip(), str(item.get('link') or '').strip()
        try:
            verified = dt.date.fromisoformat(str(item.get('verified_on') or ''))
        except ValueError:
            errors.append(f'External offer {i}: invalid verification date')
            continue
        if (price is None or price < 50_000 or discount is None or not merchant or
                not re.fullmatch(r'https://[^\s/]+(?:/[^\s]*)?', link) or not (0 <= (today - verified).days <= 2) or
                discount > price + (shipping or 0)):
            errors.append(f'External offer {i}: incomplete/stale/invalid')
            continue
        result.append({'id': f'external:{merchant}:{link}', 'name': item['name'], 'merchant': merchant,
                       'price_cents': price, 'shipping_cents': shipping, 'discount_cents': discount,
                       'total_cents': price + shipping - discount if shipping is not None else None,
                       'available': item.get('available'), 'laser_watts': 10, 'link': link,
                       'source': f'manually verified {verified}', 'price_basis': 'Manually verified retailer offer'})
    return result


def money(value):
    return 'unbekannt' if value is None else f'{value // 100:,}'.replace(',', '.') + f',{value % 100:02d} €'


def previous_prices():
    try:
        value = json.loads(CACHE.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def attach_changes(rows, previous):
    for row in rows:
        prior = previous.get(row['id'])
        prior = prior if isinstance(prior, dict) else {}
        current_total = row['total_cents']
        prior_total = prior.get('total_cents')
        prior_price = prior.get('price_cents')
        if type(current_total) is int and type(prior_total) is int:
            row['change_cents'], row['change_basis'] = current_total - prior_total, 'Endpreis'
        elif type(prior_price) is int:
            row['change_cents'], row['change_basis'] = row['price_cents'] - prior_price, 'Geraetepreis (ohne Versand)'
        else:
            row['change_cents'], row['change_basis'] = None, 'noch kein Vergleich'


def email_report(markup, stamp):
    required = ('SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD', 'MAIL_FROM', 'MAIL_TO')
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        print('E-Mail nicht konfiguriert: ' + ', '.join(missing))
        return
    msg = EmailMessage()
    msg['From'], msg['To'] = os.environ['MAIL_FROM'], os.environ['MAIL_TO']
    msg['Subject'] = f'H2S Laser Full Combo 10W Preisalarm – {stamp}'
    msg.set_content('Preisbericht als HTML enthalten.')
    msg.add_alternative(markup, subtype='html')
    port = int(os.getenv('SMTP_PORT') or '465')
    if port not in (465, 587):
        raise ValueError('SMTP_PORT must be 465 or 587')
    smtp = (smtplib.SMTP_SSL(os.environ['SMTP_HOST'], port, timeout=30, context=ssl.create_default_context())
            if port == 465 else smtplib.SMTP(os.environ['SMTP_HOST'], port, timeout=30))
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
    rows = official_offers(errors, diagnostics) + extra_offers(errors, now.date())
    rows = list({r['id']: r for r in rows}.values())
    rows.sort(key=lambda r: (r['total_cents'] is None, r['total_cents'] if r['total_cents'] is not None else r['price_cents']))
    attach_changes(rows, previous_prices())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'preise.json').write_text(json.dumps({'version': VERSION, 'checked_at': now.isoformat(),
        'target': 'Bambu Lab H2S Laser Full Combo 10W', 'offers': rows,
        'errors': errors, 'diagnostics': diagnostics}, ensure_ascii=False, indent=2), encoding='utf-8')
    table = []
    for row in rows:
        change = row['change_cents']
        change_text = ('noch kein Vergleich' if change is None else 'unveraendert' if change == 0 else
                       ('gesunken ' if change < 0 else 'gestiegen ') + money(abs(change)))
        values = [row['merchant'], money(row['price_cents']), money(row['shipping_cents']),
                  money(row['discount_cents']), money(row['total_cents']),
                  change_text + ' (' + row['change_basis'] + ')',
                  'ja' if row['available'] is True else 'nein' if row['available'] is False else 'unbekannt']
        table.append('<tr>' + ''.join('<td>' + html.escape(str(v)) + '</td>' for v in values)
                     + '<td><a href="' + html.escape(row['link'], quote=True) + '">Angebot</a></td></tr>')
    report = ('<h2>H2S Laser Full Combo 10W | ' + html.escape(stamp) + '</h2>'
              '<p>Nur das H2S Laser Full Combo 10W. Katalogpreise ohne verifizierten Versand sind keine Endpreise.</p>'
              '<table border="1" cellpadding="5"><tr><th>Händler</th><th>Preis</th><th>Versand</th>'
              '<th>Rabatt</th><th>Endpreis</th><th>Änderung</th><th>Lieferbar</th><th>Link</th></tr>'
              + ''.join(table) + '</table>')
    if not rows:
        report += '<p><strong>Keine verlässlich identifizierten Angebote.</strong></p>'
    if errors:
        report += '<p>Hinweise: ' + html.escape('; '.join(errors[:8])) + '</p>'
    (OUT / 'bericht.html').write_text('<!doctype html><html lang="de"><meta charset="utf-8"><body>' + report + '</body></html>', encoding='utf-8')
    if not rows:
        print('FEHLER: Keine H2S Laser Full Combo 10W Angebote erkannt')
        return 1
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({r['id']: {'total_cents': r['total_cents'], 'price_cents': r['price_cents']}
                                 for r in rows}, indent=2), encoding='utf-8')
    print(f'H2S Laser Full Combo 10W: {len(rows)} Angebote; {sum(r["total_cents"] is not None for r in rows)} vollständige Endpreise')
    email_report(report, stamp)
    return 0


if __name__ == '__main__':
    sys.exit(main())
