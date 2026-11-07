"""The live demo stays in step with the code: export the static site, serve it under a sub-path as GitHub Pages does,
click through every tab and control in a real browser, and fail on any request without a file, any page error, or a
tab that renders nothing.

Needs Playwright with Chromium (pip install playwright && python -m playwright install chromium); skipped without
it. Set BK_STATIC_SITE to an already exported folder to skip the export (CI exports once and reuses it).
"""
import functools, http.server, os, pathlib, shutil, subprocess, sys, tempfile, threading, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


def _serve(site):
    """Serve `site` at http://127.0.0.1:PORT/body-kaizen/ (a sub-path, like a project's GitHub Pages)."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="bk-pages-"))
    (root / "body-kaizen").symlink_to(site, target_is_directory=True)
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, root, f"http://127.0.0.1:{srv.server_address[1]}/body-kaizen/"


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class StaticDemo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = None
        site = os.environ.get("BK_STATIC_SITE")
        if not site:
            cls.tmp = tempfile.mkdtemp(prefix="bk-site-")
            site = os.path.join(cls.tmp, "site")
            subprocess.run([sys.executable, str(ROOT / "tools" / "export_static.py"), site], check=True, capture_output=True)
        cls.site = pathlib.Path(site).resolve()
        cls.srv, cls.root, cls.url = _serve(cls.site)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close(); shutil.rmtree(cls.root, ignore_errors=True)
        if cls.tmp: shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_every_tab_and_control_has_its_data(self):
        bad = []
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1280, "height": 900})
            pg.on("response", lambda r: r.status >= 400 and bad.append(f"{r.status} {r.url}"))
            pg.on("pageerror", lambda e: bad.append(f"page error: {e}"))
            pg.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text and bad.append(f"console: {m.text}"))
            pg.goto(self.url); pg.wait_for_selector("#day h1", timeout=15000)
            self.assertTrue(pg.locator("#bk-demo-banner").is_visible())
            tabs = pg.eval_on_selector_all("nav button[data-tab]", "bs => bs.map(b => b.dataset.tab)")
            self.assertGreater(len(tabs), 8)
            for t in tabs:
                pg.click(f'nav button[data-tab="{t}"]'); pg.wait_for_timeout(900)
                sec = pg.locator(f"#tab-{t}")
                with self.subTest(tab=t):
                    self.assertTrue(sec.is_visible())
                    self.assertGreater(len(sec.inner_text().strip()), 40, f"the {t} tab rendered almost nothing")
                    self.assertEqual(sec.locator(".empty", has_text="Couldn").count(), 0, f"the {t} tab couldn't load its data")
            # the controls that ask for other data
            pg.click('nav button[data-tab="day"]'); pg.wait_for_timeout(500)
            for _ in range(3): pg.click("#prev"); pg.wait_for_timeout(500)
            pg.click("#latest"); pg.wait_for_timeout(500)
            pg.click('nav button[data-tab="training"]'); pg.wait_for_timeout(800)
            for m in ("14", "28", "session", "7"): pg.click(f'#mrange button[data-m="{m}"]'); pg.wait_for_timeout(400)
            chips = pg.locator("#wopick button[data-k]")
            self.assertGreater(chips.count(), 2, "no workouts to click")
            for i in range(min(4, chips.count())): chips.nth(i).click(); pg.wait_for_timeout(400)
            pg.click('nav button[data-tab="week"]'); pg.wait_for_timeout(500)
            for _ in range(2): pg.click("#wprev"); pg.wait_for_timeout(400)
            pg.click('nav button[data-tab="trends"]'); pg.wait_for_timeout(500)
            for d in ("14", "60", "0"): pg.click(f'#range button[data-d="{d}"]'); pg.wait_for_timeout(400)
            # writes are refused politely, not broken
            r = pg.evaluate("fetch('api/garmin/sync', {method:'POST'}).then(r => r.json())")
            self.assertTrue(r.get("demo"))
            for page in ("thresholds.html", "doctor.html", "connections.html"):
                with self.subTest(page=page):
                    pg.goto(self.url + page); pg.wait_for_timeout(1500)
                    self.assertGreater(len(pg.inner_text("body").strip()), 80)
            b.close()
        bad = [x for x in bad if "/api/garmin/sync" not in x]   # the refused write above
        self.assertEqual(bad, [], "\n".join(bad))

    def test_every_day_and_workout_is_exported(self):
        """The browser only clicks a few of each; this checks the rest have their files too."""
        import json
        sys.path.insert(0, str(ROOT / "tools")); from export_static import key
        D = self.site / "data"
        days = [d["date"] for d in json.loads((D / "summary.json").read_text(encoding="utf-8"))]
        missing = [key(r, {"date": d}) for d in days for r in ("/api/day", "/api/pace", "/api/glance", "/api/daytimeline", "/api/insights")
                   if not (D / key(r, {"date": d})).exists()]
        for w in json.loads((D / "workouts.json").read_text(encoding="utf-8")):
            for r in ("/api/workout", "/api/muscles"):
                k = key(r, {"date": w["date"], "i": w.get("idx", 0)})
                if not (D / k).exists(): missing.append(k)
        self.assertEqual(missing, [])

    def test_only_demo_data(self):
        """The export is built from the demo template: Sam, never a real data folder."""
        prof = (self.site / "data" / "profile.json").read_text(encoding="utf-8")
        self.assertIn("demo", prof.lower())


if __name__ == "__main__":
    unittest.main()
