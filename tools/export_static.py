"""Export the dashboard as a static site, for the live demo on GitHub Pages.

    python tools/export_static.py OUT [--end YYYY-MM-DD] [--days 90]

It builds fresh demo data ending on --end (default: today, so the demo always looks current), then asks the real
server code for every read-only answer the pages need and saves each as a JSON file under OUT/data/. The pages are
copied as they are; a small shim (static-demo.js, added to each page) sends their requests to those files and turns
anything that would write into a "this is a demo" reply. Nothing in app.js knows about any of this, so the demo is
always the current code.

Which answers to save comes from server.ROUTES: every route is saved once with no parameters if it answers that
way, and PARAMS below adds the per-day, per-workout and per-week variants the pages ask for. tests/test_static.py
crawls the exported site in a browser and fails on any request without a file, so a new route or parameter that
isn't covered here breaks the build instead of the demo.

Only demo data (from demo-template/ via tools/make_demo.py) ever goes into the export.
"""
import argparse, datetime as dt, json, os, pathlib, re, shutil, subprocess, sys, tempfile

CODE = pathlib.Path(__file__).resolve().parent.parent
STATIC = CODE / "app" / "static"
PAGES = ["index.html", "doctor.html", "thresholds.html", "connections.html"]   # setup.html isn't needed: the demo has data
SKIP = {"/api/session", "/api/datasetup"}   # answered by the shim


def key(path, query=None):
    """The file a request is saved under. static-demo.js builds the same name: keep the two in step."""
    name = path[len("/api/"):].strip("/").replace("/", "_")
    q = sorted((k, str(v)) for k, v in (query or {}).items() if v not in (None, ""))
    if q: name += "__" + "_".join(f"{k}-{v}" for k, v in q)
    return re.sub(r"[^A-Za-z0-9_.-]", "-", name) + ".json"


def params(server, dates, data):
    """The parameter sets the pages ask for, beyond the no-parameter call."""
    import workouts
    sessions = [(w["date"], w.get("idx", 0)) for w in (workouts.index() or []) if w.get("date")]
    mondays = sorted({(dt.date.fromisoformat(d) - dt.timedelta(days=dt.date.fromisoformat(d).weekday())).isoformat() for d in dates})
    P = {r: [{"date": d} for d in dates] for r in ("/api/day", "/api/pace", "/api/glance", "/api/daytimeline", "/api/insights",
                                                    "/api/energy", "/api/glucose")}
    P["/api/workout"] = [{"date": d, "i": i} for d, i in sessions]
    P["/api/muscles"] = [{"days": n} for n in (7, 14, 28)] + [{"date": d, "i": i} for d, i in sessions]
    P["/api/week"] = [{"start": m} for m in mondays]
    P["/api/glucose_overview"] = [{"days": 14}]
    return P


def call(server, path, query):
    q = {k: [str(v)] for k, v in (query or {}).items()}
    return server.ROUTES[path](q)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out")
    ap.add_argument("--end", default=dt.date.today().isoformat())
    ap.add_argument("--days", type=int, default=90)
    A = ap.parse_args()
    out = pathlib.Path(A.out).resolve()
    if out.exists(): shutil.rmtree(out)
    (out / "data").mkdir(parents=True)

    demo = pathlib.Path(tempfile.mkdtemp(prefix="bk-demo-")) / "demo"
    subprocess.run([sys.executable, str(CODE / "tools" / "make_demo.py"), str(demo), "--end", A.end, "--days", str(A.days)], check=True)
    os.environ.update({"FT_DATA": str(demo), "FT_NO_SYNC": "1"})
    sys.path[:0] = [str(CODE / "scripts"), str(CODE / "app")]
    import server, data   # noqa: E402  (after FT_DATA: the data folder is read at import)
    sys.path.insert(0, str(CODE / "tools")); import static_seo   # noqa: E402

    dates = [d["date"] for d in data.summary()]
    P = params(server, dates, data)
    n, size, missing = 0, 0, []
    for path in server.ROUTES:
        if path in SKIP: continue
        for q in [{}] + P.get(path, []):
            try: body = call(server, path, q)
            except Exception as e:
                if q: missing.append(f"{path} {q}: {type(e).__name__}: {e}")
                continue
            if body is None and not q: continue
            f = out / "data" / key(path, q)
            txt = json.dumps(data._jsonable(body) if hasattr(data, "_jsonable") else body, default=str, separators=(",", ":"))
            f.write_text(txt, encoding="utf-8"); n += 1; size += len(txt)
    # the pages, with absolute links made relative (the site lives under /<repo>/) and the shim loaded first
    shutil.copytree(STATIC / "vendor", out / "vendor")
    for f in ("app.js", "style.css"):
        txt = (STATIC / f).read_text(encoding="utf-8")
        (out / f).write_text(re.sub(r"""(href=["'])/(?=[a-z])""", r"\1", txt), encoding="utf-8")
    shutil.copy(CODE / "tools" / "static-demo.js", out / "static-demo.js")
    for p in PAGES:
        html = (STATIC / p).read_text(encoding="utf-8")
        html = re.sub(r"""(href=["'])/(?=[a-z])""", r"\1", html)
        html = re.sub(r'(<meta charset="utf-8">)', r'\1\n<script src="static-demo.js"></script>', html, count=1, flags=re.I) \
            if re.search(r'<meta charset="utf-8">', html, re.I) else html.replace("<head>", '<head>\n<script src="static-demo.js"></script>', 1)
        html = static_seo.apply(html, p, static_seo.base_url())
        (out / p).write_text(html, encoding="utf-8")
    (out / ".nojekyll").write_text("")
    static_seo.extras(out, static_seo.base_url(), A.end)
    (out / "data" / "_built.json").write_text(json.dumps({"built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
                                                          "end": A.end, "files": n}))
    print(f"exported {n} answers ({size / 1e6:.1f} MB) for {len(dates)} days to {out}")
    for m in missing: print("  could not export:", m)
    shutil.rmtree(demo.parent, ignore_errors=True)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
