## What and why

<!-- One change per pull request. What does it do, and why? Link the issue if there is one. -->

## Checklist

- [ ] No real health data anywhere: code, tests, screenshots, commit messages
- [ ] `python -m unittest discover -s tests` passes
- [ ] Ran `FT_DATA=demo python scripts/compute.py` and loaded every tab with no console errors, with the server on
      demo data started as `FT_NO_SYNC=1 FT_DATA=demo FT_PORT=8799 python app/server.py`
- [ ] Screenshots (demo data) for any visual change
- [ ] SCHEMA.md / AI-GUIDE.md updated if the data format or the logging rules changed
- [ ] New foods: per-100 g figures with their source
