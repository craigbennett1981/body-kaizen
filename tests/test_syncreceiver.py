"""The iPhone sync receiver, driven by a stand-in phone (tests/applephone.py) over real TLS on 127.0.0.1.

Pair, upload, resend, delete, a wrong token, a public address, a redirect, an oversize body, and an upload racing an
erase. Everything runs in temporary folders with demo samples; no real data and no real ~/.body-kaizen."""
import datetime as dt, gzip, hashlib, http.server, json, os, pathlib, ssl, stat, sys, tempfile, threading, unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("FT_DATA", str(ROOT / "demo"))
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "app"), str(ROOT / "tests")]
import bkenv  # noqa: E402
from applephone import Phone, Samples, demo_day, WATCH  # noqa: E402

try:
    import syncreceiver as SR, apple_cache as C   # noqa: E402
    HAVE = SR.installed()
except ImportError: HAVE = False

DAY = "2026-11-17"
POSIX = os.name == "posix"


@unittest.skipUnless(HAVE, "needs the iphone extra: pip install 'body-kaizen[iphone]'")
class Receiver(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); t = pathlib.Path(self.tmp.name)
        self.data = bkenv.init_data_folder(t / "data", ROOT / "demo")
        self.rx = SR.Receiver(folder=t / "sync", root=self.data, port=0, host="127.0.0.1", translate_after=3600, quiet=True)
        self.addCleanup(self.rx.stop)

    def tearDown(self): self.tmp.cleanup()

    def phone(self, name="Demo iPhone"):
        r = self.rx.start_pairing(); p = r["payload"]
        ph = Phone("127.0.0.1", self.rx.port, p["fp"], name)
        return ph, p, r

    def paired(self, name="Demo iPhone"):
        ph, p, _ = self.phone(name)
        self.assertEqual(ph.pair(p["code"])[0], 200)
        return ph

    # ----- pairing -----
    def test_off_until_paired(self):
        self.assertIsNone(self.rx.server); self.rx.ensure(); self.assertIsNone(self.rx.server)
        ph, p, r = self.phone()
        self.assertTrue(self.rx.server)                                   # listening while a code is live
        self.assertEqual(set(p), {"v", "name", "port", "addrs", "fp", "code"})
        self.assertEqual(len(r["typed"]), 9)                               # XXXX-XXXX
        st, j = ph.pair(p["code"])
        self.assertEqual(st, 200); self.assertEqual(len(j["token"]), 43)  # 256 bits, URL-safe base64
        self.rx.remove(j["device_id"])
        self.assertIsNone(self.rx.server)                                 # the last phone removed: not listening

    def test_only_the_tokens_hash_is_kept(self):
        ph = self.paired()
        text = (self.rx.dir / "devices.json").read_text(encoding="utf-8")
        self.assertNotIn(ph.token, text)
        self.assertIn(hashlib.sha256(ph.token.encode()).hexdigest(), text)
        if POSIX:
            for f in ("devices.json", "key.pem", "cert.pem"): self.assertEqual(stat.S_IMODE((self.rx.dir / f).stat().st_mode), 0o600, f)
            self.assertEqual(stat.S_IMODE(self.rx.dir.stat().st_mode), 0o700)

    def test_code_is_single_use(self):
        ph, p, _ = self.phone()
        self.assertEqual(ph.pair(p["code"])[0], 200)
        self.assertEqual(Phone("127.0.0.1", self.rx.port, p["fp"]).pair(p["code"])[0], 403)

    def test_typed_code_works(self):
        ph, p, r = self.phone()
        self.assertEqual(ph.pair(r["typed"].lower())[0], 200)

    def test_wrong_codes_burn_it(self):
        ph, p, _ = self.phone()
        for _ in range(SR.CODE_TRIES): self.assertEqual(ph.pair("WRONG-CODE")[0], 403)
        self.assertEqual(ph.pair(p["code"])[0], 403)

    def test_code_expires(self):
        ph, p, _ = self.phone()
        self.rx.pairing["expires"] = 0
        self.assertEqual(ph.pair(p["code"])[0], 403)

    def test_device_names_lose_control_characters(self):
        self.paired("Demo\x1b[31m iPhone\n‮evil\x00")
        self.assertEqual(self.rx.devices()[0]["name"], "Demo [31m iPhone evil")

    def test_pinned_certificate(self):
        ph, p, _ = self.phone()
        with self.assertRaises(ssl.SSLError): Phone("127.0.0.1", self.rx.port, "0" * 64).pair(p["code"])

    # ----- uploads -----
    def test_upload_resend_and_translate(self):
        ph = self.paired()
        res = ph.upload_all(demo_day(DAY), {"trigger": "refresh", "locked": True, "battery": True, "sent": 9, "extra": "x"})
        self.assertTrue(all(st == 200 for _, st, _ in res), res)
        self.assertEqual(sum(j["stored"] for *_, j in res), len(demo_day(DAY)))
        again = ph.upload_all(demo_day(DAY))                              # a resent batch changes nothing
        self.assertEqual(sum(j["stored"] + j["updated"] for *_, j in again), 0)
        self.rx.flush(git=False)
        d = bkenv.yaml.safe_load((self.data / "days" / "2026" / f"{DAY}.yaml").read_text(encoding="utf-8"))
        self.assertEqual((d["steps"], d["steps_source"], d["recovery"]["source"], d["recovery"]["hrv_method"]), (17800, "apple", "apple", "sdnn"))
        self.assertEqual(d["exercise"][0]["type"], "run")
        self.assertEqual(d["weight"]["kg"], 78.4)
        self.assertTrue((self.data / "imports" / "apple" / "2026" / f"{DAY}.json").exists())
        st = self.rx.status()["devices"][0]
        self.assertEqual(st["last_report"]["trigger"], "refresh"); self.assertNotIn("extra", st["last_report"])
        self.assertEqual(self.rx.flush(git=False), [])                    # nothing new: nothing to do

    def test_ping(self):
        ph = self.paired()
        self.assertEqual(ph.ping(), (200, {"ok": True}))

    def test_wrong_token(self):
        ph = self.paired()
        good = ph.token
        ph.token = "x" * 43
        self.assertEqual(ph.upload("steps", [])[0], 401)
        ph.token = None
        self.assertEqual(ph.upload("steps", [])[0], 401)
        ph.token = good; ph.device_id = "d_someoneelse"
        self.assertEqual(ph.upload("steps", [])[0], 401)                  # token and device must match

    def test_unknown_type_is_refused_first(self):
        ph = self.paired()
        self.assertEqual(ph.upload("../../etc/passwd", [])[0], 400)
        self.assertEqual(ph.upload("medications", [{"uuid": "A"}])[0], 400)
        self.assertEqual(C.count(self.data), 0)

    def test_bad_samples_are_skipped_not_stored(self):
        ph = self.paired()
        s = Samples().add("steps", f"{DAY}T08:00", f"{DAY}T08:15", 500, "count")
        st, j = ph.upload("steps", [{k: v for k, v in s.items() if k != "type"}, {"uuid": "B", "value": "lots"}, {"no": "uuid"}])
        self.assertEqual((st, j["stored"], j["skipped"]), (200, 1, 2))

    def test_oversize_body(self):
        ph = self.paired()
        # refused on its stated length, before a byte of it is read
        self.assertEqual(ph.post("/v1/samples", None, raw=b"{}", headers={"Content-Length": str(SR.MAX_BODY + 1)})[0], 413)
        try: st = ph.post("/v1/samples", None, raw=os.urandom(SR.MAX_BODY + 1))[0]
        except (ConnectionError, ssl.SSLError, OSError): st = "dropped"   # the receiver hangs up while it's still sending
        self.assertIn(st, (413, "dropped"))
        bomb = gzip.compress(b"[" + b" " * (SR.MAX_JSON + 10) + b"]")     # small on the wire, huge unzipped
        self.assertLess(len(bomb), SR.MAX_BODY)
        self.assertEqual(ph.post("/v1/samples", None, raw=bomb)[0], 413)

    def test_json_only_and_no_reading_back(self):
        ph = self.paired()
        self.assertEqual(ph.post("/v1/ping", {"device_id": ph.device_id}, headers={"Content-Type": "text/plain"})[0], 415)
        c = ph._conn()
        try:
            for method, path in (("GET", "/"), ("GET", "/v1/samples"), ("HEAD", "/v1/ping"), ("OPTIONS", "/v1/pair")):
                c.request(method, path); r = c.getresponse(); r.read(); self.assertEqual(r.status, 405, path); c.close(); c = ph._conn()
            c.request("POST", "/api/summary", body=b"{}", headers={"Content-Type": "application/json"}); r = c.getresponse(); r.read()
            self.assertEqual(r.status, 404)
        finally: c.close()

    def test_rate_and_daily_limits(self):
        ph = self.paired()
        with mock.patch.object(SR, "RATE", 3):
            self.assertEqual([ph.ping()[0] for _ in range(4)], [200, 200, 200, 429])
        self.rx._rate.clear()
        with mock.patch.object(SR, "DAILY_BYTES", 10):
            self.assertEqual(ph.ping()[0], 429)

    # ----- deletions -----
    def test_delete_only_your_own(self):
        a = self.paired("Phone A")
        w = [s for s in demo_day(DAY) if s["type"] == "workout"]
        a.upload_all(w + [s for s in demo_day(DAY) if s["type"] == "heart_rate"])
        self.rx.flush(git=False)
        b = self.paired("Phone B")
        self.assertEqual(b.delete([w[0]["uuid"]]), (200, {"ok": True, "deleted": 0}))
        self.assertEqual(a.delete([w[0]["uuid"]]), (200, {"ok": True, "deleted": 1}))
        self.rx.flush(git=False)
        d = bkenv.yaml.safe_load((self.data / "days" / "2026" / f"{DAY}.yaml").read_text(encoding="utf-8"))
        self.assertFalse(d.get("exercise"))
        self.assertNotIn("workouts", json.loads((self.data / "imports" / "apple" / "2026" / f"{DAY}.json").read_text(encoding="utf-8")))

    def test_upload_racing_an_erase_is_refused(self):
        ph = self.paired()
        dev = self.rx.authenticate({"Authorization": f"Bearer {ph.token}"}, ph.device_id)   # the upload has begun...
        self.rx.erase(ph.device_id)                                                         # ...an erase finishes...
        s = Samples().add("steps", f"{DAY}T08:00", f"{DAY}T08:15", 500, "count")
        self.assertEqual(self.rx.store(dev, {"type": "steps", "samples": [s]})[0], 409)       # ...and it's refused
        self.assertEqual(C.count(self.data), 0)
        self.assertEqual(ph.upload("steps", [s])[0], 200)                                   # a fresh upload is fine

    def test_removed_phone_cannot_send(self):
        ph = self.paired(); keep = self.paired("Other")
        ph.upload_all(demo_day(DAY)[:5])
        self.assertTrue(self.rx.remove(ph.device_id))
        self.assertEqual(C.count(self.data, ph.device_id), 0)              # what it sent leaves the cache
        self.assertEqual(ph.ping()[0], 401)
        self.assertEqual(keep.ping()[0], 200)

    # ----- the network -----
    def test_public_addresses_are_dropped_before_tls(self):
        ph, p, _ = self.phone()
        self.rx.is_allowed = lambda host: False
        with self.assertRaises((ConnectionError, ssl.SSLError, OSError)): ph.pair(p["code"])
        self.assertIsNotNone(self.rx.pairing)                              # nothing reached the pairing code

    def test_private_ranges(self):
        for ok in ("192.168.1.20", "10.0.0.5", "172.16.4.1", "169.254.3.3", "fe80::1%en0", "fd12:3456::1", "::ffff:192.168.1.9", "127.0.0.1", "::1"):
            self.assertTrue(SR.allowed(ok), ok)
        for no in ("8.8.8.8", "172.32.0.1", "100.64.0.1", "2001:4860::8888", "::ffff:8.8.8.8", "010.010.010.010", "", "nonsense"):
            self.assertFalse(SR.allowed(no), no)

    def test_redirects_are_not_followed(self):
        """The phone never follows a redirect with its token: a 307 is an answer, and the place it points to hears
        nothing."""
        heard = []
        class Elsewhere(http.server.BaseHTTPRequestHandler):
            def do_POST(self): heard.append(self.headers.get("Authorization")); self.send_response(200); self.end_headers()
            def log_message(self, *a): pass
        class Redirect(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                self.send_response(307); self.send_header("Location", f"http://127.0.0.1:{other.server_address[1]}/v1/samples")
                self.send_header("Content-Length", "0"); self.end_headers()
            def log_message(self, *a): pass
        other = http.server.HTTPServer(("127.0.0.1", 0), Elsewhere)
        bad = http.server.HTTPServer(("127.0.0.1", 0), Redirect)
        SR.make_cert(pathlib.Path(self.tmp.name)) if not (pathlib.Path(self.tmp.name) / "cert.pem").exists() else None
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(pathlib.Path(self.tmp.name) / "cert.pem", pathlib.Path(self.tmp.name) / "key.pem")
        bad.socket = ctx.wrap_socket(bad.socket, server_side=True)
        for srv in (other, bad): threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            ph = Phone("127.0.0.1", bad.server_address[1], SR.fingerprint(pathlib.Path(self.tmp.name)))
            ph.token, ph.device_id = "t" * 43, "d_1"
            self.assertEqual(ph.upload("steps", [])[0], 307)
            self.assertEqual(heard, [])
        finally:
            for srv in (other, bad): srv.shutdown(); srv.server_close()

    # ----- the cache -----
    def test_cache_keeps_14_days(self):
        ph = self.paired()
        ph.upload_all(demo_day(DAY)[:10])
        now = dt.datetime.now(dt.timezone.utc)
        self.assertEqual(C.prune(self.data, now + dt.timedelta(days=13)), 0)
        self.assertEqual(C.prune(self.data, now + dt.timedelta(days=15)), 10)
        self.assertEqual(C.count(self.data), 0)

    def test_git_never_sees_the_cache(self):
        ph = self.paired(); ph.upload_all(demo_day(DAY)[:3])
        self.assertIn("imports/apple/cache.sqlite", (self.data / ".gitignore").read_text(encoding="utf-8"))
        self.assertIn("cache.sqlite*", (self.data / "imports" / "apple" / ".gitignore").read_text(encoding="utf-8"))
        if POSIX: self.assertEqual(stat.S_IMODE(C.path(self.data).stat().st_mode), 0o600)

    def test_status_never_shows_secrets(self):
        ph = self.paired()
        txt = json.dumps(self.rx.status())
        self.assertNotIn(ph.token, txt); self.assertNotIn("token", txt); self.assertNotIn("sha256", txt)


@unittest.skipUnless(HAVE, "needs the iphone extra")
class Pairing(unittest.TestCase):
    def test_qr_code_from_the_connections_page(self):
        import connections
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t); data = bkenv.init_data_folder(t / "data", ROOT / "demo")
            rx = SR.Receiver(folder=t / "sync", root=data, port=0, host="127.0.0.1", quiet=True)
            with mock.patch.object(SR, "_RX", rx), mock.patch.object(SR, "why_off", return_value=None):
                try:
                    code, r = connections.iphone_pair({})
                    self.assertEqual(code, 200)
                    self.assertTrue(r["qr"].startswith("data:image/svg+xml"))
                    self.assertRegex(r["typed"], r"^[A-Z2-9]{4}-[A-Z2-9]{4}$")
                    self.assertTrue(r["iphone"]["listening"]); self.assertGreater(r["iphone"]["pairing_left"], 590)
                    self.assertNotIn(rx.pairing["code_sha"], json.dumps(r))
                    code, r = connections.iphone_cancel()
                    self.assertFalse(r["iphone"]["listening"])
                finally: rx.stop()


if __name__ == "__main__":
    unittest.main()
