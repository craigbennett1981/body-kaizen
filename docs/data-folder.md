# The data folder

Body Kaizen keeps your data in its own folder, separate from the code. The dashboard asks where on first run (the
installer opens it there) and remembers the choice in `~/.body-kaizen/config.json`. To point it somewhere else for one
run, set `FT_DATA` or pass `--data`:

```bash
body-kaizen --data ~/body-kaizen-data          # or, from the code: FT_DATA=~/body-kaizen-data python app/server.py
```

Keep this folder in a **private** git repository (or none). The dashboard and the scripts read and write only
inside it. The code folder is never written to, so you can update Body Kaizen with a plain `git pull`.

`demo/` in this repository is a complete example; `body-kaizen init DIR` starts a new folder from its reference files
without the demo person. View the demo with `body-kaizen demo`, or from the code `FT_NO_SYNC=1 FT_DATA=demo python app/server.py`. Syncs never run, and nothing is committed, while the
data folder is `demo/`, still has the demo profile ("Sam (demo)"), or sits anywhere inside the code folder.

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

## How your data is kept

First-run setup asks which of these you want. You can switch later.

| | Plain files | Git history on this computer | Git, plus a private GitHub backup |
|---|---|---|---|
| Needs | nothing | [git](https://git-scm.com/downloads) | git and a GitHub account |
| Every change saved as a version | no | yes | yes |
| Undo a bad edit, see what changed | no | yes | yes |
| A copy off this computer | only your own backups | only your own backups | yes, in your private repository |
| Data leaves this computer | no | no | yes, to GitHub (private) |

### Plain files

The simplest: a folder of text files and nothing else. The dashboard and your assistant work exactly the same. What
you give up is history: if a file is overwritten or deleted, it's gone. Back the folder up with the tools you already
use: Time Machine on a Mac, File History on Windows, or a copy on an external drive. A cloud-synced folder (iCloud
Drive, Dropbox, OneDrive) works too, but then your health data is stored online with that service.

### Git history on this computer

The folder is a git repository. Your assistant commits after each change (`2026-11-11: dinner`) and the Garmin sync
commits what it pulls, so every version is kept and nothing leaves this computer. To see or undo changes:

```
cd ~/body-kaizen-data
git log --oneline            # what changed, newest first
git show HEAD                # the last change in full
git revert HEAD              # undo it (kept in the history)
```

Turn on git later in an existing folder with `git init && git add -A && git commit -m "start"`.

### A private backup on GitHub

The same, plus a copy on GitHub, so a lost or broken computer doesn't lose your data.

1. Create a **private** repository: on github.com, **New repository**, any name (say `body-kaizen-data`), set
   **Private**, and leave it empty (no README). Or with the [GitHub CLI](https://cli.github.com/):
   `gh repo create body-kaizen-data --private`.
2. Connect your data folder and push it:
   ```
   cd ~/body-kaizen-data
   git remote add origin https://github.com/<you>/body-kaizen-data.git
   git branch -M main
   git push -u origin main
   ```
3. Push again whenever you like (`git push`), or let the Garmin sync push after each run: set
   `git: {auto_push: true}` in `settings.yaml`.

Keep it **private**: it's your health data. Anyone you add as a collaborator can read all of it. For more protection,
encrypt the health files before they leave your computer with git-crypt ([SECURITY.md](../SECURITY.md#encryption-what-protects-your-data-where)).
