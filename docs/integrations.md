# Integrations

All of these are optional. Each one writes into your data folder and never overwrites what you logged by hand
(sets, notes, effort, a treadmill's belt distance).

## Garmin Connect

Adds steps, calories burnt, sleep with stages, overnight HRV, resting heart rate, body battery, stress, and
every activity with its heart-rate trace, zones and recovery heart rate.

Connect from the dashboard: **Connections** (at the foot of every page) › Garmin Connect, then your Garmin email and
password, and the code Garmin sends if your account has two-step verification. The password is used once to get a
token (saved to `~/.garminconnect`, owner-only, renewed automatically) and is never stored; the half-finished
two-step login lives only in the dashboard's memory, for at most 10 minutes and 5 tries. Or from the console:

```bash
.venv/bin/python scripts/garmin_login.py                 # once: password and MFA; token saved to ~/.garminconnect
.venv/bin/python scripts/garmin_pull.py --since 2026-07-01   # back-fill history
```

While the dashboard is running it pulls four times a day (08:00, 13:00, 19:00, 22:00) and catches up after the
computer wakes; there's a "Sync now" button in the header. If the header says the sync failed, the token has
expired: log in again on the Connections page (or run `garmin_login.py`).

Raw responses are saved in `imports/garmin/` with personal and location fields removed. After a change to how
fields are mapped, `garmin_pull.py --remap` re-applies them without fetching again.

> Uses the unofficial [`garminconnect`](https://github.com/cyberjunky/python-garminconnect) library. It isn't
> endorsed by Garmin and can break when Garmin changes its site. Use at your own risk.

## Abbott LibreLinkUp (continuous glucose)

Adds glucose readings from a FreeStyle Libre sensor shared through LibreLinkUp.

**First, a LibreLinkUp account.** The dashboard can't read the LibreLink app (the one on the phone your sensor
talks to) directly. It reads the copy LibreLink shares with **LibreLinkUp**, Abbott's app for family and carers. So:

1. Install LibreLinkUp and create an account. Use a different email from your LibreLink account; a `+` alias
   (you+cgm@example.com) usually works.
2. In the **LibreLink** app: Menu › Connected Apps › LibreLinkUp › Add connection, and invite that email.
3. In **LibreLinkUp**, accept the invite. You should see your own glucose there.
4. Use the LibreLinkUp email and password below, not your LibreLink ones.

If LibreLinkUp asks you to accept new terms or verify your email, do it in the app first; the dashboard tells you
when that's the problem.

Connect from the dashboard: **Connections** (at the foot of every page) › FreeStyle Libre, then your LibreLinkUp
email and password. The page shows when it last pulled and the latest reading, warns when LibreLinkUp has nothing
new (an expired sensor, or sharing turned off), and can pull now or disconnect (which removes the password from the
keychain; readings already pulled stay). The password is sent once, to this computer's dashboard only, and never
written to a file or log. Or from the console:

```bash
.venv/bin/python scripts/libre_login.py     # once: email saved to ~/.body-kaizen/libre.json, password to the keychain
```

The dashboard then pulls every 30 minutes. The Day timeline draws the glucose curve with a dot for each meal at the
time it was eaten (sized by carbs; hover for the foods and that meal's rise), and a table below gives each timed meal's
rise, peak and minutes back to baseline. The Body tab shows the last 14 days: daily stats, a 24-hour profile and
meals ranked by spike.

> Uses the unofficial [`pylibrelinkup`](https://github.com/robberwick/pylibrelinkup) library. Not endorsed by
> Abbott. Use at your own risk, and never for treatment decisions.

## Hevy

Two ways in:

- **Day to day:** paste the text of a finished workout (Hevy's share button → copy) to your assistant. It logs every
  set straight into the day file, next to the Garmin data for the same session.
- **Circuits:** if you loop groups of lifts (one set of each, round again), tell your assistant the groups once,
  for example "1: squat, chin-up. 2: RDL, fly, face pull". It records them as `circuits:` on each session, and
  the Training tab then labels every heart-rate peak with the set it came from. Mention it when you change the
  order.
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

## Something missing?

If there's a watch, ring, scale, CGM, gym app or health service you'd like Body Kaizen to read from,
[ask for it on GitHub](https://github.com/craigbennett1981/body-kaizen/issues/new?template=integration_request.yml) (a short form): say what it is, what data you'd want from it, and whether it has an export
or an API. Requests shape what gets built next.
