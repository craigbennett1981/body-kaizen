# Integrations

All of these are optional. Each one writes into your data folder and never overwrites what you logged by hand
(sets, notes, effort, a treadmill's belt distance).

## Garmin Connect

Adds steps, calories burnt, sleep with stages, overnight HRV, resting heart rate, body battery, stress, and
every activity with its heart-rate trace, zones and recovery heart rate.

```bash
.venv/bin/python scripts/garmin_login.py                 # once: password and MFA; token saved to ~/.garminconnect
.venv/bin/python scripts/garmin_pull.py --since 2026-07-01   # back-fill history
```

While the dashboard is running it pulls four times a day (08:00, 13:00, 19:00, 22:00) and catches up after the
computer wakes; there's a "Sync now" button in the header. If the header says the sync failed, the token has
expired: run `garmin_login.py` again.

Raw responses are saved in `imports/garmin/` with personal and location fields removed. After a change to how
fields are mapped, `garmin_pull.py --remap` re-applies them without fetching again.

> Uses the unofficial [`garminconnect`](https://github.com/cyberjunky/python-garminconnect) library. It isn't
> endorsed by Garmin and can break when Garmin changes its site. Use at your own risk.

## Abbott LibreLinkUp (continuous glucose)

Adds glucose readings from a FreeStyle Libre sensor shared through LibreLinkUp.

```bash
.venv/bin/python scripts/libre_login.py     # once: email saved to ~/.body-kaizen/libre.json, password to the keychain
```

The dashboard then pulls every 30 minutes. Glucose shows on the Day timeline next to meals.

> Uses the unofficial [`pylibrelinkup`](https://github.com/robberwick/pylibrelinkup) library. Not endorsed by
> Abbott. Use at your own risk, and never for treatment decisions.

## Hevy

Two ways in:

- **Day to day:** paste the text of a finished workout (Hevy's share button → copy) to your assistant. It logs every
  set straight into the day file, next to the Garmin data for the same session.
- **Back-filling history:** export everything from Hevy (Settings → Export & Import Data → Export Workouts) and
  import the CSV:

```bash
.venv/bin/python scripts/hevy_import.py workout_data.csv --dry-run   # check what it found
.venv/bin/python scripts/hevy_import.py workout_data.csv
```

Hevy's exercise names are mapped to your lifts by the `HEVY` table at the top of `scripts/hevy_import.py`; add a
line there for any exercise it doesn't know.

## Scales and blood-pressure monitors

These are logged by hand (or by an assistant reading a screenshot of the app) in the day file: see `weight:`
and `vitals: bp:` in [SCHEMA.md](../SCHEMA.md). Any scale or monitor works.
