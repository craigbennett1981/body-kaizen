"""A stand-in for the Body Kaizen Sync iPhone app, for tests: it makes demo HealthKit samples (made-up numbers, no
real person's data) in the wire format the receiver takes, and talks to the receiver the way the app will: pinned
TLS certificate, token header, gzip JSON, no redirects followed.
"""
import datetime as dt, gzip, hashlib, http.client, json, ssl, uuid
from zoneinfo import ZoneInfo

WATCH = {"name": "Demo Watch", "bundle": "com.apple.health", "device": "Watch7,3"}
PHONE = {"name": "Demo iPhone", "bundle": "com.apple.health", "device": "iPhone16,2"}
OTHER = {"name": "Some Sleep App", "bundle": "com.example.sleep", "device": ""}


def uid(*parts):
    """A stable UUID from its parts, as the app makes for its 15-minute buckets (a resend keeps the same one)."""
    return str(uuid.UUID(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:32])).upper()


class Samples:
    """Builds samples in one time zone. Times are local wall-clock 'YYYY-MM-DDTHH:MM' strings."""

    def __init__(self, tz="Europe/London"):
        self.tz = tz; self.z = ZoneInfo(tz); self.out = []

    def t(self, local):
        return dt.datetime.fromisoformat(local).replace(tzinfo=self.z)

    def add(self, typ, start, end=None, value=None, unit="", source=WATCH, metadata=None, uuid_=None):
        a = self.t(start); b = self.t(end) if end else a
        s = {"uuid": uuid_ or uid(typ, start, end, value, source["device"], len(self.out)), "type": typ,
             "start": a.isoformat(), "end": b.isoformat(), "tz": self.tz, "value": value, "unit": unit,
             "source": dict(source), "metadata": metadata or {}}
        self.out.append(s); return s

    def sleep(self, parts, source=WATCH):
        """parts: [(start, end, stage)] with stage in_bed/asleep/awake/core/deep/rem."""
        for a, b, k in parts: self.add("sleep", a, b, k, "", source)
        return self

    def per_minute_hr(self, start, end, bpm, source=WATCH):
        t = self.t(start); stop = self.t(end); i = 0
        while t < stop:
            v = bpm(i) if callable(bpm) else bpm
            lt = t.strftime("%Y-%m-%dT%H:%M")
            self.add("heart_rate", lt, lt, v, "count/min", source, {"min": v - 2, "max": v + 3})
            t += dt.timedelta(minutes=1); i += 1
        return self

    def buckets(self, typ, start, end, per_bucket, unit, source=WATCH):
        t = self.t(start); stop = self.t(end)
        while t < stop:
            a = t.strftime("%Y-%m-%dT%H:%M"); b = (t + dt.timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M")
            v = per_bucket(t) if callable(per_bucket) else per_bucket
            if v: self.add(typ, a, b, v, unit, source, uuid_=uid(typ, a, source["device"]))
            t += dt.timedelta(minutes=15)
        return self


def demo_day(day="2026-11-17", tz="Europe/London"):
    """A plausible demo day: a watch night with stages, an iPhone in-bed, resting HR, HRV, steps and energy from both
    watch and phone, an evening run with a full heart-rate trace, a weigh-in and a blood-pressure reading."""
    d = dt.date.fromisoformat(day); prev = (d - dt.timedelta(days=1)).isoformat()
    S = Samples(tz)
    S.sleep([(f"{prev}T22:50", f"{day}T06:40", "in_bed")], PHONE)
    S.sleep([(f"{prev}T23:10", f"{day}T00:40", "core"), (f"{day}T00:40", f"{day}T01:50", "deep"),
             (f"{day}T01:50", f"{day}T02:05", "awake"), (f"{day}T02:05", f"{day}T03:30", "core"),
             (f"{day}T03:30", f"{day}T04:40", "rem"), (f"{day}T04:40", f"{day}T06:30", "core")])
    S.per_minute_hr(f"{prev}T23:00", f"{day}T06:45", lambda i: 50 + (i % 7))
    S.add("hrv_sdnn", f"{day}T03:00", None, 48.0, "ms")
    S.add("hrv_sdnn", f"{day}T05:00", None, 52.0, "ms")
    S.add("respiratory_rate", f"{day}T03:00", None, 14.5, "count/min")
    S.add("oxygen_saturation", f"{day}T03:00", None, 96.0, "%")
    S.add("oxygen_saturation", f"{day}T04:00", None, 93.0, "%")
    S.add("resting_heart_rate", f"{day}T07:00", None, 49, "count/min")
    S.buckets("steps", f"{day}T07:00", f"{day}T21:00", 300, "count", WATCH)
    S.buckets("steps", f"{day}T07:00", f"{day}T22:00", 250, "count", PHONE)       # phone counts too; one extra hour alone
    S.buckets("active_energy", f"{day}T07:00", f"{day}T21:00", 12.0, "kcal", WATCH)
    S.buckets("basal_energy", f"{day}T00:00", f"{day}T23:59", 18.0, "kcal", WATCH)
    S.add("workout", f"{day}T18:00", f"{day}T18:40", 2400, "s", WATCH,
          {"activity": "running", "indoor": False, "distance_m": 7000.0, "energy_kcal": 420.0})
    t = S.t(f"{day}T18:00")
    for i in range(0, 2400, 5):   # every few seconds inside the workout: a warm-up, then steady
        lt = (t + dt.timedelta(seconds=i))
        S.out.append({"uuid": uid("hr", day, i), "type": "heart_rate", "start": lt.isoformat(), "end": lt.isoformat(),
                      "tz": tz, "value": 110 + min(i // 30, 40), "unit": "count/min", "source": dict(WATCH), "metadata": {}})
    S.add("body_mass", f"{day}T07:05", None, 78.4, "kg", {"name": "Demo Scale", "bundle": "com.example.scale", "device": ""})
    S.add("body_fat", f"{day}T07:05", None, 19.5, "%", {"name": "Demo Scale", "bundle": "com.example.scale", "device": ""})
    S.add("blood_pressure", f"{day}T07:30", None, {"systolic": 117, "diastolic": 76}, "mmHg", PHONE)
    S.add("vo2max", f"{day}T18:45", None, 47.3, "ml/(kg*min)")
    return S.out


# ---------- talking to the receiver ----------

class Phone:
    """Pairs with a receiver and uploads, as the app does: the certificate is pinned by its SHA-256 fingerprint (no
    certificate authority), and redirects are never followed."""

    def __init__(self, host, port, fingerprint, name="Demo iPhone"):
        self.host, self.port, self.fp, self.name = host, port, fingerprint, name
        self.token = self.device_id = None

    def _conn(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE   # trust comes from the pin below, not a CA
        c = http.client.HTTPSConnection(self.host, self.port, context=ctx, timeout=10)
        c.connect()
        der = c.sock.getpeercert(binary_form=True)
        if hashlib.sha256(der).hexdigest() != self.fp:
            c.close(); raise ssl.SSLError("certificate doesn't match the pinned fingerprint")
        return c

    def post(self, path, body, token=True, raw=None, headers=None):
        """-> (status, json or None). A redirect comes back as its status: it is never followed."""
        data = raw if raw is not None else gzip.compress(json.dumps(body).encode())
        h = {"Content-Type": "application/json", "Content-Encoding": "gzip", "Content-Length": str(len(data))}
        if token and self.token: h["Authorization"] = f"Bearer {self.token}"
        h.update(headers or {})
        c = self._conn()
        try:
            c.request("POST", path, body=data, headers=h)
            r = c.getresponse(); txt = r.read()
            try: j = json.loads(txt) if txt else None
            except ValueError: j = None
            return r.status, j
        finally: c.close()

    def pair(self, code):
        st, j = self.post("/v1/pair", {"code": code, "device_name": self.name}, token=False)
        if st == 200: self.token, self.device_id = j["token"], j["device_id"]
        return st, j

    def upload(self, typ, samples, report=None):
        body = {"device_id": self.device_id, "type": typ, "samples": samples}
        if report: body["report"] = report
        return self.post("/v1/samples", body)

    def upload_all(self, samples, report=None):
        """Every sample, one batch per type, as the app sends them. -> [(type, status, reply)]"""
        by = {}
        for s in samples: by.setdefault(s["type"], []).append({k: v for k, v in s.items() if k != "type"})
        return [(t, *self.upload(t, v, report)) for t, v in by.items()]

    def delete(self, uuids):
        return self.post("/v1/deletions", {"device_id": self.device_id, "uuids": list(uuids)})

    def ping(self):
        return self.post("/v1/ping", {"device_id": self.device_id})
