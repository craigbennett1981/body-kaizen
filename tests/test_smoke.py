"""Smoke tests against the demo data folder: recompute every day, start the dashboard, and check every API
route answers. Runs on a temporary copy so the demo folder is never modified. Standard library only."""
import json, os, pathlib, re, shutil, socket, subprocess, sys, tempfile, time, unittest, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


class Smoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = pathlib.Path(cls.tmp.name) / "data"
        shutil.copytree(DEMO, cls.data)
        cls.env = {**os.environ, "FT_DATA": str(cls.data), "FT_NO_SYNC": "1", "FT_NO_SELF_RESTART": "1",
                   "FT_PORT": str(free_port())}
        cls.days = sorted(p.stem for p in (cls.data / "days").rglob("*.yaml"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_compute_all_days(self):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "compute.py")], env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.days, "demo folder has no day files")

    def test_api_routes(self):
        # The server's output goes to a file, not a pipe: nobody reads the pipe, and once a traceback fills it
        # (4 KB on Windows) the server blocks on every later request.
        log = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
        srv = subprocess.Popen([sys.executable, str(ROOT / "app" / "server.py")], env=self.env, stdout=log, stderr=subprocess.STDOUT)
        base = f"http://127.0.0.1:{self.env['FT_PORT']}"
        try:
            for _ in range(50):
                try: urllib.request.urlopen(base + "/api/summary", timeout=1); break
                except OSError: time.sleep(0.2)
            day = self.days[-1]
            routes = ["/", "/api/summary", "/api/training", "/api/body", "/api/reference", f"/api/day?date={day}",
                      f"/api/pace?date={day}", f"/api/glance?date={day}", f"/api/daytimeline?date={day}",
                      f"/api/insights?date={day}", "/api/week", "/api/plan", "/api/longevity", "/api/healthscore",
                      "/api/advice", "/api/wellbeing", "/api/timeline", "/api/workouts", "/api/muscles?days=7", "/api/todo", "/api/alerts",
                      "/api/readiness", "/api/energy", f"/api/energy?date={day}", "/api/foods"]
            for path in routes:
                with self.subTest(path=path):
                    try:
                        with urllib.request.urlopen(base + path, timeout=20) as r:
                            self.assertEqual(r.status, 200)
                            body = r.read()
                            if path.startswith("/api/"): json.loads(body)
                    except urllib.error.HTTPError as e:
                        log.flush(); log.seek(0)
                        self.fail(f"{path}: HTTP {e.code}. Server log:\n{log.read()[-3000:]}")
        finally:
            srv.terminate(); srv.wait(timeout=10); log.close()

    def test_no_platform_specific_strftime(self):
        """strftime's %-d, %-I and friends (no leading zero) exist on macOS and Linux only; Windows raises."""
        bad = [f"{p.relative_to(ROOT)}:{i}" for d in ("app", "scripts", "body_kaizen") for p in (ROOT / d).rglob("*.py")
               for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if re.search(r"%-[a-zA-Z]", line)]
        self.assertEqual(bad, [], "use f'{d.day} {d:%b}' instead")


if __name__ == "__main__":
    unittest.main()
