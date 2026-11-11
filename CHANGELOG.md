# Changelog

What changed in each release. Earlier releases are described on the
[releases page](https://github.com/craigbennett1981/body-kaizen/releases).

## Unreleased

### Body tab
- **Your real maintenance:** what you actually burn, from the last 28 days of eating against what your fasted weight
  trend did (7,700 kcal per kg), with a 90% range and Garmin's burn beside it, so you can see how far Garmin's figure
  is out. Your calorie targets moved so a typical week of yours lands on maintenance, or on 0.25 or 0.5 kg a week
  towards your weight target (never below your BMR), and your trend weight at the next InBody scan for each. A chart
  shows the estimate week by week. Set `adaptive:` in targets.yaml for your own goal rate and scan date. Nothing
  changes on its own: ask your assistant to switch targets.

### Training tab
- **One period for the top of the tab:** the 7 days, 30 days, 60 days and All buttons beside the title now set the
  Activity calendar and Intensity minutes too, not just Calories burnt. Intensity minutes shows days for 7 days,
  weeks for 30 and 60, and months for All. Its own Weeks and Months buttons are gone.
- **Activity and Intensity minutes side by side** on a wide screen (stacked on a phone), with bigger calendar squares
  for short periods. The Intensity chart shrinks to the calendar's height, and its note is down to this week and the
  trend (the rest is on hover).
- **Muscles worked opens on this workout**, the one picked above it, instead of the last 7 days.

### Training tab
- **Intensity minutes per week or month:** Garmin's count (moderate plus vigorous counted twice) against your Garmin
  weekly goal (150 when the watch reports none), pro rata for months. A 4-week average line, this week's progress and
  what's left to do, how the last 4 full weeks compare with the 4 before, and how many of the last 12 weeks met the
  goal. Weeks with too few days of watch data are faded and left out of the trend.

### Setting up
- **Choose how your data is kept:** a second setup step offers plain files (simplest, no history or backup), plain
  files with git history (recommended: every change a version, nothing leaves the computer) or history plus a private
  GitHub backup, whose steps go on the to-do list. Without git installed, plain files are offered and git is linked.
  [docs/data-folder.md](docs/data-folder.md#how-your-data-is-kept) explains each one and the GitHub steps.

### Dashboard
- **A logo of its own:** three rising steps with a dot on the top one, in the dashboard's blue. It is the browser-tab
  icon (SVG, plus `favicon.ico` and an Apple touch icon), the demo's icon and the installer's app icon. The icon files
  are the only thing served before signing in.

## 0.7.0 (7 November 2026)

### Dashboard
- **Dates on the Week tab's Last 12 weeks grid:** each week's start date above its column (just the month starts on
  a phone).

### Setting up
- **Metric or imperial:** chosen at first-run setup (metric by default) and changeable from the profile icon.
  Weights, distances, paces and portions follow it everywhere; files stay metric and macros stay in grams.
- **Set up your AI assistant** from the dashboard: after first-run setup (and from the profile icon), a prompt to copy
  into Claude Code that points it at your data folder and the guide, writes your `CLAUDE.md` and asks about you.

### Install in one line
- **macOS, Linux and Windows installers** (`install/install.sh`, `install/install.ps1`): no Python needed (uv brings
  its own), the Garmin and LibreLinkUp syncs included, the dashboard started at login, and a **Body Kaizen** launcher
  in Applications, the applications menu or the Start menu that opens it signed in. Run again to update; uninstalling
  leaves your data alone.

### Security
- **Only you can open the dashboard.** Every request needs a cookie holding a secret only your account can read
  (`~/.body-kaizen/session.key`). Starting it from a terminal or `scripts/setup_mac.sh` opens your browser signed
  in; `body-kaizen open` (or `python -m body_kaizen open`) signs in another browser. Once per browser: it survives
  restarts. Other accounts on the computer get a "not signed in" page and no data.
- **Harder to tie up:** bad request lengths refused at once, idle connections dropped after 30 seconds, day ranges
  capped, errors while saving logged rather than dropping the connection, and the Garmin check no longer starts a
  process on every status request.
- **Private files:** `~/.body-kaizen` and `~/.garminconnect`, and every login file in them, are created private to
  your account. New data folders are private to you too (0700), get a `.gitignore` for sync bookkeeping, and no
  longer inherit the demo person's experiments. The data-folder check ignores case on
  macOS and Windows.
- **Build:** GitHub Actions pinned to commits, and the release tag passed to scripts through the environment.

## 0.6.0 (7 November 2026)

### Experiments tab
- **Test one change on yourself:** a rule each evening (asleep by 22:30) judged on that night's sleep, or a daily
  habit for a few weeks (sodium under 2 g) judged on morning blood pressure, weight or sleep. Suggested from your own
  data, built from a fixed list of variables (anything else is flagged), with habits no device records and
  supplements logged like food.
- **While it runs:** a checklist for today, reminder toasts for readings and the rule, days to go, how many more you
  can miss and still get a verdict, early results shown as a lean, and a halfway note.
- **When it ends:** a verdict with a 90% range per outcome, a warning when a reading was already trending that way,
  what to do next, and a button that copies the result for your assistant to write up.
- **Try a rule** and **Look for a relationship** question your history before you commit to a test; copying one
  gives your assistant the entry and the steps to start it.

### Fewer tabs: 13 down to 9
- **Sleep & recovery** (was Sleep and Recovery), **Week** (now with the trends chart and all the advice),
  **History** (was Timeline and Wellbeing). Glucose by food and by meal moved to **Food**; the health score shows
  once, on Longevity. Old links to the merged tabs still work.

### Clearer about what it is
- **Wellness framing:** the README, disclaimer and live demo say plainly who it isn't for (under 18s, pregnancy, eating
  disorders, adjusting insulin or medication), with careful wording throughout and a privacy note.
- **A short notice above the highlights** in the README, pointing to the full disclaimer.
- **Integrations:** if there's one you'd use, ask for it as a GitHub issue.

## 0.5.0 (7 November 2026)

### Try it without installing
- **Live demo at [demo.bodykaizen.app](https://demo.bodykaizen.app/):** the real dashboard on 90 days of made-up
  data for Sam, a fictional person. Every tab works. It's rebuilt from the code on every merge and daily, and a
  browser test clicks through every tab before each deploy, so it never drifts from what you'd install.

### New tabs
- **Food:** every food you've logged with its macros per 100 g, protein per 100 kcal, how often and how much, all
  time or the last 7 days, searchable and sortable. Above it: where this week's saturated fat, protein, calories and
  fibre came from, your staples, plants this week against 30, swaps for your biggest saturated-fat sources from foods
  you already eat, what each meal supplies on an average day, weekdays against weekends, and (with a CGM) your foods
  ranked by glucose rise.
- **Sleep:** last night's stages, sleep debt over 7 nights, and when to be in bed tonight, worked back from your
  weekday alarm. Your sleep stages against typical adult ranges and what changes them, when you wake in the night,
  how regular your bedtimes are, your own nights compared by the day before (late session, late meal, caffeine after
  2 pm, busy or stressful days), and advice from what it finds. The Recovery tab gets a one-line summary that links
  to it.

### On the dashboard
- **Energy balance:** the Calories box shows your deficit now and the one you're heading for today, from Garmin's
  burn. The Body tab charts 30 days of burnt minus eaten and the weight change it predicts against your actual trend.
- **Body composition:** a small chart for every measure your scale gives, with InBody scans alongside.
- Tabs in alphabetical order after Day. Axis names on the Training and blood-pressure charts no longer collide with
  the legend, and the Training chart's dates are no longer clipped.

### Fixes
- "Today" and the timeline's "now" use the timezone in your profile. They had UTC+8 written in, so anyone outside
  Singapore saw them hours out.
- **Windows:** UTF-8 everywhere, a restart that works, folder-picker fixes, and CI on Windows and macOS.

### Security
- Everything the pages show is escaped; a strict Content-Security-Policy with a per-page nonce; no framing by other
  sites; request parameters are checked before they reach the data folder.

### Docs
- A shorter README with a clickable demo preview and three feature clips; every page explained in
  [docs/features.md](https://github.com/craigbennett1981/body-kaizen/blob/main/docs/features.md), kit advice in [docs/kit.md](https://github.com/craigbennett1981/body-kaizen/blob/main/docs/kit.md), and the disclaimer in
  [DISCLAIMER.md](https://github.com/craigbennett1981/body-kaizen/blob/main/DISCLAIMER.md).
- `tools/readme_media.py` remakes every GIF and screenshot from the demo, and `tools/export_static.py` builds the
  live demo; tests check the docs describe every tab and use every image.
