"""First-run data-folder setup: the dashboard starts in setup mode when there's no data folder, refuses unsafe
choices, creates a new folder from the starter files, saves the choice and restarts on it. Uses temporary
folders and a temporary config file only. Standard library only."""
import http.client, json, os, pathlib, re, socket, subprocess, sys, tempfile, time, unittest, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests")); import signin   # noqa: E402
sys.path[:0] = [str(ROOT / "scripts")]
# Same environment as the other test files (unittest discover imports them all into one process, this one first),
# and never the real ~/.body-kaizen/config.json.
os.environ.setdefault("FT_DATA", str(ROOT / "demo"))
os.environ.setdefault("BK_CONFIG", str(pathlib.Path(tempfile.gettempdir()) / "bk-test-config.json"))
import bkenv   # noqa: E402


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


class Resolve(unittest.TestCase):
    def test_env_beats_config_beats_default(self):
        self.assertEqual(bkenv.resolve_data({"FT_DATA": "/tmp/a"}, {"data_dir": "/tmp/b"}), pathlib.Path("/tmp/a").resolve())
        self.assertEqual(bkenv.resolve_data({}, {"data_dir": "/tmp/b"}), pathlib.Path("/tmp/b").resolve())
        self.assertEqual(bkenv.resolve_data({}, {}), pathlib.Path(bkenv.DEFAULT_DATA).expanduser().resolve())

    def test_init_folder_has_no_demo_person_or_dated_data(self):
        with tempfile.TemporaryDirectory() as t:
            out = bkenv.init_data_folder(pathlib.Path(t) / "mine")
            self.assertTrue((out / "targets.yaml").exists())
            for d in bkenv.DATA_DIRS: self.assertEqual(list((out / d).iterdir()), [])
            self.assertNotIn("profile:", (out / "settings.yaml").read_text(encoding="utf-8"))


class SetupMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(dir=pathlib.Path.home(), prefix='.bk-test-')
        t = pathlib.Path(cls.tmp.name)
        (t / "empty").mkdir()
        cls.cfg = t / "config.json"
        cls.port = free_port()
        env = {**os.environ, "FT_DATA": str(t / "empty"), "BK_CONFIG": str(cls.cfg), "FT_NO_SYNC": "1",
               "FT_NO_SELF_RESTART": "1", "FT_PORT": str(cls.port)}
        cls.srv = subprocess.Popen([sys.executable, str(ROOT / "app" / "server.py")], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.cookie = signin.sign_in(cls.port, cls.cfg)
        cls.page = cls.get("/", wait=True).decode()
        cls.token = re.search(r'name="bk-token" content="([^"]+)"', cls.page).group(1)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate(); cls.srv.wait(timeout=10); cls.tmp.cleanup()

    @classmethod
    def get(cls, path, wait=False):
        for _ in range(75 if wait else 1):
            try:
                with urllib.request.urlopen(cls.base + path, timeout=3) as r: return r.read()
            except OSError:
                if not wait: raise
                time.sleep(0.2)

    def post(self, path, body, token=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("POST", path, body=json.dumps(body).encode(), headers={
            "Host": f"127.0.0.1:{self.port}", "Cookie": self.cookie, "Origin": self.base, "Sec-Fetch-Site": "same-origin",
            "Content-Type": "application/json", "X-BK-Token": token or self.token})
        r = c.getresponse(); out = (r.status, json.loads(r.read() or b"{}")); c.close(); return out

    def test_1_setup_page_and_info(self):
        self.assertIn("Welcome to Body Kaizen", self.page)
        info = json.loads(self.get("/api/datasetup"))
        self.assertTrue(info["needs_setup"])
        with self.assertRaises(urllib.error.HTTPError) as e: self.get("/api/summary")
        self.assertEqual(e.exception.code, 503)

    def test_2_refuses_unsafe_choices(self):
        for path in (str(ROOT), str(ROOT / "demo"), "relative/path", "", "/etc", "~/../.."):
            with self.subTest(path=path):
                self.assertFalse(self.post("/api/datasetup/check", {"path": path})[1]["ok"])
        busy = pathlib.Path(self.tmp.name) / "busy"; busy.mkdir(); (busy / "notes.txt").write_text("x")
        res = self.post("/api/datasetup/check", {"path": str(busy)})[1]
        self.assertFalse(res["ok"]); self.assertTrue(res["suggest"].endswith("Body Kaizen data"))

    def test_3_create_needs_the_token(self):
        self.assertEqual(self.post("/api/datasetup/create", {"path": "/tmp/x"}, token="wrong")[0], 403)

    def test_4_create_saves_and_restarts_on_the_new_folder(self):
        new = pathlib.Path(self.tmp.name) / "my data"
        status, res = self.post("/api/datasetup/create", {"path": str(new), "git": False})
        self.assertEqual(status, 200, res); self.assertTrue(res["restarting"])
        self.assertEqual(json.loads(self.cfg.read_text(encoding="utf-8"))["data_dir"], str(new.resolve()))
        self.assertTrue((new / "targets.yaml").exists())
        time.sleep(1.0)
        for _ in range(75):
            try:
                if not json.loads(self.get("/api/datasetup"))["needs_setup"]: break
            except OSError: pass
            time.sleep(0.2)
        json.loads(self.get("/api/summary"))   # the full dashboard now answers
        self.assertIn('id="setup"', self.get("/").decode())   # index.html with its profile dialog


if __name__ == "__main__":
    unittest.main()
