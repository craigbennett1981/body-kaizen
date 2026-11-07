# Changelog

What changed in each release. Earlier releases are described on the
[releases page](https://github.com/craigbennett1981/body-kaizen/releases).

## Unreleased

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
