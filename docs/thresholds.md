# Thresholds

Every number Body Kaizen judges your data against, where it is defined and where it comes from. The dashboard
shows the same list, with your own values filled in, on **How your numbers are judged**, linked at the foot of the dashboard (`/thresholds.html`).

Two kinds:

- **Your own targets and bands**, in your data folder: `targets.yaml` (calorie, protein, saturated fat, fibre,
  fat and carb targets; weight target; pace windows; reference points such as the easy-run heart-rate cap, sleep
  target and the resting-HR walk-only line), `markers.yaml` (green and amber bands, test intervals and notes for
  every longevity marker), `athlete.yaml` (the health score's top / average / poor reference points) and
  `exercises.yaml` (`training_plan`: rep range, sets, deload rhythm, weekly sets guide). Change them there; the
  page always shows what is in force.
- **Rules fixed in the code**, listed below. They live in `app/thresholds.py` (`RULES`) as well, so the page and
  this file must be edited together.

Basis: a named guideline when the code relies on one; *(inferred)* when a guideline obviously underlies the number
but the code doesn't cite it; *heuristic* for a hand-set judgement; *no source* when nothing better can honestly
be said. These are self-tracking aids, not medical advice.

We make a best effort to get these right, but guidelines change and we can get them wrong. If you spot a
problem, please [raise a GitHub issue](https://github.com/craigbennett1981/body-kaizen/issues).

## Food and the day's macros

| Threshold | Rule | Basis | Shown on | Defined in |
|---|---|---|---|---|
| Day judged | Each target is ticked or crossed only once the day is closed; before that you see over/under arrows | design rule | Day, Trends, Week | `data.py evaluate` |
| Live colour | Inside the target = green; missed by up to 10% = amber; more = red | heuristic | Day macro tiles | `app.js liveStatus` |
| High sat-fat food | A single food item with 3 g or more saturated fat is tinted red | heuristic | Day timeline | `app.js SF_HIGH` |
| Guessed portions | A note when 15% or more of the day's calories come from low-confidence estimates | heuristic | Day notes | `insights.py` |
| Protein spread | Counts feeds of 30 g protein or more; suggests four of 35–40 g when the target is 150 g+ | muscle protein synthesis research (inferred); heuristic | Day notes | `insights.py` |
| Under-eating week | Under the calorie floor on 60%+ of the last 7 closed days (needs 4+) | heuristic | Day notes | `insights.py` |

## Pace through the day

| Threshold | Rule | Basis | Shown on | Defined in |
|---|---|---|---|---|
| Floors and ranges | Eaten ÷ expected-so-far: 85%+ green, 65–85% amber, below red (85% and 65% are adjustable in your pace settings) | heuristic | Day pace strips | `pace.py` |
| Caps (saturated fat) | Up to 105% of the allowance so far green, up to 125% amber, above red; over the full-day cap is always red | heuristic | Day pace strips | `pace.py` |
| Range ceiling | More than 115% of the upper end so far = amber (red once over the full-day upper) | heuristic | Day pace strips | `pace.py` |
| Next move | Sat-fat warning when under 8 g is left; protein prompt when 5 g+ is still needed; fibre prompt after 12:00 when 5 g+ short | heuristic | Day 'next move' line | `glance.py` |

## Blood pressure

| Threshold | Rule | Basis | Shown on | Defined in |
|---|---|---|---|---|
| Category | Normal under 120/80; elevated 120–129 systolic; stage 1 130–139 or 80–89; stage 2 140+ or 90+; crisis 180+ or 120+ | 2017 ACC/AHA adult guideline | Body, Day notes, Doctor page | `data.py bp_category` |
| Morning reading | Taken before 09:00 (adjustable in your settings) | measurement practice: same time, before coffee | Body (30-day morning average) | `data.py` |
| Pulse pressure | Systolic − diastolic: under 30 narrow; 30–50 healthy; 50–60 upper normal; over 60 wide, worth watching | 40 typical and 60+ linked with artery stiffness in cohort studies (common rule of thumb); 30 and 50 cut-offs are heuristic | Body | `app.js ppCat` |

## Glucose (CGM)

| Threshold | Rule | Basis | Shown on | Defined in |
|---|---|---|---|---|
| In range | 3.9–7.8 mmol/L | non-diabetic 'tight range' (inferred); the 2019 International Consensus 3.9–10.0 range is for diabetes | Day glucose panel, Body | `glucose.py LOW, HIGH` |
| Sensor settling | First 24 h of each sensor left out of rolling figures | first-day sensor accuracy is lower (manufacturer guidance, inferred) | Body | `glucose.py SETTLE_H` |
| Time in range chip | 95%+ green, under 85% red | mirrors the cgm_tir marker | Day, Body | `app.js` |
| Variability chip | CV 18% or less green, over 25% red | mirrors the cgm_cv marker | Day | `app.js` |
| Meal response | Baseline = mean of the 30 min before; rise measured over 150 min; rise of 3.0+ red, 1.5 or less green | heuristic, no source | Day, Body | `glucose.py, app.js` |
| GMI | 3.31 + 0.02392 × mean glucose (mg/dL) | Bergenstal et al. 2018 | Body | `glucose.py` |

## Sleep

| Threshold | Rule | Basis | Shown on | Defined in |
|---|---|---|---|---|
| Sleep score colour | Garmin score 80+ green, under 60 red | Garmin's own bands (inferred) | Day readiness strip | `app.js` |
| Late session | Gym or run starting at 19:00 or later followed by a sleep score under 70 = warning | heuristic | Day notes | `insights.py` |
| Short night | Under 7 h counts as short | AASM/SRS adult minimum of 7 h (inferred) | Advice | `advice.py` |
| Irregular bedtime | Sleep-onset standard deviation over 30 min = advice; over 60 min = alert | heuristic | Advice, Day notes, toasts | `advice.py, alerts.py` |
| Bedtime habit | Asleep within 30 min of the median of the previous 14 nights | heuristic | Week | `habits.py` |

## Recovery and readiness

| Threshold | Rule | Basis | Shown on | Defined in |
|---|---|---|---|---|
| Readiness bands | 70+ green, 50–69 amber, under 50 red | heuristic, checked by the built-in backtest against your logged off-episodes | Day, Recovery | `readiness.py BANDS` |
| Signals | Each costs points vs your own 28-day baseline: resting HR and HRV 9 per SD, sleep debt 9 per hour, training-load spike 35 per unit above 1.2, stress and body battery 4, feel 8 per point below 3 | heuristic | Day, Recovery | `readiness.py W` |
| Noise band | Within 0.5 SD of your baseline costs nothing | heuristic | Day, Recovery | `readiness.py NOISE` |
| Load spike | 7-day load ÷ 4-week load above 1.2 | acute:chronic workload ratio (Gabbett 2016, inferred) | Day, Recovery | `readiness.py` |
| HRV dip | HRV under 90% of your HRV baseline = 'go easier' | heuristic | Day notes | `insights.py` |
| Resting HR rising | 7-day mean more than 2 SD above the 60-day baseline for 3+ days | heuristic | Day notes, toasts | `alerts.py` |
| vs normal | Glance strip colours only gaps of 5 ms HRV or 3 bpm resting HR | heuristic | Day | `glance.py` |

## Heart rate, runs and workouts

| Threshold | Rule | Basis | Shown on | Defined in |
|---|---|---|---|---|
| HR zones | Z1–Z5 at 50/60/70/80/90% of max HR | %HRmax five-zone model (Garmin default, inferred) | Training workout trace | `workouts.py` |
| Max HR | The higher of 175 and your highest recorded session max | heuristic floor | Training | `workouts.py _max_hr` |
| Effort detection | Heart-rate peak 8+ bpm above the low since the last peak, 45 s+ apart | heuristic | Training workout trace | `workouts.py _trace` |
| Recovery HR | Drop in 2 min after stopping: 40+ excellent, 30+ good, 20+ fair, under 20 low | no source | Training workout | `app.js` |
| VO2 max drop | Latest under 95% of the value about 3 months earlier | heuristic | Day notes, toasts | `alerts.py` |

## Lifting and muscles

| Threshold | Rule | Basis | Shown on | Defined in |
|---|---|---|---|---|
| Double progression | All top sets at the top of the rep range: add the lift's smallest increment and drop to the bottom; any set below the range: hold; otherwise add a rep | standard double progression | Training plan | `planner.py` |
| Estimated 1RM | kg × (1 + reps ÷ 30) | Epley formula | Training, personal-best stars | `data.py, workouts.py` |
| Personal best | Estimated 1RM above every earlier session of that lift | design rule | Day, Training, Week | `data.py` |
| Warm-up sets | Under 75% of the session's top weight are ignored for weekly sets | heuristic | Training volume | `planner.py` |
| Secondary muscles | Count as half a set | common convention | Training | `planner.py, muscles.py` |
| Cardio on the muscle map | 10 minutes = 1 set for the main muscles | heuristic | Training muscle map | `muscles.py` |

## Health score

| Threshold | Rule | Basis | Shown on | Defined in |
|---|---|---|---|---|
| Scoring curve | 100 at the 'top' reference, 50 at 'average', 0 at 'poor', straight lines between | design; reference values below | Day, Longevity | `healthscore.py` |
| Unmeasured | A marker never measured, or stale, counts as 50 | design rule: no credit for unknowns | Day, Longevity | `healthscore.py UNMEASURED` |
| Stale after | Labs, InBody and manual tests 400 days; watch, CGM and calculated 21 days | heuristic | Day, Longevity | `healthscore.py STALE` |
| Domain colours | 80+ green, 55+ amber, below red | heuristic | Longevity | `app.js` |

## Advice and alerts

| Threshold | Rule | Basis | Shown on | Defined in |
|---|---|---|---|---|
| Steps | Enough = the start of the green band for steps in `markers.yaml` (7,000 a day in the starter file); `targets.yaml reference.steps_daily` is only a chart line | mortality benefit levels off around 7,000–8,000 steps (Paluch 2022; Ding 2025, both Lancet Public Health) | Advice, Day notes, Habits | `data.py steps_target` |
| Calories advice | In range on under 60% of the last 7 closed days = act | heuristic | Advice | `advice.py` |
| Sodium | 14-day average over 2,300 mg = act | WHO 2,000 mg / US Dietary Guidelines 2,300 mg (inferred) | Advice | `advice.py` |
| Protein alert | 7-day protein under 1.4 g/kg | heuristic (below the 1.6 g/kg Morton 2018 plateau) | Day notes, toasts | `alerts.py` |
| Lifting frequency | Under 2.5 gym sessions a week (30 days) = act | heuristic | Advice | `advice.py` |
| Cardio frequency | Under 2 cardio sessions a week = act | heuristic | Advice | `advice.py` |
| Weigh-in | No fasted weigh-in for more than 5 days = act | heuristic | Advice | `advice.py` |
| Weekly hit rate | 70%+ green, under 40% red | heuristic | Week | `app.js` |

## Longevity marker bands (`markers.yaml`)

Bands include the lower edge and exclude the upper. Green wins, then amber; anything outside both is red. 'contested' bands can make an in-range value amber, never red. 'lab' judges against the range printed on that lab report.

Markers marked `verify: true` carry a provisional target that has not yet been checked against a source; the
dashboard tags them. The starter `markers.yaml` notes the guideline behind each band where there is one (for
example 2017 ACC/AHA for blood pressure, InBody's 0.360–0.390 ECW ratio, AWGS 2019 for SMI, the lab's printed range
for `bands: lab`).

### Bands worth knowing the source of

| Marker | Green | Amber | Red | Source |
|---|---|---|---|---|
| ApoB | under 0.9 g/L | 0.9–1.0 | over 1.0 | NLA expert consensus 2024 (Soffer et al., *J Clin Lipidol*): 0.9 g/L for borderline-to-intermediate risk (0.7 high, 0.6 very high). 1.0 is the ESC/EAS 2019 moderate-risk goal. The Singapore lipid guideline (ACG 2023) sets no ApoB target. |
| Systolic BP (30-day avg) | under 120 | 120–129 (elevated) | 130+ (stage 1 and over) | 2017 ACC/AHA |
| Diastolic BP (30-day avg) | under 80 | none | 80+ (stage 1 and over) | 2017 ACC/AHA: diastolic has no "elevated" band, so stage 1 is red, as it is for systolic |
| Protein (7-day avg) | 1.6 g/kg or more | 1.2–1.6 | under 1.2 | Muscle gain plateaus near 1.6 g/kg (Morton et al. 2018, *Br J Sports Med*; upper CI ~2.2). No upper limit: more isn't harmful with healthy kidneys |
| Body fat (InBody) | 8–20% | 20–25% | under 8% or over 25% | Male athletic range. Bioimpedance reads ~3–4 points under DXA, so 8% InBody ≈ 11–12% DXA. Women need about 8 points more: edit the bands |
| Steps (30-day avg) | 7,000+ | 5,000–7,000 | under 5,000 | Mortality benefit levels off around 7,000–8,000 (Paluch et al. 2022; Ding et al. 2025, both *Lancet Public Health*) |

These live in your `markers.yaml`; change them there if your doctor sets different targets.

## Health score (`athlete.yaml`, `app/healthscore.py`)

Each marker scores 100 at `top` (a fit, athletic person of the age and sex set in `athlete.yaml`), 50 at `avg`
and 0 at `poor`, in straight lines, capped at 0–100. Domains and their weights (cardio fitness 25, heart and
blood 20, strength and function 15, body composition 15, metabolic 10, sleep and recovery 10, daily habits 5) are
a judgement informed by the evidence that fitness and strength predict mortality most strongly. It is not a
validated model: use it to follow your own change over time.

## Known weak spots

- Readiness weights, the 0.5 SD noise band, the 1.2 load ratio and the 70 / 50 bands are hand-set; the only check
  is the built-in backtest against your own logged off-episodes.
- The pace multipliers (85% / 65%, 105% / 125%, 115%) and the live 10% amber band are heuristics.
- CGM bands (time in range, variability, mean) and the meal-rise colours have no firm source for non-diabetic
  adults.
- Recovery-HR bands, the 175 bpm max-HR floor, pulse-pressure 30 / 50 cut-offs and the 3 g per item sat-fat tint
  have no source.
- Fitness-test bands (grip, sit-to-stand, one-leg stand, VO2max) are flagged `verify` in the starter markers.
