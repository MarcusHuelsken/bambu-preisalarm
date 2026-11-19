"""Dependency-free price charts for HTML reports and email clients.

History is append-only for confirmed observations, never synthesized.
"""
import datetime as dt
import html
import json
import struct
import zlib
from pathlib import Path

MAX_DAYS = 365
WIDTH, HEIGHT = 760, 270
PALETTE = [(25, 100, 180), (210, 80, 70), (30, 145, 105), (160, 90, 180), (220, 145, 35)]


def update_history(path, offers, stamp):
    try:
        history = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(history, list):
            history = []
    except (OSError, ValueError):
        history = []
    day = dt.date.fromisoformat(stamp[:10])
    cutoff = day - dt.timedelta(days=MAX_DAYS)
    clean = []
    for row in history:
        try:
            date = dt.date.fromisoformat(row['date'])
            if cutoff <= date <= day and isinstance(row['price_cents'], int) and row['price_cents'] > 0:
                clean.append({k: row[k] for k in ('date', 'merchant', 'price_cents', 'total_cents')})
        except (KeyError, ValueError, TypeError):
            continue
    for offer in offers:
        if not isinstance(offer.get('price_cents'), int):
            continue
        clean = [r for r in clean if not (r['date'] == day.isoformat() and r['merchant'] == offer['merchant'])]
        clean.append({'date': day.isoformat(), 'merchant': offer['merchant'],
                      'price_cents': offer['price_cents'], 'total_cents': offer.get('total_cents')})
    clean.sort(key=lambda r: (r['date'], r['merchant']))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding='utf-8')
    return clean


def series(history, key='price_cents'):
    merchants = sorted({r['merchant'] for r in history if isinstance(r.get(key), int)})
    dates = sorted({r['date'] for r in history if isinstance(r.get(key), int)})
    points = {m: [(dates.index(r['date']), r[key]) for r in history
                  if r['merchant'] == m and isinstance(r.get(key), int)] for m in merchants}
    return dates, points


def chart_svg(history, key='price_cents'):
    dates, lines = series(history, key)
    if not dates:
        return '<p>Noch keine verifizierten historischen Preise vorhanden.</p>'
    values = [value for line in lines.values() for _, value in line]
    low, high = min(values), max(values)
    span = max(high - low, 100)
    left, top, width, height = 80, 25, WIDTH - 110, HEIGHT - 75
    def xy(i, value):
        return (left + (i / max(len(dates) - 1, 1)) * width,
                top + height - (value - low) / span * height)
    elements = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="Preisverlauf">']
    for n in range(5):
        y = top + height * n / 4
        price = (high - span * n / 4) / 100
        elements.append(f'<line x1="{left}" x2="{left+width}" y1="{y:.1f}" y2="{y:.1f}" stroke="#ddd"/>')
        elements.append(f'<text x="5" y="{y+4:.1f}" font-size="12">{price:.0f} EUR</text>')
    for index, (merchant, points) in enumerate(lines.items()):
        color = '#%02x%02x%02x' % PALETTE[index % len(PALETTE)]
        coords = ' '.join(f'{x:.1f},{y:.1f}' for x, y in (xy(i, v) for i, v in points))
        elements.append(f'<polyline fill="none" stroke="{color}" stroke-width="3" points="{coords}"/>')
        elements.append(f'<text x="{left + index * 135}" y="{HEIGHT-8}" fill="{color}" font-size="11">{html.escape(merchant)}</text>')
    elements.append(f'<text x="{left}" y="{HEIGHT-32}" font-size="11">{dates[0]}</text>')
    elements.append(f'<text x="{left+width-75}" y="{HEIGHT-32}" font-size="11">{dates[-1]}</text>')
    elements.append('</svg>')
    return ''.join(elements)


def chart_png(history, key='price_cents'):
    """Draw RGB PNG using stdlib; broadly supported as inline email CID."""
    dates, lines = series(history, key)
    if not dates:
        return None
    vals = [v for line in lines.values() for _, v in line]
    low, high = min(vals), max(vals)
    span = max(high - low, 100)
    pixels = bytearray([255] * WIDTH * HEIGHT * 3)
    def pixel(x, y, color):
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            i = (y * WIDTH + x) * 3
            pixels[i:i+3] = bytes(color)
    def segment(x0, y0, x1, y1, color):
        steps = max(abs(x1-x0), abs(y1-y0), 1)
        for j in range(steps+1):
            x = round(x0 + (x1-x0)*j/steps)
            y = round(y0 + (y1-y0)*j/steps)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    pixel(x+dx, y+dy, color)
    for n in range(5):
        y = 20 + round((HEIGHT-55)*n/4)
        for x in range(45, WIDTH-20):
            pixel(x, y, (225, 225, 225))
    for index, points in enumerate(lines.values()):
        coords = [(45 + round(i / max(len(dates)-1, 1)*(WIDTH-65)),
                   20 + round((1-(v-low)/span)*(HEIGHT-55))) for i, v in points]
        for a, b in zip(coords, coords[1:]):
            segment(*a, *b, PALETTE[index % len(PALETTE)])
        for x, y in coords:
            segment(x-2, y, x+2, y, PALETTE[index % len(PALETTE)])
    raw = b''.join(b'\x00' + bytes(pixels[y*WIDTH*3:(y+1)*WIDTH*3]) for y in range(HEIGHT))
    def chunk(tag, data):
        return struct.pack('!I', len(data)) + tag + data + struct.pack('!I', zlib.crc32(tag+data)&0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', WIDTH, HEIGHT, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
