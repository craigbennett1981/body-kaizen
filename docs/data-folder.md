# The data folder

Body Kaizen keeps your data in its own folder, separate from the code, and finds it through the `FT_DATA`
environment variable:

```bash
FT_DATA=~/body-kaizen-data python app/server.py
```

Keep this folder in a **private** git repository (or none). The dashboard and the scripts read and write only
inside it. The code folder is never written to, so you can update Body Kaizen with a plain `git pull`.

`demo/` in this repository is a complete example. Copy it to start your own and clear out the dated files.

## Layout

```
body-kaizen-data/
├── days/YYYY/YYYY-MM-DD.yaml   one file per day: food, weight, vitals, training, recovery, notes
├── measurements/
│   ├── inbody.yaml             body-composition scans
│   ├── labs.yaml               blood test results, stored exactly as the lab reported them
│   ├── tests.yaml              functional tests: grip, sit-to-stand, one-leg stand, waist
│   ├── episodes.yaml           illness or injury periods, so the charts can explain dips
│   └── supplements.yaml        what you take and since when
├── imports/                    raw responses from synced services (garmin/, libre/, hevy/), kept so
│                               a mapping fix can be re-applied without fetching again
├── reviews/                    weekly write-ups, if you keep them
│
├── targets.yaml                calorie, protein, saturated-fat and fibre targets, versioned by date,
│                               and how they're paced through the day
├── settings.yaml               your profile (name, start date) and timezone, asked for on first open; input defaults;
│                               brand `eras`; `git` options (auto_commit on, auto_push off)
├── athlete.yaml                reference points for the health score: your age and sex, and what
│                               "top", "average" and "poor" mean for each marker
├── markers.yaml                long-term markers (lipids, BP, VO2 max…) with target bands and test intervals
├── exercises.yaml              your lifts: aliases, muscles, equipment changes, progression rules
├── meals.yaml                  named meals: type "b1" and it expands to your usual breakfast
├── foods.yaml                  (optional) your own foods; added to the code's foods/starter.yaml, same key = yours wins
├── overrides.yaml              fixes for log lines the food matcher gets wrong
├── events.yaml                 life and setup events shown on the timeline
└── todo.yaml                   a to-do list shown on the Day page
```

Every file is optional except `days/` and `targets.yaml`. A missing file means that feature has nothing to show.

## Day files

The format is in [SCHEMA.md](../SCHEMA.md). After editing a day by hand, run

```bash
FT_DATA=~/body-kaizen-data python scripts/compute.py 2026-10-23
```

to recompute its totals. With no date it recomputes every day.

## Targets

`targets.yaml` holds blocks that start on a date; each day uses the latest block that began on or before it, so
changing your targets never rewrites the past.

```yaml
intake:
  - from: 2026-10-12
    label: maintenance
    kcal:
      rest: [2050, 2150]       # day types come from the day's training
      training: [2250, 2350]
      big: [2400, 2500]
    protein_g: {min: 150}
    satfat_g: {max: 20}
    fibre_g: {min: 30}
```

The `pace:` section sets what share of each target belongs before lunch, between lunch and dinner, and in the
evening. The Day page uses it to colour your macros while the day is still going.

## Backing up

It's a folder of text files: commit it, and push it to a **private** remote.
