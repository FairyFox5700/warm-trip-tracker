from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
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
    candidates: list[dict[str, Any]] = []
    for room in data.get("rooms", {}).get("privates", []):
        if room.get("totalRoomsAvailable", 0) or room.get("totalBedsAvailable", 0):
            candidates.append({"room": room, "private": True})
    if review_score >= minimum_score:
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


def choose_best_deal(candidates: list[dict[str, Any]], budget: float) -> dict[str, Any] | None:
    qualified = []
    for candidate in candidates:
        stay = candidate.get("accommodation")
        flight = candidate.get("flight")
        if not stay or not flight or candidate.get("typical_high_c", 0) < 18:
            continue
        total = round(flight["total_eur"] + stay["total_eur"], 2)
        if total > budget:
            continue
        qualified.append({
            **candidate,
            "flight_total_eur": flight["total_eur"],
            "stay_total_eur": stay["total_eur"],
            "combined_total_eur": total,
            "budget_headroom_eur": round(budget - total, 2),
            "room_type": stay["room_type"],
            "outbound": flight["outbound"],
            "return": flight["return"],
        })
    if not qualified:
        return None
    return max(qualified, key=lambda item: (item.get("utility_score", 0), -item["combined_total_eur"]))


def render_index(deal: dict[str, Any]) -> str:
    used = round(deal["combined_total_eur"] / 200 * 100, 2)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Warm Trip Tracker</title>
<style>*{{box-sizing:border-box}}body{{font:16px system-ui;margin:0;background:#0f1117;color:#f4f5f7}}main{{max-width:820px;margin:40px auto;padding:20px}}.card{{background:#181b23;border:1px solid #303543;border-radius:18px;padding:22px}}h1{{margin:0 0 5px}}.muted{{color:#a8afbf}}.grid{{display:grid;grid-template-columns:1.3fr .7fr;gap:14px;margin-top:18px}}.row{{display:flex;justify-content:space-between;gap:20px;padding:11px 0;border-bottom:1px solid #303543}}.price{{font-size:28px;color:#79d8a5;font-weight:800}}.bar{{height:10px;background:#303543;border-radius:99px;overflow:hidden;margin-top:14px}}.bar span{{display:block;width:{used}%;height:100%;background:#79d8a5}}a{{color:#8db8ff}}.pill{{display:inline-block;padding:5px 9px;border:1px solid #303543;border-radius:99px;margin:3px;font-size:13px}}@media(max-width:650px){{main{{margin:0}}.grid{{grid-template-columns:1fr}}}}</style></head>
<body data-status="verified"><main><h1>Warm trip tracker</h1><div class="muted">Dublin · 1 traveller · direct flights · flights + stay ≤ €200</div>
<div class="grid"><section class="card"><div class="muted">VERIFIED LIVE DEAL</div><h2>{deal['destination']}</h2><div>{deal['dates']}</div>
<div class="row"><span>Direct Ryanair return</span><strong>€{deal['flight_total_eur']:.2f}</strong></div><div class="row"><span>{deal['property']} · {deal['review_score']}/10</span><strong>€{deal['stay_total_eur']:.2f}</strong></div><div class="row"><span>Total</span><span class="price">€{deal['combined_total_eur']:.2f}</span></div><div class="bar"><span></span></div><p class="muted">€{deal['budget_headroom_eur']:.2f} below budget</p></section>
<aside class="card"><span class="pill">{deal['typical_high_c']}°C typical high</span><span class="pill">Personal item</span><span class="pill">Taxes included</span><p><strong>Outbound</strong><br>{deal['outbound']}</p><p><strong>Return</strong><br>{deal['return']}</p></aside></div>
<div class="card" style="margin-top:14px"><strong>{deal['room_type']}</strong><p>Prices are live observations, not reservations. Transfers, meals, larger baggage, seats and possible card fees are excluded.</p><a href="{deal['flight_url']}">Check flights</a> · <a href="{deal['stay_url']}">Check accommodation</a><p class="muted">Last checked: {deal['checked_at']}</p></div></main></body></html>'''


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
    best = choose_best_deal(observations, config["budget_eur"])
    if best is None:
        raise RuntimeError(f"No qualifying live deal; source errors: {errors}")
    best["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    best["source_errors"] = errors
    (ROOT / "data.json").write_text(json.dumps(best, indent=2) + "\n", encoding="utf-8")
    (ROOT / "index.html").write_text(render_index(best), encoding="utf-8")
    return best


if __name__ == "__main__":
    try:
        result = run()
        print(json.dumps({"status": "ok", "destination": result["destination"], "total_eur": result["combined_total_eur"]}))
    except Exception as error:
        print(json.dumps({"status": "error", "error": str(error)}), file=sys.stderr)
        raise
