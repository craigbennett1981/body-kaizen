# Body Kaizen: data schema

Everything lives in your data folder (`FT_DATA`): one YAML file per day at `days/YYYY/YYYY-MM-DD.yaml`, plus
reference data (`foods.yaml`, `exercises.yaml`, `targets.yaml`, `settings.yaml`) and imports from the syncs.

Daily input is shorthand sent to your AI assistant, which expands it into the day file, runs `scripts/compute.py`
and commits. Defaults in `settings.yaml` mean you only type what differs.

---

## Day file

```yaml
date: 2026-10-15
status: complete            # complete | partial | unlogged
day_type: training          # rest | training | big  (derived from exercise if omitted)
note: ""                    # free text: travel, wedding, ill, etc.

weight:                     # morning weigh-in, optional
  kg: 75.3
  fasted: true
  bf_pct: 17.0              # home scale, optional
  muscle_kg: 59.5
  ffm_kg: 62.5

recovery:                   # morning Garmin check, optional
  rhr: 47
  hrv_ms: 73
  hrv_status: balanced      # balanced | unbalanced | low
  sleep: "7h12m"
  sleep_score: 81
  body_battery: 56          # overnight charge
  awake_min: 0

feel: {overall: 4, mood: 4, energy: 4, gut: 3, stress: 2, note: "flat after lunch"}   # 1–5 (stress: 5 = very stressed), all optional
habits: {screens_off: "21:40", walk_after_dinner: true}   # habits declared in experiments.yaml, from chat

symptoms:                   # health issues reported that day, any number
  - {what: headache, severity: 1, time: "15:00", note: "after screen-heavy day"}   # severity 1 mild, 2 moderate, 3 severe
  - {what: bloating, severity: 2}
  - {what: sore-shoulder, severity: 1, area: left}

vitals:
  bp:                       # any number of readings
    - {time: "07:10", sys: 118, dia: 76, pulse: 52, context: morning}
    - {time: "21:30", sys: 124, dia: 80, pulse: 61, context: post-exercise}
  # context: morning | evening | pre-exercise | post-exercise | post-meal | other
  # arm / position / device default from settings.yaml


steps: 11250

coach:                      # notes written by your assistant when logging; shown first on the Day view
  - {kind: bad,  text: "Second late session this week before a poor night — keep gym before 7pm."}
  - {kind: good, text: "Sat fat under 20g three days running."}
  # kind: good (win, green) | bad (warning, red) | info (observation, grey)

exercise: [ ...sessions, see below... ]

meals:
  breakfast: [ ...items... ]
  lunch:     [ ...items... ]
  dinner:    [ ...items... ]
  snacks:    [ ...items, each with optional `after: breakfast|lunch|dinner` ]

totals:                     # COMPUTED — never hand-edited
  kcal: 1985
  protein_g: 128
  carbs_g: 210
  fat_g: 58
  satfat_g: 17
  fibre_g: 29
  sodium_mg: 2100
  caffeine_mg: 90
```

### Food items

Each entry keeps what was typed (`raw`) and what it resolved to (`parsed`).
`parsed` and `totals` are written by `scripts/compute.py` — never edit by hand;
fix `foods.yaml` / `overrides.yaml` and re-run instead.

```yaml
- raw: "Yoghurt 140g + 1/2 scoop protein powder"
  parsed:
  - {item: scoop, n: 0.5}
  - {item: yogurt, g: 140}
- raw: "Fried chicken leg 202g (skin and bone 82g not eaten"
  parsed:
  - {item: chicken-leg, g: 202, excluded_g: 82}
- raw: "Breaded chicken cutlet 810cal"
  parsed:
  - {item: chicken-breaded, kcal: 810, conf: med}
- {raw: "Ice cream 215 calories", after: dinner, parsed: [...]}   # snacks carry `after`
```

| parsed field | meaning |
|--------------|---------|
| `item`       | key in `foods.yaml` |
| `g`          | weight (cooked unless `raw_weight: true`) |
| `ml`         | volume, for drinks (foods with `liquid: true`); always used for fluids |
| `n`          | count, for unit foods (egg, tea, scoop, slice, bar) |
| `kcal`       | calorie figure given; macros scaled from the food's profile |
| `excluded_g` | not eaten (bone, skin, trimmed fat) |
| `conf`       | omitted = high · `med` (estimated amount) · `low` (guessed portion) |

Resolution rules live in `scripts/nutrition.py`; one-off phrasings that the
parser can't read go in `overrides.yaml`. A brand change on a date (a new milk from the 20th) goes in `eras:` in `settings.yaml`.

`totals.low_confidence_kcal_pct` = share of the day's kcal from guessed portions.

### Exercise sessions

Common fields on every session:

```yaml
- type: gym                 # gym | run | swim | yoga | ruck | walk | scooter | other
  start: "16:22"
  duration_min: 41
  source: garmin            # garmin | apple | hevy | treadmill | manual | chat-history
  hr: {avg: 120, max: 145, recovery: 35}
  kcal: {total: 327, active: 240}
  rpe: 6                    # 1–10
  note: ""
  coach:                    # your assistant's comments on the session; shown on the Training tab and the Day page
    - {kind: good, text: "Three bests: cable fly 54.4 x 12, RDL 70 x 12, row reset done."}
    - {kind: bad,  text: "Heavy legs the day before a pace run."}
    - {kind: info, text: "Accessories matched last session."}
    # kind: good (win) | bad (warning) | info (observation)
```

`circuits:` (optional) says how the session was run: each inner list is a circuit of lifts done one set each,
looped until their sets run out, and the circuits come in the order they were done. A lift on its own,
`[leg-curl]`, means straight sets. With it, the Training tab labels each heart-rate peak with its set (hover a dot
on the trace: "Chin up · set 2 of 3 · bw×8"). The peaks are split between circuits at the longest gaps (moving
to new equipment); a stray peak such as a warm-up walk is left unlabelled. Without `circuits:`, peaks are shown
but not labelled, because Hevy doesn't record when each set happened. Names are `exercises.yaml` keys.

Each lift can also carry `note:` (your assistant's comment on that lift, shown under it). Bodyweight sets are
written `'0x8'` **in quotes** (unquoted, YAML reads `0x8` as the hex number 8).

Type-specific:

```yaml
# gym
  lifts:
    - {ex: smith-squat,    sets: [20x10, 40x10, 50x10, 60x10]}
    - {ex: leg-curl,       sets: [86.2x10, 86.2x10, 86.2x10]}
    - {ex: farmers-walk,   sets: [50kg@60m, 50kg@60m, 50kg@60m]}
    - {ex: plank,          sets: [60s, 60s, 60s]}
# set notation: <kg>x<reps> | <kg>kg@<m>m | <sec>s
  circuits:                 # optional: the order the sets were done in (see below)
    - [smith-squat, chin-up]
    - [leg-curl, farmers-walk, plank]

# run
  mode: treadmill           # treadmill | outdoor | trail
  effort: easy              # easy | pace | progressive | long | intervals
  distance_km: 5.0
  distance_source: belt     # belt | watch | gps
  time: "34:52"
  moving_time: "34:30"
  zones_min: {z1: 12, z2: 22}
  cadence: 165
  temp_c: 31
  # computed: pace_per_km

# swim
  distance_m: 625
  pool_m: 25
  stroke: freestyle

# ruck
  distance_km: 7
  load_kg: 10
  time: "1:15:00"

# yoga
  style: vinyasa
```

---

## Chat shorthand (input)

```
15 oct
w 75.3
bp 07:10 118/76 p52
feel 4 mood 4 gut 3 energy 4 stress 2
sym headache mild 15:00, bloating moderate, sore shoulder (left) mild
gym 4:22pm 41min hr120/145 327cal
  leg curl 86.2x10 x3
  farmers 50kg 60m x3
run treadmill easy 5km 34:52 hr124/135 rec35 rpe2
B 07:30: sourdough 56, 2 egg, 2 tea, yog 140 + chia 105     # a time after the meal letter links it to the glucose curve
L: chicken breast 145, pasta 137 cream sauce
D: rice 78, pork chop 134, spinach 65
S: mooncake 90cal
```

- Order doesn't matter; partial days are fine — send more later.
- Named meals from `meals.yaml`: `b1`, `shake`, `cr`, `sr` (and `2x shake`). Add your own there.
- New packaged food? Send a photo of the nutrition label: it's added to `foods.yaml` with `conf: label`.
- `x3` = three identical sets. `90cal` = calorie override.
- Anything ambiguous gets flagged back in the summary before commit.

---

## Files

In your data folder:

| path | purpose |
|------|---------|
| `days/YYYY/*.yaml` | one file per day |
| `settings.yaml` | your profile (name, start date), timezone, input defaults, `eras`, `git` options (below) |
| `targets.yaml` | versioned intake targets (effective-from dates) and how they're paced through the day |
| `foods.yaml` | your own foods (optional): added to the starter list in the code, same key = yours wins. The Food tab counts fruit, veg, nuts, grains and beans as plants; set `plant: true` or `plant: false` on a food to overrule it |
| `meals.yaml` | named meals (one word expands to several items) |
| `overrides.yaml` | exact logged phrasings → components, for text the matcher gets wrong |
| `exercises.yaml` | lift catalogue: aliases, equipment, equipment epochs, progression rules |
| `athlete.yaml`, `markers.yaml` | reference points for the health score; long-term markers with target bands |
| `measurements/` | blood tests, InBody scans, functional tests, episodes, supplements |
| `imports/` | raw responses from Garmin, LibreLinkUp and Hevy |
| `events.yaml`, `todo.yaml` | timeline events; your to-do list |
| `experiments.yaml` | n-of-1 experiments for the Experiments tab (below) |

In the code: `foods/starter.yaml` (starter food list), `scripts/` (`nutrition.py` matcher, `compute.py` totals, syncs and
imports), `app/` (dashboard).

### experiments.yaml

An experiment is a rule kept for a number of nights, and the outcomes it should move. Nights are keyed by the
morning you wake up: `night.*` is that night's sleep and the morning's HRV and resting heart rate; `day.*`, `food.*`
and `habit.*` are the day before it (the day you went to bed on).

```yaml
habits:                         # things no device records, logged in day files (below); declare them to test them
  screens_off: {type: time, label: Screens off}        # type: time | bool | num | min
  walk_after_dinner: {type: bool}
experiments:
  - id: screens                 # short, unique
    title: Screens off by 21:30
    start: 2026-11-08           # the first evening; the first night counted is the one you wake from on the 9th
    days: 14                    # nights, 3 to 60; 14 if left out
    rule:
      all:                      # or any:
        - {var: habit.screens_off, op: "<=", value: "21:30"}
        - {var: day.caffeine_last, op: "<=", value: "14:00"}
    outcomes: [night.asleep, night.score, night.hrv]   # the default; {var: night.awake, better: lower} to say which way is good
    hypothesis: Screens off earlier helps me fall asleep sooner.   # optional
    baseline_days: 28           # optional: nights before the start to compare with
    status: stopped             # optional: only to end one early; otherwise worked out from the dates
    notes: Asleep 20 min sooner on kept nights; keeping it.   # optional: the write-up, added when it finishes
    requires: [bp.evening]      # optional: extra readings to remind about (below)
  - id: salt                    # a period experiment: a daily habit, and readings that move over days, not one night
    type: period
    title: Sodium under 2 g a day
    start: 2026-11-08           # the first day of the habit
    days: 21
    ramp_days: 3                # optional, default 3: readings from the first days are left out while any effect builds
    daily:                      # checked against each day, like rule: (no night.*, bp.* or weight.* in it)
      all: [{var: day.sodium, op: "<=", value: 2000}]
    outcomes: [bp.morning_sys, bp.morning_dia]         # required; weight.kg needs {var: weight.kg, better: lower} or higher
```

Operators: `<=`, `>=`, `<`, `>`, `=`, `!=` (yes/no variables take `=` or `!=` with `true` or `false`). Times are
`"HH:MM"`. The first shorthand still works: `rule: {bedtime_by: "22:30"}`, `session_end_by`, `last_meal_by`,
`caffeine_cutoff`, `sat_fat_max`, `steps_min`.

| variable | what it is |
|---|---|
| `night.bedtime`, `night.wake` | asleep at, woke at (times; outcomes: earlier bedtime counts as better) |
| `night.asleep`, `night.deep`, `night.rem`, `night.awake` | minutes asleep, in deep and REM sleep, awake in the night |
| `night.score`, `night.hrv`, `night.rhr`, `night.battery` | sleep score, overnight HRV, resting heart rate, body battery on waking |
| `day.kcal`, `day.protein`, `day.carbs`, `day.fat`, `day.satfat`, `day.fibre`, `day.sodium`, `day.caffeine` | the day's totals |
| `day.caffeine_last`, `day.first_meal`, `day.last_meal` | times: last food or drink with 20 mg+ caffeine, first and last timed food |
| `day.dinner_kcal`, `day.dinner_carbs` | dinner's calories and carbs |
| `day.trained`, `day.session_end`, `day.steps`, `day.stress` | trained (yes/no), when the last session ended, steps, average stress |
| `food.<key>` | yes/no: had that food or supplement (any key in your food list) |
| `amount.<key>` | how much of it: g, ml, or servings for foods logged by count |
| `habit.<name>` | a habit declared above |
| `bp.morning_sys`, `bp.morning_dia`, `bp.morning_pulse`, `bp.evening_sys`, `bp.evening_dia` | that date's blood pressure, the average of its morning or evening readings (period outcomes) |
| `weight.kg` | that morning's fasted weight (period outcome) |

Night experiments take `night.*` outcomes; period experiments take `night.*`, `bp.*` and `weight.*`. A time that didn't happen (no training, no caffeine, no timed food) keeps
a "by" rule (`<=` or `<`). A night with no value for the rule is left out, not counted either way. Unknown
variables, operators or values are listed on the Experiments tab and that experiment isn't scored.

Kept nights are compared with the baseline nights; each outcome gets the difference and a 90% range from
resampling, and only counts as better or worse when the whole range is on one side of zero. A finished experiment
needs 60% of judged nights kept (and at least 5) for a verdict.

A period experiment compares the period's readings (after the ramp-up) with the baseline's, resampling runs of 3
days because one day's reading is close to the next. It needs 7+ readings on each side and 75% of days kept. If an
outcome was already drifting the same way before the start, and that drift would explain at least 30% of the
change, the verdict is "Could be a trend" instead of "It worked".

While one runs, the card shows what's left and how many more misses it can take and still give a verdict; early
results read "leaning better" or "leaning worse", since the range is wide and can flip. A toast marks the halfway
point and the finish (with the verdict and what to do next).

Each running or planned experiment has a checklist for today on its card: the readings it is judged on (needed
during the baseline weeks too), and once it has started, the rule. Readings follow from the outcomes and rule
(`bp.morning_*` needs a morning reading, `weight.kg` a weigh-in, `night.*` the watch worn overnight); `requires:`
adds more, from `bp.morning`, `bp.evening`, `weight`, `sleep` or a `habit.*`/`food.*` variable to log. Anything not
done by its time shows as a dashboard toast, dismissed for the day: morning readings from 10:00, food from 20:00,
habits from 21:00, an evening reading from 21:30, and a bedtime rule 45 minutes before the time.

### settings.yaml

```yaml
profile: {name: Sam, start_date: 2026-07-26}   # asked for on first open; click your name in the header to change
timezone: Europe/London                         # IANA name; detected on first open
units: metric                                   # metric (default) or imperial: how weights, distances and portions are shown; files stay metric
food: {weights_are: cooked, egg: boiled}        # input defaults
eras:                                           # which food a generic name means on each date (a brand change)
  milk-lowfat:
    - {from: 2026-10-20, use: milk-brand-b-lowfat}
git: {auto_commit: true, auto_push: false}      # commit after each sync; push only if you turn it on
```
### exercises.yaml: muscle tags

Each lift lists the muscles it works, which drive the muscle map on the Training tab and the weekly sets table:

```yaml
lifts:
  seated-row:
    aliases: [row, seated row, cable row]
    muscles: [upper-back]                    # primary: every working set counts
    secondary: [biceps, rear-delts, traps]   # secondary: each set counts half
```

Muscle names: `chest`, `front-delts`, `rear-delts`, `biceps`, `triceps`, `forearms`, `abs`, `obliques`, `traps`,
`upper-back`, `lower-back`, `glutes`, `quads`, `hamstrings`, `adductors`, `calves`. Broad names still work and
spread across the muscles they cover: `shoulders`, `back`, `core`, `grip`, `legs`.

Runs, walks, rucks, swims, yoga and rides count too, as set-equivalents: every 10 minutes is one set for the main
muscles and half a set for the supporting ones (a 25-minute run: 2.5 sets for quads, hamstrings, glutes and calves).
To change which muscles an activity works, add an `activities:` block in the same shape:

```yaml
activities:
  run: {muscles: [quads, hamstrings, glutes, calves], secondary: [abs, obliques, adductors]}
```

### exercises.yaml: weekly plan

`training_plan.week` sets what each weekday is for; the Training tab shows the next seven days under "Next session".

```yaml
training_plan:
  week:
    mon: {kind: gym, name: Full-body gym}
    tue: {kind: run, session: easy}
    thu: {kind: run, session: [octopus, long-easy]}   # a list alternates week to week
    sat: {kind: run, session: intervals}
    sun: {kind: rest, name: Rest}
  week_from: 2026-11-02                               # week 1 of the pattern
  every_gym: ["Calf raise 3 x 15"]                    # shown on every gym day
  runs:
    easy: {name: Easy run, detail: "30-40 min under 140 bpm"}
    intervals: {name: VO2 max intervals, detail: "...", progression: ["5 x 3 min", "6 x 3 min"]}   # one step a week
  run_test: {every_weeks: 5, baseline: {date: 2026-10-27, what: 5K, time: "25:20"}}
```

## Commit convention

`YYYY-MM-DD: <what changed>` e.g. `2026-10-16: breakfast, gym, bp`.
Corrections are new commits: `2026-10-16: fix lunch rice 120g`.

## Meal times and glucose

Any meal entry can carry `time: "13:10"`. With a FreeStyle Libre connected, timed meals get a glucose response
(before, peak, rise, time to peak, minutes back to baseline). CGM readings live in `imports/libre/YYYY/YYYY-MM-DD.json`
(`readings: {"HH:MM": mmol/L}`), pulled every 30 minutes through LibreLinkUp (scripts/libre_login.py once, then automatic).

## Blood pressure timing

Give each reading a time (`bp 07:10 118/76 p52`): morning readings and evening readings are summarised separately.

## Item times

Every food item carries the time it was eaten: `time: "13:10"` on the entry. Shorthand: put the time first on each item,
e.g. `13:10 rice 102, 13:10 beef 125, 15:00 dates 52`, or once per meal line (`L 13:10: rice 102, beef 125`) to apply it to every item.
Items within 20 minutes of each other are treated as one eating event when matching against glucose.
