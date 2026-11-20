#!/usr/bin/env python3
"""Thailand family flight alert using SerpApi Google Flights, Python stdlib."""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import smtplib
import ssl
import sys
import time
from email.message import EmailMessage
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parent
CONFIG = BASE / "flugalarm_config.json"
OUT = BASE / "output" / "fluege"
ENDPOINT = "https://serpapi.com/search.json"


def api_request(params):
    key = os.getenv("SERPAPI_API_KEY")
    if not key:
        raise RuntimeError("SERPAPI_API_KEY als GitHub-Secret fehlt")
    url = ENDPOINT + "?" + urlencode({**params, "api_key": key})
    try:
        with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=55) as response:
            result = json.loads(response.read(3_000_000))
    except HTTPError as exc:
        raise RuntimeError(f"SerpApi HTTP {exc.code}; Kontingent oder Zugang prüfen") from None
    except (URLError, ValueError):
        raise RuntimeError("SerpApi konnte nicht erreicht oder gelesen werden") from None
    if not isinstance(result, dict):
        raise RuntimeError("SerpApi: unerwartetes Datenformat")
    if result.get("error"):
        raise RuntimeError("SerpApi: " + str(result["error"]).replace(key, "[secret]")[:180])
    return result


def query(config, airports, outbound, inbound, departure_token=None):
    trip = config["trip"]
    params = {
        "engine": "google_flights", "type": "1",
        "departure_id": ",".join(airports), "arrival_id": trip["destination"],
        "outbound_date": outbound.isoformat(), "return_date": inbound.isoformat(),
        "currency": "EUR", "gl": "de", "hl": "en",
        "adults": trip["adults"], "children": trip["children"],
        "travel_class": "1", "sort_by": "2", "stops": "2"
    }
    if departure_token:
        params["departure_token"] = departure_token
    return params


def rows(result):
    return [x for group in ("best_flights", "other_flights")
            for x in result.get(group, []) if isinstance(x, dict)]


def leg(raw):
    segments = raw.get("flights") or []
    if not isinstance(segments, list) or not 1 <= len(segments) <= 2:
        return None
    try:
        duration = float(raw["total_duration"]) / 60
        origin = segments[0]["departure_airport"]["id"]
        destination = segments[-1]["arrival_airport"]["id"]
    except (ValueError, TypeError, KeyError):
        return None
    if duration <= 0:
        return None
    return {
        "origin": origin, "destination": destination, "hours": round(duration, 2),
        "stops": len(segments) - 1,
        "airlines": sorted({str(x.get("airline") or "Unknown") for x in segments}),
        "segments": [
            {
                "from": s.get("departure_airport", {}).get("id"),
                "to": s.get("arrival_airport", {}).get("id"),
                "departure": s.get("departure_airport", {}).get("time"),
                "arrival": s.get("arrival_airport", {}).get("time"),
                "flight": s.get("flight_number")
            } for s in segments
        ],
        "extensions": [str(e) for e in raw.get("extensions", [])]
    }


def scale(x, points):
    if x <= points[0][0]:
        return points[0][1]
    for (a, av), (b, bv) in zip(points, points[1:]):
        if x <= b:
            return av + (bv - av) * (x - a) / (b - a)
    return points[-1][1]


def score(offer, config):
    t = config["trip"]
    dep = dt.date.fromisoformat(offer["departure_date"])
    ret = dt.date.fromisoformat(offer["return_date"])
    if not (dt.date.fromisoformat(t["departure_start"]) <= dep <= dt.date.fromisoformat(t["departure_end"])):
        return None
    days = (ret - dep).days + 1
    if not t["min_calendar_days"] <= days <= t["max_calendar_days"]:
        return None
    if offer["stops_out"] > t["max_stops_per_direction"] or offer["stops_back"] > t["max_stops_per_direction"]:
        return None
    if max(offer["hours_out"], offer["hours_back"]) > t["max_hours_per_direction"]:
        return None
    access = config["airports"][offer["origin"]]
    extra = config["comfort"]
    effective = offer["price_eur"] + access["ground_cost_eur"] + extra["assumed_seat_reservation_eur"] + extra["assumed_baggage_eur"]
    values = {
        "price": scale(effective, [(2400, 100), (2800, 86), (3200, 62), (3600, 35), (4400, 0)]),
        "travel_duration": scale((offer["hours_out"] + offer["hours_back"]) / 2, [(11, 100), (14, 90), (17, 65), (20, 30), (23, 0)]),
        "ground_access": max(0, min(100, 100 - max(0, access["ground_minutes"] - 30) * 0.4 - access["ground_cost_eur"] * 0.11)),
        "comfort": max(0, 100 - 12 * (offer["stops_out"] + offer["stops_back"])
                        - (extra["penalty_baggage_unknown"] if offer["baggage"] == "unknown" else 35 if offer["baggage"] == "not_included" else 0)
                        - extra["penalty_seats_not_guaranteed"]),
        "travel_date": max(0, 100 - 10 * abs((dep - dt.date.fromisoformat(t["preferred_departure"])).days))
    }
    weights = config["weights"]
    denominator = sum(max(0, float(weights.get(k, 0))) for k in values)
    total = sum(max(0, float(weights.get(k, 0))) * v for k, v in values.items())
    return {
        "score": round(total / denominator, 1) if denominator else 0,
        "component_scores": {k: round(v, 1) for k, v in values.items()},
        "effective_cost_estimate_eur": round(effective, 2), "calendar_days": days
    }


def parse_pair(outbound, returning, dep, ret, config):
    out, back = leg(outbound), leg(returning)
    if out is None or back is None:
        return None
    if out["origin"] not in config["airports"] or not config["airports"][out["origin"]]["enabled"]:
        return None
    if out["destination"] != config["trip"]["destination"] or back["origin"] != out["destination"] or back["destination"] != out["origin"]:
        return None
    try:
        price = float(returning["price"])
    except (ValueError, TypeError, KeyError):
        return None
    if not 0 < price < 30000:
        return None
    extras = " ".join(out["extensions"] + back["extensions"]).lower()
    baggage = "not_included" if "checked baggage for a fee" in extras else "unknown"
    offer = {
        "origin": out["origin"], "departure_date": dep.isoformat(), "return_date": ret.isoformat(),
        "price_eur": round(price, 2), "hours_out": out["hours"], "hours_back": back["hours"],
        "stops_out": out["stops"], "stops_back": back["stops"],
        "carriers": ", ".join(sorted(set(out["airlines"] + back["airlines"]))),
        "baggage": baggage, "seats_guaranteed": False,
        "segments": [out["segments"], back["segments"]],
        "source": "Google Flights via SerpApi",
        "price_status": "indicative_all_passengers_check_final_total"
    }
    evaluated = score(offer, config)
    if evaluated is None:
        return None
    offer.update(evaluated)
    return offer


def find_offers(config, dep, ret):
    allowed = [airport for airport, opt in config["airports"].items() if opt["enabled"]]
    outbound_results = api_request(query(config, allowed, dep, ret))
    candidates = []
    for raw in rows(outbound_results):
        route = leg(raw)
        if not route or route["origin"] not in allowed or route["destination"] != config["trip"]["destination"]:
            continue
        if route["hours"] > config["trip"]["max_hours_per_direction"] or not raw.get("departure_token"):
            continue
        try:
            price = float(raw["price"])
        except (ValueError, TypeError, KeyError):
            continue
        if price > 0:
            candidates.append((price + max(0, route["hours"] - 14) * 25, raw))
    if not candidates:
        return [], 1
    # One follow-up request resolves return legs for the most promising departure.
    best = min(candidates, key=lambda item: item[0])[1]
    result = api_request(query(config, allowed, dep, ret, departure_token=best["departure_token"]))
    paired = [parse_pair(best, x, dep, ret, config) for x in rows(result)]
    return [x for x in paired if x], 2


def dates_to_check(config, now):
    trip = config["trip"]
    start = dt.date.fromisoformat(trip["departure_start"])
    end = dt.date.fromisoformat(trip["departure_end"])
    possibilities = [
        (start + dt.timedelta(days=i), start + dt.timedelta(days=i + duration - 1))
        for i in range((end-start).days + 1)
        for duration in range(trip["min_calendar_days"], trip["max_calendar_days"] + 1)
    ]
    if not possibilities:
        return [], 0
    count = max(1, min(int(trip["max_queries_per_run"]), len(possibilities)))
    offset = ((now.date() - dt.date(2026, 1, 1)).days * count) % len(possibilities)
    return [possibilities[(offset + i) % len(possibilities)] for i in range(count)], len(possibilities)


def find_alerts(offers, config, previous):
    rules = config["alerts"]
    selected = []
    seen = set()
    for offer in sorted(offers, key=lambda x: x["price_eur"]):
        qualifies = (
            (offer["price_eur"] <= rules["great_price_eur"] and offer["score"] >= rules["great_score_min"])
            or (offer["price_eur"] <= rules["watch_price_eur"] and offer["score"] >= rules["watch_score_min"])
        )
        if not qualifies:
            continue
        signature = ":".join(str(offer[x]) for x in ("origin", "departure_date", "return_date", "carriers", "stops_out", "stops_back"))
        if signature in seen:
            continue
        seen.add(signature)
        if rules["only_new_or_improved"] and signature in previous and offer["price_eur"] >= previous[signature] - 30:
            continue
        offer["alert_key"] = signature
        selected.append(offer)
    return selected


def email_alert(offers):
    required = ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM", "FLIGHT_MAIL_TO"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        print("E-Mail deaktiviert: fehlend " + ", ".join(missing))
        return False
    table = "".join(
        "<tr>" + "".join("<td>" + html.escape(str(value)) + "</td>" for value in [
            o["origin"], o["departure_date"], o["return_date"], o["carriers"],
            f'{o["price_eur"]:.2f} €', f'{o["score"]}/100',
            f'{o["hours_out"]:.1f}/{o["hours_back"]:.1f} h', o["baggage"]
        ]) + "</tr>" for o in offers[:15]
    )
    body = ("<h2>Thailand-Flugpreisalarm: interessante Angebote</h2>"
            "<p>Suchpreise von Google Flights via SerpApi für 2 Erwachsene + 2 Kinder. "
            "<strong>Familiengesamtpreis, Gepäck, benachbarte Plätze und Ticketbedingungen vor Buchung prüfen.</strong></p>"
            "<table border='1' cellpadding='6'><tr><th>Abflug</th><th>Hin</th><th>Zurück</th>"
            "<th>Airline</th><th>Preisindikator</th><th>Score</th><th>Dauer</th><th>Gepäck</th></tr>"
            + table + "</table>")
    msg = EmailMessage()
    msg["From"] = os.environ["MAIL_FROM"]
    msg["To"] = os.environ["FLIGHT_MAIL_TO"]
    msg["Subject"] = f"Thailand-Flüge: {len(offers)} Angebote – ab {min(x['price_eur'] for x in offers):.0f} €"
    msg.set_content("Interessante Thailand-Flüge gefunden. Details im HTML-Teil dieser E-Mail.")
    msg.add_alternative(body, subtype="html")
    host, port = os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "465"))
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as smtp:
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
    elif port == 587:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
    else:
        raise ValueError("SMTP_PORT muss 465 oder 587 sein")
    print("Flugalarm-E-Mail gesendet")
    return True


def main():
    now = dt.datetime.now(dt.timezone.utc)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if not os.getenv("SERPAPI_API_KEY"):
        raise RuntimeError("SERPAPI_API_KEY fehlt; in GitHub Settings > Actions Secrets setzen")
    schedule, total = dates_to_check(config, now)
    offers, errors, requests = [], [], 0
    for dep, ret in schedule:
        try:
            found, count = find_offers(config, dep, ret)
            offers.extend(found)
            requests += count
        except RuntimeError as exc:
            errors.append(f"{dep} bis {ret}: {exc}")
            if "429" in str(exc) or "Kontingent" in str(exc) or "quota" in str(exc).lower():
                break
        time.sleep(0.2)
    offers.sort(key=lambda x: (-x["score"], x["price_eur"]))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"fluege.json").write_text(json.dumps({
        "checked_at": now.isoformat(), "provider": "Google Flights via SerpApi",
        "date_combinations_total": total, "date_combinations_checked": len(schedule),
        "api_requests": requests, "offers": offers[:75], "errors": errors
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    cache = BASE/".cache"/"flight_alert_history.json"
    try:
        previous = json.loads(cache.read_text(encoding="utf-8"))
        if not isinstance(previous, dict):
            previous = {}
    except (OSError, ValueError):
        previous = {}
    to_notify = find_alerts(offers, config, previous)
    sent = email_alert(to_notify) if to_notify else False
    if sent:
        previous.update({x["alert_key"]: x["price_eur"] for x in to_notify})
    cache.parent.mkdir(exist_ok=True)
    cache.write_text(json.dumps(previous, indent=2), encoding="utf-8")
    print(f"Datumskombinationen {len(schedule)}/{total}, API-Abfragen {requests}, "
          f"gültige Angebote {len(offers)}, Mail-Kandidaten {len(to_notify)}")
    for issue in errors[:10]:
        print("WARNUNG", issue)
    return 1 if errors and not offers else 0


if __name__ == "__main__":
    sys.exit(main())
