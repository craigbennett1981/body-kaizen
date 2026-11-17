"""The sync receiver: where the Body Kaizen Sync iPhone app sends Apple Health data, over the home network.

A second listener, separate from the dashboard (which stays on 127.0.0.1). It is off until a phone is paired, or
while a pairing code shown on the Connections page is live, and it can only be uploaded to: four POST routes, no
pages, nothing to read back. See docs/iphone-sync.md, "The sync receiver", and SECURITY.md.

- TLS with a self-signed ECDSA P-256 certificate kept in ~/.body-kaizen/sync/ (0600 files in a 0700 folder). The
  phone pins its SHA-256 fingerprint from the QR code, so no certificate authority is involved.
- One random 256-bit token per phone; only its SHA-256 is stored.
- Connections from outside private address ranges are dropped before TLS, before anything else.
- Limits: 5 MB per request (gzip JSON), requests per minute and bytes per day per phone, samples per batch.
- An upload that was under way when that phone was erased or removed is refused (409); pairing and erasing never
  run at the same time (one lock).

Needs the `iphone` extra (cryptography for the certificate, segno for the QR code): pip install 'body-kaizen[iphone]'.
"""
import datetime as dt, hashlib, hmac, ipaddress, json, os, pathlib, platform, secrets, socket, ssl, subprocess
import sys, threading, time, traceback, unicodedata, zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import bkenv          # noqa: E402
import apple_cache    # noqa: E402
import apple_import   # noqa: E402
import source_apple   # noqa: E402

SYNC_DIR = pathlib.Path(os.environ.get("BK_SYNC_DIR") or "~/.body-kaizen/sync").expanduser()
PORT = int(os.environ.get("FT_SYNC_PORT", "8766"))

MAX_BODY = 5 * 1024 * 1024          # bytes on the wire (gzip JSON)
MAX_JSON = 64 * 1024 * 1024         # bytes once unzipped: a small upload can't unzip into a huge one
MAX_SAMPLES = 20_000                # per batch
MAX_UUIDS = 20_000                  # per deletion request
RATE = 120                          # requests per phone per minute
DAILY_BYTES = 300 * 1024 * 1024     # bytes per phone per day: a stolen token can't fill the disk
CODE_TTL = 600                      # a pairing code lasts 10 minutes
CODE_TRIES = 5                      # wrong codes before the pairing code is burned
QUIET = 20                          # seconds after the last upload before translating
TYPED = "ABCDEFGHJKMNPQRSTVWXYZ23456789"   # the typed code's letters: no 0/O, 1/I/L, U
REPORT_TRIGGERS = {"new_data", "refresh", "processing", "unlock", "leaving", "manual", "url_session", "first_sync"}

# Private ranges (RFC 1918, link-local, unique local) and this computer itself.
PRIVATE = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16",
                                              "fc00::/7", "fe80::/10", "127.0.0.0/8", "::1/128")]


def installed():
    try:
        import cryptography, segno  # noqa: F401
        return True
    except ImportError: return False


def allowed(host):
    """Whether a connection from `host` may be answered at all: private, link-local or this computer only."""
    try: ip = ipaddress.ip_address(str(host).split("%")[0])
    except ValueError: return False
    if ip.version == 6 and ip.ipv4_mapped: ip = ip.ipv4_mapped
    return any(ip in n for n in PRIVATE)


def clean_name(s, most=60):
    """A device name fit for logs and the Connections page: no control or format characters, one line, short."""
    s = "".join(" " if unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") else c for c in str(s or ""))
    return " ".join(s.split())[:most] or "iPhone"


def _sha(s): return hashlib.sha256(s.encode() if isinstance(s, str) else s).hexdigest()


def _now(): return dt.datetime.now(dt.timezone.utc)


def _iso(t=None): return (t or _now()).isoformat(timespec="seconds")


def computer_name():
    if platform.system() == "Darwin":
        try:
            r = subprocess.run(["scutil", "--get", "ComputerName"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip(): return clean_name(r.stdout.strip())
        except (OSError, subprocess.SubprocessError): pass
    return clean_name(socket.gethostname().split(".")[0] or "Body Kaizen")


def local_addrs():
    """This computer's private IPv4 addresses, for the QR code (the phone also finds the Mac by Bonjour later)."""
    out = []
    for probe in ("192.168.255.255", "10.255.255.255", "172.31.255.255"):   # UDP connect sends nothing
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((probe, 9)); ip = s.getsockname()[0]
        except OSError: continue
        if ip not in out and allowed(ip) and not ipaddress.ip_address(ip).is_loopback: out.append(ip)
    try:
        for fam, *_, sa in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = sa[0]
            if ip not in out and allowed(ip) and not ipaddress.ip_address(ip).is_loopback: out.append(ip)
    except OSError: pass
    return out[:4]


# ---------- the certificate ----------

def make_cert(folder):
    """A self-signed ECDSA P-256 certificate for the receiver, made once. -> SHA-256 fingerprint (hex) of its DER."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Body Kaizen sync receiver")])
    now = _now() - dt.timedelta(days=1)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now).not_valid_after(now + dt.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    bkenv.write_private(folder / "key.pem", key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                               serialization.NoEncryption()).decode())
    bkenv.write_private(folder / "cert.pem", cert.public_bytes(serialization.Encoding.PEM).decode())
    return fingerprint(folder)


def fingerprint(folder):
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert((folder / "cert.pem").read_text(encoding="utf-8"))).hexdigest()


# ---------- the receiver ----------

class Receiver:
    def __init__(self, folder=SYNC_DIR, root=None, port=PORT, host=None, is_allowed=allowed, translate_after=QUIET, quiet=False):
        self.dir = pathlib.Path(folder); self.root = pathlib.Path(root or bkenv.DATA)
        self.port, self.host, self.is_allowed, self.quiet, self._quiet_log = port, host, is_allowed, translate_after, quiet
        self.lock = threading.RLock()     # pairing, erasing, removing and storing an upload: one at a time
        self.pairing = None               # {code_sha, typed_sha, expires, tries}
        self.server = self.thread = self.worker = None
        self._rate = {}                   # device id -> [request times in the last minute]
        self._due = None; self._gone = set(); self._pruned = None; self._stop = threading.Event()

    def log(self, msg):
        if not self._quiet_log: print(f"sync: {msg}", flush=True)

    # ----- files -----
    def _read(self, name, default):
        try: return json.loads((self.dir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError): return default

    def _write(self, name, obj):
        bkenv.private_dir(self.dir)
        tmp = self.dir / f".{name}.tmp"
        bkenv.write_private(tmp, json.dumps(obj, indent=1)); os.replace(tmp, self.dir / name)

    def devices(self): return self._read("devices.json", {}).get("devices", [])

    def _save_devices(self, devs): self._write("devices.json", {"devices": devs})

    def _status(self): return self._read("status.json", {})

    # ----- pairing -----
    def start_pairing(self):
        """A one-time code (128-bit, 10 minutes, single use) and its 8-character typed form; starts the listener.
        -> {payload (for the QR code), typed, expires_in}"""
        with self.lock:
            bkenv.private_dir(self.dir)
            fp = fingerprint(self.dir) if (self.dir / "cert.pem").exists() and (self.dir / "key.pem").exists() else make_cert(self.dir)
            code = secrets.token_urlsafe(16)                                   # 128 bits
            typed = "".join(secrets.choice(TYPED) for _ in range(8))
            self.pairing = {"code_sha": _sha(code), "typed_sha": _sha(typed), "expires": time.monotonic() + CODE_TTL, "tries": 0}
            payload = {"v": 1, "name": computer_name(), "port": self.port, "addrs": local_addrs(), "fp": fp, "code": code}
        self.ensure()
        return {"payload": payload, "typed": f"{typed[:4]}-{typed[4:]}", "expires_in": CODE_TTL}

    def cancel_pairing(self):
        with self.lock: self.pairing = None
        self.ensure()

    def pairing_left(self):
        p = self.pairing
        return max(0, round(p["expires"] - time.monotonic())) if p and p["expires"] > time.monotonic() else 0

    def pair(self, body):
        """POST /v1/pair {code, device_name} -> (status, reply). The code is burned on success, and after 5 wrong tries."""
        code = str(body.get("code") or "")
        with self.lock:
            p = self.pairing
            if not p or p["expires"] <= time.monotonic(): self.pairing = None; return 403, {"error": "no pairing code is live"}
            typed = code.upper().replace("-", "").replace(" ", "")
            if not (hmac.compare_digest(_sha(code), p["code_sha"]) or hmac.compare_digest(_sha(typed), p["typed_sha"])):
                p["tries"] += 1
                if p["tries"] >= CODE_TRIES: self.pairing = None
                return 403, {"error": "wrong code"}
            self.pairing = None
            token = secrets.token_urlsafe(32)                                  # 256 bits
            dev = {"id": "d_" + secrets.token_hex(6), "name": clean_name(body.get("device_name")), "token_sha256": _sha(token),
                   "paired": _iso(), "generation": 1}
            self._save_devices(self.devices() + [dev])
        self.log(f"paired {dev['name']} ({dev['id']})")
        return 200, {"device_id": dev["id"], "token": token, "name": computer_name()}

    def remove(self, device_id):
        """Unpair a phone and erase what it sent from the raw cache (the day files keep what was translated)."""
        with self.lock:
            devs = self.devices()
            if not any(d["id"] == device_id for d in devs): return False
            self._save_devices([d for d in devs if d["id"] != device_id])
            apple_cache.erase(self.root, device_id)
            st = self._status(); st.pop(device_id, None); self._write("status.json", st)
        self.ensure()
        return True

    def erase(self, device_id):
        """Delete everything a phone sent from the raw cache and start a new generation, so an upload still under way
        is refused instead of bringing erased data back."""
        with self.lock:
            devs = self.devices()
            for d in devs:
                if d["id"] == device_id: d["generation"] = d.get("generation", 1) + 1
            self._save_devices(devs)
            return apple_cache.erase(self.root, device_id)

    # ----- requests -----
    def authenticate(self, headers, body_device):
        auth = headers.get("Authorization") or ""
        if not auth.startswith("Bearer "): return None
        h = _sha(auth[7:].strip())
        dev = next((d for d in self.devices() if hmac.compare_digest(d["token_sha256"], h)), None)
        if not dev or (body_device is not None and body_device != dev["id"]): return None
        return dev

    def rate_ok(self, device_id):
        now = time.monotonic()
        q = [t for t in self._rate.get(device_id, []) if now - t < 60]
        q.append(now); self._rate[device_id] = q
        return len(q) <= RATE

    def count_bytes(self, device_id, n):
        """Add `n` received bytes to the phone's day. -> False once over the daily limit."""
        with self.lock:
            st = self._status(); s = st.setdefault(device_id, {})
            today = dt.date.today().isoformat()
            b = s.get("bytes_today") if (s.get("bytes_today") or {}).get("date") == today else {"date": today, "n": 0}
            b["n"] += n; s["bytes_today"] = b; self._write("status.json", st)
            return b["n"] <= DAILY_BYTES

    def store(self, dev, body):
        """POST /v1/samples once authenticated and read. -> (status, reply)"""
        typ = body.get("type")
        if typ not in source_apple.TYPES: return 400, {"error": "unknown type"}   # before anything touches it
        samples = body.get("samples")
        if not isinstance(samples, list) or len(samples) > MAX_SAMPLES or not all(isinstance(s, dict) for s in samples):
            return 400, {"error": "samples must be a list of objects"}
        with self.lock:
            now = next((d for d in self.devices() if d["id"] == dev["id"]), None)
            if not now or now.get("generation") != dev.get("generation"): return 409, {"error": "erased or removed while this was sent"}
            res = apple_cache.put(self.root, dev["id"], typ, samples)
            st = self._status(); s = st.setdefault(dev["id"], {})
            s["last_upload"] = _iso()
            today = dt.date.today().isoformat()
            c = s.get("samples_today") if (s.get("samples_today") or {}).get("date") == today else {"date": today, "n": 0}
            c["n"] += res["stored"] + res["updated"]; s["samples_today"] = c
            if isinstance(body.get("report"), dict): s["last_report"] = {**clean_report(body["report"]), "at": _iso()}
            self._write("status.json", st)
        if res["days"]: self._schedule()
        return 200, {"ok": True, **{k: res[k] for k in ("stored", "updated", "unchanged", "skipped")}}

    def deletions(self, dev, body):
        uuids = body.get("uuids")
        if not isinstance(uuids, list) or len(uuids) > MAX_UUIDS or not all(isinstance(u, str) and 0 < len(u) <= 64 for u in uuids):
            return 400, {"error": "uuids must be a list of strings"}
        with self.lock:
            now = next((d for d in self.devices() if d["id"] == dev["id"]), None)
            if not now or now.get("generation") != dev.get("generation"): return 409, {"error": "erased or removed while this was sent"}
            res = apple_cache.delete(self.root, dev["id"], uuids)
            self._gone |= set(res["workouts"])
        if res["days"]: self._schedule()
        return 200, {"ok": True, "deleted": res["deleted"]}

    # ----- translating -----
    def _schedule(self): self._due = time.monotonic() + self.quiet

    def flush(self, git=True):
        """Translate the days uploads have touched into day files now. -> summary lines"""
        days = apple_cache.take_dirty(self.root)
        with self.lock: gone, self._gone = self._gone, set()
        if not days: return []
        paths, summary = apple_import.translate(self.root, days, gone)
        if git: apple_import.commit(self.root, paths, summary)
        for line in summary: self.log(f"{line}")
        return summary

    def _work(self):
        while not self._stop.wait(1):
            try:
                if self._due and time.monotonic() >= self._due: self._due = None; self.flush()
                today = dt.date.today()
                if self._pruned != today: self._pruned = today; apple_cache.prune(self.root)   # nightly, and at start
                if self.pairing and not self.pairing_left(): self.cancel_pairing()
            except Exception: traceback.print_exc()

    # ----- the listener -----
    def wanted(self): return bool(self.devices()) or bool(self.pairing_left())

    def ensure(self):
        """Listen while a phone is paired or a pairing code is live; stop otherwise."""
        with self.lock:
            if self.wanted() and not self.server: self._start()
            elif not self.wanted() and self.server: self._shutdown()

    def _start(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(self.dir / "cert.pem", self.dir / "key.pem")
        self.server = _Server(self.host, self.port, ctx, self)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, name="sync-receiver", daemon=True); self.thread.start()
        if not self.worker:
            self._stop.clear()
            self.worker = threading.Thread(target=self._work, name="sync-translate", daemon=True); self.worker.start()
        self.log(f"receiving from paired phones on port {self.port}")

    def _shutdown(self):
        srv, self.server = self.server, None
        srv.shutdown(); srv.server_close()
        self.log("stopped listening (no paired phones)")

    def stop(self):
        with self.lock:
            if self.server: self._shutdown()
        self._stop.set(); self.worker = None
        if self._due: self._due = None; self.flush()

    def status(self):
        """For the Connections page: never a token, code or key."""
        st = self._status()
        devs = [{"id": d["id"], "name": d["name"], "paired": d.get("paired"), "last_upload": st.get(d["id"], {}).get("last_upload"),
                 "last_report": st.get(d["id"], {}).get("last_report"),
                 "samples_today": (st.get(d["id"], {}).get("samples_today") or {}).get("n", 0)
                 if (st.get(d["id"], {}).get("samples_today") or {}).get("date") == dt.date.today().isoformat() else 0}
                for d in self.devices()]
        return {"installed": installed(), "blocked": bkenv.sync_blocked(), "listening": bool(self.server), "port": self.port,
                "devices": devs, "pairing_left": self.pairing_left()}


def clean_report(r):
    """The phone's short wake-up report, reduced to known fields (it is shown on the Connections page)."""
    out = {}
    if r.get("trigger") in REPORT_TRIGGERS: out["trigger"] = r["trigger"]
    for k in ("locked", "battery", "low_power"):
        if isinstance(r.get(k), bool): out[k] = r[k]
    if isinstance(r.get("sent"), int) and not isinstance(r.get("sent"), bool) and 0 <= r["sent"] < 10**8: out["sent"] = r["sent"]
    return out


class _Server(ThreadingHTTPServer):
    """Accepts plain connections, drops any from outside private ranges, and only then starts TLS (in the
    connection's own thread, so a slow handshake holds up no one else)."""
    daemon_threads = True
    request_queue_size = 32

    def __init__(self, host, port, ctx, rx):
        self.ctx, self.rx = ctx, rx
        if host is None:   # every interface, IPv4 and IPv6
            self.address_family = socket.AF_INET6
            try: super().__init__(("::", port), _Handler); return
            except OSError: self.address_family = socket.AF_INET; host = "0.0.0.0"
        if ":" in host: self.address_family = socket.AF_INET6
        super().__init__((host, port), _Handler)

    def server_bind(self):
        if self.address_family == socket.AF_INET6:
            try: self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            except (OSError, AttributeError): pass
        super().server_bind()

    def verify_request(self, request, client_address):
        return self.rx.is_allowed(client_address[0])

    def finish_request(self, request, client_address):
        request.settimeout(15)
        try: tls = self.ctx.wrap_socket(request, server_side=True)
        except (ssl.SSLError, OSError): return
        try: _Handler(tls, client_address, self)
        finally:
            try: tls.close()
            except OSError: pass


class _Handler(BaseHTTPRequestHandler):
    timeout = 15
    server_version = "BodyKaizenSync"
    sys_version = ""

    def _send(self, code, obj):
        self._drain()
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers(); self.wfile.write(b)

    def _drain(self):
        """Read and drop a request body that wasn't read, so the answer isn't lost when the connection closes (a
        refusal comes before the body is read). Never more than MAX_BODY; a longer one is cut off."""
        if getattr(self, "_drained", False): return
        self._drained = True
        try: n = int(self.headers.get("Content-Length") or 0)
        except (ValueError, AttributeError): n = 0
        if 0 < n <= MAX_BODY:
            try: self.rfile.read(n)
            except OSError: pass

    def do_GET(self): self._send(405, {"error": "upload only"})
    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = do_GET

    def _body(self):
        """The request's JSON, or None after answering. JSON only, at most MAX_BODY on the wire and MAX_JSON unzipped."""
        h = self.headers
        if (h.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json": self._send(415, {"error": "JSON only"}); return None
        try: n = int(h.get("Content-Length") or -1)
        except ValueError: n = -1
        if n < 0: self._send(411, {"error": "length required"}); return None
        if n > MAX_BODY:   # not read: take what has already arrived (so a short sender gets the answer), then hang up
            self._drained = True
            try: self.connection.settimeout(0.3); self.connection.recv(65536)
            except OSError: pass
            self._send(413, {"error": "too large"}); return None
        raw = self.rfile.read(n); self._drained = True
        if len(raw) != n: return None
        enc = (h.get("Content-Encoding") or "identity").strip().lower()
        if enc == "gzip":
            d = zlib.decompressobj(16 + zlib.MAX_WBITS)
            try: raw = d.decompress(raw, MAX_JSON)
            except zlib.error: self._send(400, {"error": "bad gzip"}); return None
            if d.unconsumed_tail: self._send(413, {"error": "too large"}); return None
        elif enc != "identity": self._send(415, {"error": "gzip or nothing"}); return None
        try: body = json.loads(raw)
        except ValueError: self._send(400, {"error": "bad json"}); return None
        if not isinstance(body, dict): self._send(400, {"error": "bad json"}); return None
        self._n = n
        return body

    def do_POST(self):
        rx = self.server.rx
        try:
            path = self.path.split("?")[0]
            if path not in ("/v1/pair", "/v1/samples", "/v1/deletions", "/v1/ping"): return self._send(404, {"error": "not found"})
            if path == "/v1/pair":
                body = self._body()
                if body is None: return
                return self._send(*rx.pair(body))
            pre = rx.authenticate(self.headers, None)      # the token first: nothing is read for a stranger
            if not pre: return self._send(401, {"error": "not paired"})
            if not rx.rate_ok(pre["id"]): return self._send(429, {"error": "too many requests"})
            body = self._body()
            if body is None: return
            dev = rx.authenticate(self.headers, body.get("device_id"))
            if not dev: return self._send(401, {"error": "not paired"})
            if not rx.count_bytes(dev["id"], self._n): return self._send(429, {"error": "daily limit reached"})
            if path == "/v1/ping": return self._send(200, {"ok": True})
            if path == "/v1/samples": return self._send(*rx.store(pre, body))
            return self._send(*rx.deletions(pre, body))
        except Exception:
            traceback.print_exc()
            try: self._send(500, {"error": "server error"})
            except OSError: pass

    def log_message(self, fmt, *args):
        if os.environ.get("FT_LOG"): super().log_message(fmt, *args)


# ---------- the dashboard's one receiver ----------

_RX = None


def receiver():
    global _RX
    if _RX is None: _RX = Receiver()
    return _RX


def why_off():
    """Why the receiver can't run here, or None."""
    if not installed(): return "the iPhone packages aren't installed"
    if os.environ.get("FT_NO_SYNC"): return "syncing is off (FT_NO_SYNC)"
    return bkenv.sync_blocked()


def start_if_paired():
    """Called as the dashboard starts: listen if a phone is paired."""
    if why_off(): return False
    try: receiver().ensure(); return bool(receiver().server)
    except Exception: traceback.print_exc(); return False
