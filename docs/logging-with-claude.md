# Logging with Claude

Body Kaizen has no input screens. You talk to **Claude** (or another AI assistant that can edit files and run
commands), and it writes everything into your data folder. This guide covers setting it up and everything you
can feed it.

## How it works

```
 you ──message / photo──▶ Claude ──edits──▶ days/2026/2026-10-23.yaml
                                  ──runs───▶ scripts/compute.py 2026-10-23   (recalculates totals)
                                  ──commits─▶ your private data repo
 you ◀──totals vs targets, what to do next──┘           dashboard shows it on refresh
```

Claude needs three things: **read and write access to your data folder**, the ability to **run commands** there
(for `compute.py` and `git`), and **standing instructions** saying how you want it done.

## Setting it up

### Option A: Claude Code, or a Claude desktop session with your folder connected

1. Open your data folder in Claude Code (`cd ~/body-kaizen-data && claude`), or connect the folder to a
   Claude desktop session.
2. Copy [`CLAUDE.example.md`](CLAUDE.example.md) into the data folder as **`CLAUDE.md`** and edit it. Claude
   reads it at the start of every session, so it knows the format, your defaults and how to reply.
3. Set `FT_CODE` in that file to where you cloned Body Kaizen, so Claude can run `compute.py`.

### Option B: a Claude project

Make a project (for example "Food tracker"), connect your data folder to it, and paste the contents of
`CLAUDE.example.md` into the project's instructions. Also add [`AI-GUIDE.md`](../AI-GUIDE.md) and
[`SCHEMA.md`](../SCHEMA.md) to the project's files, since the project can't read your code folder. Every chat in
the project then logs the same way, from your phone or your computer.

### Other assistants

Anything with file editing and a shell works. Give it [`AI-GUIDE.md`](../AI-GUIDE.md) (the full brief) plus your edited
`CLAUDE.example.md`, under whatever name that tool reads (often `AGENTS.md`).

## What you can feed it

Send things as they happen, in any order, in plain words. Partial days are fine; just send more later.

### Food and drink

| Send | Example | What happens |
|---|---|---|
| Items with weights | `lunch: chicken breast 172g, pasta 179g` | Matched to `foods.yaml`, logged under lunch with the time |
| Raw or cooked | `52g oats (uncooked), made with water` | Weighed state noted so the macros are right |
| Drinks | `english breakfast tea with milk`, `300ml low fat milk + 1 scoop protein` | Your defaults in `settings.yaml` fill in which milk, what a scoop is |
| Named meals | `b1`, `2x shake` | Expanded from `meals.yaml` |
| A calorie figure | `custard mooncake 90 cal` | Logged by calories when there's no weight |
| **A nutrition label photo** | 📷 back of the pack + `add 1 serving` | New entry in `foods.yaml` with the label's figures (`conf: label`), then logged |
| **A photo of a plate** | 📷 + `rice may be 120g, rest looks right` | Identified and estimated, marked as an estimate, adjusted by what you say |
| Combined weights | `apple and grapefruit 180g combined` | Split into the two foods |
| Corrections | `the leg was 160g with the bone`, `that was 3 sets not 4` | Fixed, and recorded in `overrides.yaml` so it stays fixed |

### Body and vitals

| Send | Example |
|---|---|
| **Scale app screenshot** | 📷 weight, body fat, muscle, visceral fat, water, BMR: all fields logged as the morning weigh-in |
| Weight in text | `w 75.3` |
| **Blood-pressure app screenshot** | 📷 or `bp 07:10 118/76 p52` |
| InBody or similar scan | 📷 / PDF of the printout → `measurements/inbody.yaml` |
| **Blood test report** | 📷 / PDF → `measurements/labs.yaml`, values exactly as the lab reported them, with its reference ranges |
| Functional tests | `grip 46/44`, `sit to stand 22`, `waist 84` |
| Supplements | `started vitamin D3 daily from today` |

ID numbers, dates of birth and addresses on reports aren't stored; tell Claude to leave them out in your
instructions.

### Training

| Send | Example |
|---|---|
| **Hevy workout** | Paste the text from Hevy's share button: every set is logged |
| Gym in shorthand | `leg curl 86.2x10 x3`, `farmers 50kg 60m x3` |
| Runs and other sessions | `run treadmill easy 5km 34:52 hr124`, `swim 625m`, `ruck 7km 10kg` |
| What the day is | `gym today`, `rest day`: sets the calorie target |
| Corrections to watch data | `recovery HR is wrong, I didn't start it on time`, `belt said 5.0 km` |

Watch data (sleep, HRV, steps, heart rate) comes from the Garmin sync on its own; you don't send it.

### How you feel

| Send | Example |
|---|---|
| Daily scores (1–5) | `feel 4 mood 4 energy 3 gut 3 stress 2` |
| Symptoms | `headache mild 15:00`, `bloating moderate` |
| Notes | `slept around 10pm but kept waking; watch sleep is wrong` |
| Off spells | `been flat since Tuesday, gut not great` → logged as an episode |
| Life events | `new gym from Monday`, `travelling 3–9 Nov` → timeline |

### Questions and changes

You can also just ask: "how many calories in that?", "how does this yogurt compare to my usual one?",
"what's my VO2 max?", "plan tomorrow's gym session". And change things: "move my protein target to 160 g
from Monday", "the milk is the new brand from today".

## What a good reply looks like

Put this in your instructions. After each log, Claude replies with the day so far against your targets:

| 23 Oct (gym day) | So far | Target |
|---|---|---|
| Calories | 588 | 2,250–2,350 |
| Protein | **38 g** | ≥150 g |
| Saturated fat | **4.9 g** ✅ | ≤20 g |
| Fibre | **13.2 g** ✅ | ≥30 g |

…and one line on what to do next ("lunch needs about 50 g of protein").

## Tips

- **Weigh food when you can.** Weights beat guesses; Claude marks guesses `conf: med` or `conf: low`, and the
  Day page shows what share of your calories came from guessed portions.
- **Put your habits in `settings.yaml` and `meals.yaml`** so messages stay short.
- **Say when the day is done** ("close the day") so it gets judged against the full-day targets.
- **Ask for the tone you want.** Gentle encouragement or blunt pushback: it's one line in your instructions.

## Privacy

Claude reads and writes your health data. Check your Claude data-retention settings, keep the data repository
private, and keep credentials out of it. See [SECURITY.md](../SECURITY.md).
