#!/usr/bin/env python3
"""Reject synthetic or unverifiable success in the auto-repair workflow."""
import json
from pathlib import Path

report = json.loads(Path("output/preise.json").read_text(encoding="utf-8"))
offers = report.get("offers", [])
assert isinstance(offers, list) and offers, "No offers"
assert any(
    o.get("source") == "Live JSON-LD"
    and o.get("merchant") in {"reichelt elektronik", "IGO3D", "Polyfab3D"}
    and isinstance(o.get("price_cents"), int)
    and 50000 <= o["price_cents"] <= 2000000
    and o.get("link", "").startswith("https://")
    and "Bruttopreis" in o.get("price_basis", "")
    and "10" in o.get("name", "")
    for o in offers
), "No live verified gross offer for the requested 10W model"
print("Verified at least one live gross offer; shipping may remain unknown.")
