import json
import tempfile
import unittest
from pathlib import Path

from monitor import choose_best_deal, choose_qualifying_deals, parse_hostelworld, parse_ryanair, render_index


class TrackerTests(unittest.TestCase):
    def test_combines_exact_flight_and_whole_stay_total(self):
        outbound = {
            "fares": [{"outbound": {"departureDate": "2026-11-16T17:55:00", "arrivalDate": "2026-11-16T21:40:00", "flightNumber": "FR7062", "price": {"value": 20.99, "currencyCode": "EUR"}}}]
        }
        inbound = {
            "fares": [{"outbound": {"departureDate": "2026-11-21T20:35:00", "arrivalDate": "2026-11-21T22:30:00", "flightNumber": "FR7063", "price": {"value": 39.18, "currencyCode": "EUR"}}}]
        }
        stay = {
            "cancellationPolicies": [{"description": "Free cancellation before 10 Nov"}],
            "vat": 0,
            "rooms": {"dorms": [{"name": "Standard 16 Bed Mixed Dorm", "totalBedsAvailable": 10, "totalPrice": [{"price": {"value": "87.00", "currency": "EUR"}}]}], "privates": []},
        }

        flight = parse_ryanair(outbound, inbound)
        accommodation = parse_hostelworld(stay, minimum_score=8.0, review_score=9.5)
        best = choose_best_deal([{"destination": "Alicante", "flight": flight, "accommodation": accommodation, "typical_high_c": 20.5}], budget=200)

        self.assertEqual(60.17, best["flight_total_eur"])
        self.assertEqual(87.0, best["stay_total_eur"])
        self.assertEqual(147.17, best["combined_total_eur"])
        self.assertEqual("Standard 16 Bed Mixed Dorm", best["room_type"])

    def test_rejects_dorm_below_minimum_review_score(self):
        stay = {"rooms": {"dorms": [{"name": "Dorm", "totalBedsAvailable": 2, "totalPrice": [{"price": {"value": "50", "currency": "EUR"}}]}], "privates": []}}
        self.assertIsNone(parse_hostelworld(stay, minimum_score=8.0, review_score=7.9))

    def test_returns_all_qualifying_deals_ranked_and_deduplicated(self):
        flight = {"total_eur": 50.0, "outbound": "OUT", "return": "BACK"}
        stay = {"total_eur": 80.0, "room_type": "Dorm"}
        candidates = [
            {"destination": "Alicante", "dates": "16–21 Nov", "property": "VAD", "flight": flight, "accommodation": stay, "typical_high_c": 20.5, "utility_score": 8.5},
            {"destination": "Málaga", "dates": "18–21 Nov", "property": "Lights", "flight": flight, "accommodation": stay, "typical_high_c": 20.1, "utility_score": 7.9},
            {"destination": "Alicante", "dates": "16–21 Nov", "property": "VAD", "flight": {**flight, "total_eur": 55.0}, "accommodation": stay, "typical_high_c": 20.5, "utility_score": 8.5},
            {"destination": "Cold", "dates": "18–21 Nov", "property": "Cold Stay", "flight": flight, "accommodation": stay, "typical_high_c": 12.0, "utility_score": 9.9},
        ]

        deals = choose_qualifying_deals(candidates, budget=200)

        self.assertEqual(["Alicante", "Málaga"], [deal["destination"] for deal in deals])
        self.assertEqual(130.0, deals[0]["combined_total_eur"])

    def test_rendered_page_contains_live_deal_markers(self):
        deal = {"destination": "Alicante", "dates": "16–21 November", "flight_total_eur": 60.17, "stay_total_eur": 87.0, "combined_total_eur": 147.17, "budget_headroom_eur": 52.83, "typical_high_c": 20.5, "property": "VAD Hostel Alicante", "review_score": 9.5, "room_type": "Standard 16 Bed Mixed Dorm", "outbound": "FR7062 · 17:55–21:40", "return": "FR7063 · 20:35–22:30", "flight_url": "https://example.com/flight", "stay_url": "https://example.com/stay", "checked_at": "2026-10-16T11:54:50+02:00"}
        second = {**deal, "destination": "Málaga", "combined_total_eur": 165.49, "budget_headroom_eur": 34.51}
        html = render_index([deal, second], source_errors=[{"destination": "Faro", "error": "blocked"}])
        self.assertIn("Warm trip tracker", html)
        self.assertIn("Alicante", html)
        self.assertIn("Málaga", html)
        self.assertIn("2 verified deals", html)
        self.assertIn("€147.17", html)
        self.assertIn("data-status=\"verified\"", html)


if __name__ == "__main__":
    unittest.main()
