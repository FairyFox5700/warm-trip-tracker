from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "warm-trip-tracker/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def parse_ryanair(outbound: dict[str, Any], inbound: dict[str, Any]) -> dict[str, Any]:
    first = outbound["fares"][0]["outbound"]
    second = inbound["fares"][0]["outbound"]
    total = round(float(first["price"]["value"]) + float(second["price"]["value"]), 2)
    return {
        "total_eur": total,
        "outbound": f'{first["flightNumber"]} · {first["departureDate"][11:16]}–{first["arrivalDate"][11:16]}',
        "return": f'{second["flightNumber"]} · {second["departureDate"][11:16]}–{second["arrivalDate"][11:16]}',
    }


def parse_hostelworld(data: dict[str, Any], minimum_score: float, review_score: float) -> dict[str, Any] | None:
    if review_score < minimum_score:
        return None
    candidates: list[dict[str, Any]] = []
    for room in data.get("rooms", {}).get("privates", []):
        if room.get("totalRoomsAvailable", 0) or room.get("totalBedsAvailable", 0):
            candidates.append({"room": room, "private": True})
    for room in data.get("rooms", {}).get("dorms", []):
        if room.get("totalBedsAvailable", 0):
            candidates.append({"room": room, "private": False})
    priced = []
    for item in candidates:
        totals = item["room"].get("totalPrice", [])
        if totals:
            priced.append((float(totals[0]["price"]["value"]), not item["private"], item["room"]))
    if not priced:
        return None
    total, _, room = min(priced, key=lambda row: row[0])
    cancellation = ""
    if data.get("cancellationPolicies"):
        cancellation = data["cancellationPolicies"][0].get("description", "")
    return {
        "total_eur": round(total, 2),
        "room_type": room["name"],
        "availability": room.get("totalBedsAvailable") or room.get("totalRoomsAvailable"),
        "cancellation": cancellation,
    }


def choose_qualifying_deals(candidates: list[dict[str, Any]], budget: float) -> list[dict[str, Any]]:
    deduplicated: dict[tuple[str, str, str], dict[str, Any]] = {}
    for candidate in candidates:
        stay = candidate.get("accommodation")
        flight = candidate.get("flight")
        if not stay or not flight or candidate.get("typical_high_c", 0) < 18:
            continue
        mandatory_tax = round(float(candidate.get("mandatory_tax_eur", 0)), 2)
        total = round(flight["total_eur"] + stay["total_eur"] + mandatory_tax, 2)
        if total > budget:
            continue
        deal = {
            **candidate,
            "flight_total_eur": flight["total_eur"],
            "stay_total_eur": stay["total_eur"],
            "combined_total_eur": total,
            "budget_headroom_eur": round(budget - total, 2),
            "mandatory_tax_eur": mandatory_tax,
            "room_type": stay["room_type"],
            "outbound": flight["outbound"],
            "return": flight["return"],
        }
        fingerprint = (deal["destination"], deal.get("dates", ""), deal.get("property", ""))
        previous = deduplicated.get(fingerprint)
        if previous is None or deal["combined_total_eur"] < previous["combined_total_eur"]:
            deduplicated[fingerprint] = deal
    return sorted(
        deduplicated.values(),
        key=lambda item: (-item.get("utility_score", 0), item["combined_total_eur"]),
    )


def choose_best_deal(candidates: list[dict[str, Any]], budget: float) -> dict[str, Any] | None:
    deals = choose_qualifying_deals(candidates, budget)
    return deals[0] if deals else None


def render_index(deals: list[dict[str, Any]], source_errors: list[dict[str, str]] | None = None) -> str:
    if not deals:
        raise ValueError("At least one verified deal is required")
    source_errors = source_errors or []
    cards = []
    for rank, deal in enumerate(deals, start=1):
        used = round(deal["combined_total_eur"] / 200 * 100, 2)
        badge = "BEST VALUE" if rank == 1 else f"VERIFIED #{rank}"
        cards.append(f'''<article class="card deal" data-destination="{escape(deal['destination'])}">
<div class="muted">{badge}</div><h2>{escape(deal['destination'])}</h2><div>{escape(deal['dates'])}</div>
<div class="row"><span>Direct Ryanair return</span><strong>€{deal['flight_total_eur']:.2f}</strong></div>
<div class="row"><span>{escape(deal['property'])} · {deal['review_score']}/10</span><strong>€{deal['stay_total_eur']:.2f}</strong></div>
<div class="row"><span>Total</span><span class="price">€{deal['combined_total_eur']:.2f}</span></div>
<div class="bar"><span style="width:{used}%"></span></div><p class="muted">€{deal['budget_headroom_eur']:.2f} below budget · {deal['typical_high_c']}°C typical high{f" · €{deal['mandatory_tax_eur']:.2f} mandatory tax included" if deal.get('mandatory_tax_eur') else ""}</p>
<details><summary>Times, room and booking links</summary><p><strong>Outbound:</strong> {escape(deal['outbound'])}<br><strong>Return:</strong> {escape(deal['return'])}</p><p>{escape(deal['room_type'])}</p><a href="{escape(deal['flight_url'])}">Check flights</a> · <a href="{escape(deal['stay_url'])}">Check accommodation</a></details></article>''')
    errors_note = f'<p class="muted">{len(source_errors)} source check(s) failed without hiding valid deals.</p>' if source_errors else ""
    checked_at = escape(deals[0]["checked_at"])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Warm Trip Tracker</title>
<style>*{{box-sizing:border-box}}body{{font:16px system-ui;margin:0;background:#0f1117;color:#f4f5f7}}main{{max-width:980px;margin:40px auto;padding:20px}}.card{{background:#181b23;border:1px solid #303543;border-radius:18px;padding:22px}}h1{{margin:0 0 5px}}.muted{{color:#a8afbf}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:14px;margin-top:18px}}.deal:first-child{{border-color:#79d8a5}}.row{{display:flex;justify-content:space-between;gap:20px;padding:11px 0;border-bottom:1px solid #303543}}.price{{font-size:28px;color:#79d8a5;font-weight:800}}.bar{{height:10px;background:#303543;border-radius:99px;overflow:hidden;margin-top:14px}}.bar span{{display:block;height:100%;background:#79d8a5}}a{{color:#8db8ff}}summary{{cursor:pointer;color:#8db8ff}}@media(max-width:650px){{main{{margin:0}}}}</style></head>
<body data-status="verified"><main><h1>Warm trip tracker</h1><div class="muted">Dublin · 1 traveller · direct flights · flights + stay ≤ €200</div><p><strong>{len(deals)} verified deals</strong>, ranked by comfort, usable time, flexibility and total cost.</p>
<section class="grid">{''.join(cards)}</section>
<div class="card" style="margin-top:14px"><strong>How to read this</strong><p>The first card is the best overall value—not necessarily the cheapest. Prices are live observations, not reservations. Transfers, meals, larger baggage, seats and possible card fees are excluded.</p>{errors_note}<p class="muted">Last checked: {checked_at}</p></div></main></body></html>'''


def run(config_path: Path = ROOT / "config.json") -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    observations = []
    errors = []
    for item in config["candidates"]:
        try:
            flight = parse_ryanair(fetch_json(item["outbound_api"]), fetch_json(item["return_api"]))
            stay = parse_hostelworld(fetch_json(item["stay_api"]), config["minimum_dorm_score"], item["review_score"])
            observations.append({**item, "flight": flight, "accommodation": stay})
        except Exception as exc:
            errors.append({"destination": item["destination"], "error": str(exc)})
    deals = choose_qualifying_deals(observations, config["budget_eur"])
    if not deals:
        raise RuntimeError(f"No qualifying live deal; source errors: {errors}")
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for deal in deals:
        deal["checked_at"] = checked_at
    payload = {"deals": deals, "source_errors": errors, "checked_at": checked_at}
    (ROOT / "data.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (ROOT / "index.html").write_text(render_index(deals, errors), encoding="utf-8")
    return payload


if __name__ == "__main__":
    try:
        result = run()
        print(json.dumps({"status": "ok", "verified_deals": len(result["deals"]), "best": result["deals"][0]["destination"]}))
    except Exception as error:
        print(json.dumps({"status": "error", "error": str(error)}), file=sys.stderr)
        raise
