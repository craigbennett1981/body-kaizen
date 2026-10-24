# Contributing

Thanks for helping. Body Kaizen is a maintained project and contributions are welcome: bug reports, fixes, new
foods, docs, views and integrations. It is small and deliberately simple, so a few ground rules keep it that way.

## How the project is run

- **One maintainer, best effort.** Issues and pull requests are usually looked at within a week or two. If
  something has gone quiet for longer, a polite nudge is fine.
- **Talk before you build anything big.** For a new tab, a format change or a new integration, open an issue
  first so we can agree the approach. Small fixes can go straight to a pull request.
- **Good first issues** are labelled `good first issue`.
- **Questions and show-and-tell** go in Discussions; issues are for bugs and concrete proposals.
- Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).
- By contributing you agree that your contribution is licensed under the project's
  [Apache License 2.0](LICENSE), as section 5 of that licence sets out.

## What fits

Welcome:

- Fixes, tests, docs, accessibility and performance improvements.
- New foods for `foods/starter.yaml` (generic foods, not one brand's product in one country).
- New views or metrics, **backed by published evidence** for anything that scores health or sets a target.
- New integrations as optional scripts that write into the data folder, off unless the user sets them up.
- Better instructions for AI assistants in `AI-GUIDE.md`.

Out of scope:

- Accounts, a hosted service, or anything that sends data off the user's computer.
- Input forms that replace the AI-assistant workflow (a small helper is fine; a second way of doing everything isn't).
- Diagnosis or treatment advice.

## Privacy first

- **Never put real health data in an issue, pull request, screenshot, test or commit message.** That includes
  your own. Reproduce problems with the `demo/` data folder, or a few made-up day files.
- Code must never send data anywhere except the services a user has explicitly set up (Garmin, LibreLinkUp).
  No analytics, no telemetry, no remote fonts or scripts: ECharts and the font are bundled in `app/static/vendor/`.
- The server binds to `127.0.0.1` and checks the `Host` header. Keep it that way.

## Keep it simple

- **Python standard library** for the server and the tab modules. The only runtime dependency the core needs
  is PyYAML; the integrations bring their own. Python 3.10 or newer.
- **No build step** for the front end: plain JavaScript in `app/static/app.js`, plain CSS.
- **Data is plain YAML** in the format described in [SCHEMA.md](SCHEMA.md). If you change the format, update
  SCHEMA.md and [AI-GUIDE.md](AI-GUIDE.md), and keep old files readable.
- **Code never hard-codes a person, place or timezone.** Those belong in the data folder's `settings.yaml`,
  `athlete.yaml` and `targets.yaml`.

## Getting set up

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
FT_DATA=demo FT_PORT=8799 .venv/bin/python app/server.py
```

The server reloads app modules when they change on disk, so you can edit and refresh. To rebuild the demo data:
`python tools/make_demo.py`.

## Pull requests

- One change per pull request, with a short description of what it does and why.
- Run the tests: `python -m unittest discover -s tests`. Add a test for a bug fix or new logic where you can.
- Run `FT_DATA=demo python scripts/compute.py` and load every tab before you open it; check the browser console
  for errors.
- For a visual change, include a before-and-after screenshot taken **with demo data**.
- New foods: macros per 100 g (or per unit), and where the figures came from (a product label, or a named
  nutrition database).
- CI runs the tests on Python 3.10 to 3.13; it needs to pass before merging.

## Reporting bugs

Open an issue using the bug template: what you did, what you expected and what happened, plus the server log
and any browser console errors. Remove anything personal from logs first.

For a security or privacy problem, see [SECURITY.md](SECURITY.md) instead of opening a public issue.
