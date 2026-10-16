# Warm Trip Tracker

A public, zero-secret tracker for warm trips from Dublin under **€200 total** for direct return flights plus accommodation.

## Current rules

- One traveller from Dublin (DUB)
- Direct economy return flights
- Three to five nights
- Typical daytime high of at least 18°C
- Private room preferred; dorm accepted only at review score 8.0+
- Personal-item fare assumption
- Exact dated flight inventory and exact whole-stay accommodation totals only

## How it works

There are two automation layers:

1. **Hermes local monitor** — runs daily at 08:00 local time for 45 bounded checks. It scans the wider October–November window, compares exact fares and matching stays, suppresses duplicates, and reports only verified deals or material improvements. It never books anything.
2. **GitHub Actions public validator** — runs daily at 08:10 UTC and revalidates the known Alicante, Málaga, and Lanzarote candidates through the public Ryanair and Hostelworld availability endpoints. It regenerates `data.json` and `index.html`, then commits only when the result changes.

GitHub Pages publishes the current generated dashboard. Prices are observations, not reservations.

## Run locally

```bash
python monitor.py
```

No third-party Python packages or secrets are required.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Files

- `monitor.py` — fetches, validates, ranks, and renders
- `config.json` — candidate dates and public source URLs
- `data.json` — latest verified result
- `index.html` — generated public dashboard
- `.github/workflows/ci.yml` — push/PR tests
- `.github/workflows/update-tracker.yml` — daily/manual live refresh

## Limitations

Airlines and accommodation providers may change or block their public endpoints. The scheduled workflow isolates candidate failures and keeps the last published page when no qualifying live result can be verified. Airport transfers, meals, seats, larger baggage, insurance, and payment-card fees are excluded unless explicitly shown.

## License

MIT
