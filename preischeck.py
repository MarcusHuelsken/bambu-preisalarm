"""Unofficial Bambu Lab EU price monitor. Python standard library only."""
import datetime as dt
import html
import json
import os
from pathlib import Path
import smtplib
import ssl
import urllib.request
from email.message import EmailMessage

SHOP = 'https://eu.store.bambulab.com'
# Additional product slugs can be added; only successfully accessed products are reported.
SLUGS = ['a1-mini', 'a1', 'p1s', 'p2s', 'x1-carbon', 'h2s', 'h2d', 'h2c']
OUT = Path('output')


def get_product(slug):
    req = urllib.request.Request(f'{SHOP}/en/products/{slug}.js', headers={
        'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=20) as response:
        data = json.load(response)
    if not isinstance(data, dict) or not isinstance(data.get('variants'), list):
        raise ValueError('Keine auswertbaren Varianten')
    return data


def euro(cents):
    return f'{cents / 100:.2f} €'.replace('.', ',')


def email_report(body, count):
    names = ['SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD', 'MAIL_FROM', 'MAIL_TO']
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        print('E-Mail nicht aktiviert; fehlend:', ', '.join(missing))
        return
    message = EmailMessage()
    message['Subject'] = f'Bambu Lab Preischeck – {dt.date.today().isoformat()} ({count} Varianten)'
    message['From'] = os.environ['MAIL_FROM']
    message['To'] = os.environ['MAIL_TO']
    message.set_content('Der HTML-Bericht enthält die aktuellen Angebote.')
    message.add_alternative(body, subtype='html')
    port = int(os.environ.get('SMTP_PORT') or '465')
    if port == 465:
        with smtplib.SMTP_SSL(os.environ['SMTP_HOST'], port, context=ssl.create_default_context(), timeout=30) as smtp:
            smtp.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
            smtp.send_message(message)
    elif port == 587:
        with smtplib.SMTP(os.environ['SMTP_HOST'], port, timeout=30) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
            smtp.send_message(message)
    else:
        raise ValueError('SMTP_PORT muss 465 oder 587 sein')
    print('Bericht per E-Mail versandt.')


def main():
    rows = []
    problems = []
    for slug in SLUGS:
        try:
            product = get_product(slug)
            for variant in product['variants']:
                price = variant.get('price')
                if not isinstance(price, int) or price <= 0:
                    continue
                title = str(product.get('title') or slug)
                extra = variant.get('public_title') or variant.get('title') or ''
                if extra != 'Default Title':
                    title += ' – ' + extra
                vid = str(variant.get('id') or '')
                rows.append({
                    'title': title, 'price_cents': price,
                    'available': variant.get('available'),
                    'url': f'{SHOP}/en/products/{slug}?variant={vid}',
                })
        except Exception as exc:
            problems.append(f'{slug}: {type(exc).__name__}: {str(exc)[:100]}')
    rows.sort(key=lambda x: x['price_cents'])
    cells = ''.join('<tr><td>' + html.escape(row['title']) + '</td><td>' +
                    euro(row['price_cents']) + '</td><td>' +
                    ('Ja' if row['available'] else 'Nein/Unbekannt') +
                    '</td><td><a href="' + html.escape(row['url'], quote=True) +
                    '">Shop</a></td></tr>' for row in rows)
    body = ('<h2>Bambu Lab – täglicher EU-Shop-Preischeck</h2>'
            '<p>Preise sind Momentaufnahmen; keine Garantie für Versandkosten, Rabatte oder Vollständigkeit.</p>'
            '<table border="1" cellpadding="5"><tr><th>Modell / Variante</th><th>Preis</th>'
            '<th>Verfügbarkeit</th><th>Link</th></tr>' + cells + '</table>')
    if problems:
        body += '<p><strong>Nicht geprüft:</strong> ' + html.escape('; '.join(problems)) + '</p>'
    OUT.mkdir(exist_ok=True)
    (OUT / 'bericht.html').write_text(body, encoding='utf-8')
    (OUT / 'preise.json').write_text(json.dumps({'variants': rows, 'errors': problems}, indent=2, ensure_ascii=False), encoding='utf-8')
    if not rows:
        raise RuntimeError('Keine Preise verfügbar. Produktendpunkte prüfen.')
    email_report(body, len(rows))


if __name__ == '__main__':
    main()
