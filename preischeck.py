#!/usr/bin/env python3
"""Bambu H2S Laser Full Combo 10W price monitor, version 1.3.5.

Conservative price extraction from exact-model retailer pages and optional
manually verified offers. No guessing about VAT, shipping or discounts.
"""
VERSION = '1.3.5'
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
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; H2S-price-monitor/1.3.5)', 'Accept-Language': 'de-DE,de;q=0.9'}
SOURCES = [
    {'merchant': 'reichelt elektronik', 'url': 'https://www.reichelt.de/de/de/shop/produkt/3d_drucker_bambu_lab_h2s_laser_full_combo_10_w-412547', 'kind': 'net'},
    {'merchant': 'IGO3D', 'url': 'https://www.igo3d.com/bambu-lab-h2s-laser-full-combo-10-w-en', 'kind': 'variant'},
    {'merchant': 'Polyfab3D', 'url': 'https://www.polyfab3d.de/bambu-lab-3d-drucker/4769-bambu-lab-h2s-laser-full-combo-10w.html', 'kind': 'net'},
    {'merchant': 'Conrad', 'url': 'https://www.conrad.de/de/p/bambulab-h2s-laser-full-combo-10-w-ams-2-pro-3d-drucker-ki-unterstuetzung-kammerheizung-app-anbindung-integrierte-ka-3466450.html', 'kind': 'gross'},
]


def cents(value):
    if value is None or isinstance(value, bool):
        return None
    raw = str(value).strip()
    if not re.fullmatch(r'\d{1,6}(?:\.\d{1,2})?', raw):
        return None
    try:
        n = int(Decimal(raw) * 100)
        return n if 50000 <= n <= 2000000 else None
    except InvalidOperation:
        return None


def target_variant(name):
    s = re.sub(r'\s+', ' ', str(name).lower())
    required = (r'\bh2s\b', r'\blaser\b', r'\bfull\s*combo\b', r'\b10\s*w(?:att)?\b')
    forbidden = (r'\b40\s*w(?:att)?\b', r'\bh2d\b', r'\bh2c\b', r'\bupgrade\b', r'\bmodule only\b')
    return all(re.search(p, s) for p in required) and not any(re.search(p, s) for p in forbidden)


def fetch_page(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as response:
        if not response.geturl().startswith('https://'):
            raise ValueError('Unsafe redirect')
        content = response.read(3_000_001)
        if len(content) > 3_000_000:
            raise ValueError('HTML too large')
        return content.decode('utf-8', errors='replace')


def ld_objects(page):
    for match in re.finditer(r'<script\b[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script\s*>', page, re.I | re.S):
        try:
            obj = json.loads(html.unescape(match.group(1)))
        except ValueError:
            continue
        stack = [obj]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                yield node
                if '@graph' in node:
                    stack.append(node['@graph'])


def product_offers(page, source):
    """Only accept a single-product page whose JSON-LD name exactly matches.

    Variant-selection pages are deliberately excluded because their visible
    default price may refer to a cheaper non-laser model.
    """
    errors = []
    if source['kind'] == 'variant':
        return [], ['Variantenseite: Preis nicht eindeutig der 10W-Variante zugeordnet']
    for node in ld_objects(page):
        typ = node.get('@type', '')
        if isinstance(typ, list):
            is_product = 'Product' in typ
        else:
            is_product = typ == 'Product' or str(typ).endswith('/Product')
        if not is_product or not target_variant(node.get('name', '')):
            continue
        offers = node.get('offers') or []
        if isinstance(offers, dict):
            offers = [offers]
        for offer in offers if isinstance(offers, list) else []:
            if not isinstance(offer, dict) or offer.get('priceCurrency') != 'EUR':
                continue
            price = cents(offer.get('price'))
            if price is None:
                continue
            # Do not label net prices as consumer gross prices.
            if source['kind'] == 'net':
                errors.append('Nettopreis erkannt; nicht als Verbraucher-Endpreis übernommen')
                continue
            if offer.get('valueAddedTaxIncluded') is not True:
                errors.append('MwSt.-Status nicht ausdrücklich bestätigt')
                continue
            return [{'id': 'retailer:' + source['merchant'], 'name': node['name'],
                     'merchant': source['merchant'], 'price_cents': price,
                     'shipping_cents': None, 'discount_cents': 0, 'total_cents': None,
                     'available': None, 'link': source['url'],
                     'source': 'Live JSON-LD', 'price_basis': 'Bruttopreis; Versand unbekannt'}], errors
    return [], errors or ['Kein eindeutig zuordenbares JSON-LD-Angebot']


def extra_offers(today, errors):
    path = ROOT / 'offers.json'
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, list):
            raise ValueError('Expected list')
    except (OSError, ValueError) as exc:
        errors.append('offers.json: ' + str(exc))
        return []
    result = []
    for i, offer in enumerate(data):
        try:
            if not isinstance(offer, dict) or not target_variant(offer.get('name', '')):
                raise ValueError('Wrong model')
            date = dt.date.fromisoformat(offer['verified_on'])
            if not 0 <= (today - date).days <= 2:
                raise ValueError('Verification too old')
            price = cents(offer['price_eur'])
            shipping_raw = offer.get('shipping_eur')
            shipping = (0 if str(shipping_raw).strip() in ('0', '0.0', '0.00')
                        else cents(shipping_raw)) if shipping_raw is not None else None
            if shipping_raw is not None and shipping is None:
                raise ValueError('Invalid shipping amount')
            discount_raw = str(offer.get('discount_eur', 0)).strip()
            if not re.fullmatch(r'\d{1,6}(?:\.\d{1,2})?', discount_raw):
                raise ValueError('Invalid discount precision')
            discount = int(Decimal(discount_raw) * 100)
            if price is None or discount < 0 or discount > price or not str(offer['link']).startswith('https://'):
                raise ValueError('Invalid amounts or URL')
            if offer.get('vat_included') is not True:
                raise ValueError('Gross price not verified (vat_included must be true)')
            result.append({'id': 'manual:' + str(offer['link']), 'name': offer['name'],
                           'merchant': offer['merchant'], 'price_cents': price,
                           'shipping_cents': shipping, 'discount_cents': discount,
                           'total_cents': price + shipping - discount if shipping is not None else None,
                           'available': offer.get('available'), 'link': offer['link'],
                           'source': 'Manual verification ' + offer['verified_on'],
                           'price_basis': 'Gross price; verified manual entry'})
        except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
            errors.append(f'offers.json entry {i}: {exc}')
    return result


def money(n):
    return 'unbekannt' if n is None else f'{n / 100:.2f} €'.replace('.', ',')


def send_email(markup, stamp):
    keys = ('SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD', 'MAIL_FROM', 'MAIL_TO')
    missing = [key for key in keys if not os.getenv(key)]
    if missing:
        print('E-Mail nicht konfiguriert: ' + ', '.join(missing))
        return
    msg = EmailMessage()
    msg['From'], msg['To'] = os.environ['MAIL_FROM'], os.environ['MAIL_TO']
    msg['Subject'] = f'H2S Laser Full Combo 10W Preisalarm v{VERSION} – {stamp}'
    msg.set_content('HTML-Bericht im Anhang der E-Mail.')
    msg.add_alternative(markup, subtype='html')
    port = int(os.getenv('SMTP_PORT', '465'))
    if port not in (465, 587):
        raise ValueError('SMTP_PORT must be 465 or 587')
    with (smtplib.SMTP_SSL(os.environ['SMTP_HOST'], port, timeout=30, context=ssl.create_default_context())
          if port == 465 else smtplib.SMTP(os.environ['SMTP_HOST'], port, timeout=30)) as smtp:
        if port == 587:
            smtp.starttls(context=ssl.create_default_context())
        smtp.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
        smtp.send_message(msg)


def main():
    now = dt.datetime.now(ZoneInfo('Europe/Berlin'))
    errors, diagnostics, rows = [], [], []
    for source in SOURCES:
        try:
            page = fetch_page(source['url'])
            offers, warnings = product_offers(page, source)
            rows.extend(offers)
            diagnostics.append({'merchant': source['merchant'], 'url': source['url'],
                                'bytes': len(page), 'offers': len(offers), 'notes': warnings})
        except (OSError, ValueError) as exc:
            errors.append(source['merchant'] + ': ' + type(exc).__name__ + ': ' + str(exc)[:160])
    rows.extend(extra_offers(now.date(), errors))
    rows.sort(key=lambda x: (x['total_cents'] is None, x['total_cents'] or x['price_cents']))
    previous = {}
    try:
        previous = json.loads(CACHE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pass
    for row in rows:
        old = previous.get(row['id'], {}) if isinstance(previous, dict) else {}
        if old.get('total_cents') is not None and row['total_cents'] is not None:
            row['change_cents'] = row['total_cents'] - old['total_cents']
            row['change_basis'] = 'Endpreis'
        elif old.get('price_cents') is not None:
            row['change_cents'] = row['price_cents'] - old['price_cents']
            row['change_basis'] = 'Gerätepreis'
        else:
            row['change_cents'], row['change_basis'] = None, 'Kein Vergleich'
    OUT.mkdir(exist_ok=True)
    report = {'version': VERSION, 'checked_at': now.isoformat(), 'target': 'Bambu Lab H2S Laser Full Combo 10W',
              'offers': rows, 'errors': errors, 'diagnostics': diagnostics}
    (OUT / 'preise.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    trs = []
    for row in rows:
        cells = [row['merchant'], money(row['price_cents']), money(row['shipping_cents']),
                 money(row['total_cents']), row['change_basis'],
                 money(row['change_cents']) if row['change_cents'] is not None else '—']
        trs.append('<tr>' + ''.join('<td>' + html.escape(str(c)) + '</td>' for c in cells)
                   + '<td><a href="' + html.escape(row['link'], quote=True) + '">Angebot</a></td></tr>')
    markup = ('<h2>H2S Laser Full Combo 10W – v' + VERSION + '</h2>'
              '<p>Nur nachweisbare Brutto-Gerätepreise; Versand wird niemals geschätzt.</p>'
              '<table border="1"><tr><th>Händler</th><th>Gerätepreis</th><th>Versand</th>'
              '<th>Endpreis</th><th>Vergleichsbasis</th><th>Änderung</th><th>Link</th></tr>'
              + ''.join(trs) + '</table>')
    if not rows:
        markup += '<p>Keine eindeutig bestätigten Bruttopreise gefunden. Siehe preise.json.</p>'
    (OUT / 'bericht.html').write_text('<!doctype html><html lang="de"><meta charset="utf-8"><body>' + markup + '</body></html>', encoding='utf-8')
    if not rows:
        print('FEHLER: Keine eindeutig verifizierten Brutto-Angebote. Siehe output/preise.json')
        return 1
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps({r['id']: {'price_cents': r['price_cents'], 'total_cents': r['total_cents']} for r in rows}), encoding='utf-8')
    print(f'v{VERSION}: {len(rows)} verifizierte Angebote')
    send_email(markup, now.strftime('%d.%m.%Y %H:%M'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
