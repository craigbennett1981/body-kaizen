"""The raw cache: the last 14 days of uploads from paired iPhones, in imports/apple/cache.sqlite.

Kept so a fix to the translation (source_apple.py) can be re-applied to recent days without asking the phone again.
Git ignores the file (the data folder's .gitignore), and rows older than 14 days are deleted nightly, so nothing raw
enters the data folder's history. What lasts is the translated day files and the detail files beside this one.

Samples are keyed by HealthKit's UUID, so a resent batch changes nothing. Each row belongs to the phone that sent it
first: only that phone can change or delete it (two phones on one Apple account send the same samples).
"""
import contextlib, datetime as dt, json, pathlib, sqlite3, threading

import source_apple as A

KEEP_DAYS = 14
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
  uuid TEXT PRIMARY KEY, device TEXT NOT NULL, type TEXT NOT NULL,
  start TEXT NOT NULL, stop TEXT NOT NULL,   -- UTC ISO, for finding a day's samples
  body TEXT NOT NULL,                       -- the sample as sent (JSON)
  received TEXT NOT NULL                    -- UTC ISO: rows are kept 14 days from here
);
CREATE INDEX IF NOT EXISTS samples_start ON samples(start);
CREATE INDEX IF NOT EXISTS samples_received ON samples(received);
CREATE INDEX IF NOT EXISTS samples_device ON samples(device);
CREATE TABLE IF NOT EXISTS dirty (day TEXT PRIMARY KEY);   -- local days waiting to be translated
"""


def path(root): return pathlib.Path(root) / "imports" / "apple" / "cache.sqlite"


@contextlib.contextmanager
def _db(root):
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    try: p.parent.chmod(0o700)
    except OSError: pass
    gi = p.parent / ".gitignore"   # a data folder set up before the cache existed has no rule for it in its own .gitignore
    if not gi.exists(): gi.write_text("# The raw cache: 14 days of iPhone uploads, never committed\ncache.sqlite*\n", encoding="utf-8")
    new = not p.exists()
    con = sqlite3.connect(p, timeout=30)
    try:
        if new:
            try: p.chmod(0o600)
            except OSError: pass
        con.execute("PRAGMA secure_delete = ON")   # deleted health data is overwritten, not left in free pages
        con.executescript(SCHEMA)
        with con: yield con
    finally: con.close()


def _utc(ts): return A._parse(ts).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _now(now=None): return (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%S")


def _days(*samples):
    out = set()
    for s in samples:
        if s: out |= A.days_touched(s)
    return out


def put(root, device, typ, samples, now=None):
    """Store one batch. Each sample needs `uuid`; `type` comes from the batch. Samples the adapter can't use are
    skipped, not stored. -> {stored, updated, unchanged, skipped, days}"""
    res = {"stored": 0, "updated": 0, "unchanged": 0, "skipped": 0, "days": set()}
    rec = _now(now)
    with _lock, _db(root) as con:
        for s in samples:
            s = {**s, "type": typ}
            if not isinstance(s.get("uuid"), str) or A.valid(s): res["skipped"] += 1; continue
            body = json.dumps(s, sort_keys=True, separators=(",", ":"))
            row = con.execute("SELECT device, body FROM samples WHERE uuid = ?", (s["uuid"],)).fetchone()
            if row and row[0] != device: res["unchanged"] += 1; continue   # another phone's: not ours to change
            if row and row[1] == body: res["unchanged"] += 1; continue
            old = json.loads(row[1]) if row else None
            con.execute("INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?,?,?)",
                        (s["uuid"], device, typ, _utc(s["start"]), _utc(s["end"]), body, rec))
            res["updated" if row else "stored"] += 1
            res["days"] |= _days(s, old)
        con.executemany("INSERT OR IGNORE INTO dirty VALUES (?)", [(d.isoformat(),) for d in res["days"]])
    return res


def delete(root, device, uuids):
    """Delete samples this phone sent (others' are left alone). -> {deleted, days, workouts: [uuid]}"""
    res = {"deleted": 0, "days": set(), "workouts": []}
    with _lock, _db(root) as con:
        for u in uuids:
            row = con.execute("SELECT body, type FROM samples WHERE uuid = ? AND device = ?", (u, device)).fetchone()
            if not row: continue
            con.execute("DELETE FROM samples WHERE uuid = ?", (u,))
            res["deleted"] += 1; res["days"] |= _days(json.loads(row[0]))
            if row[1] == "workout": res["workouts"].append(u)
        con.executemany("INSERT OR IGNORE INTO dirty VALUES (?)", [(d.isoformat(),) for d in res["days"]])
    return res


def erase(root, device):
    """Everything one phone sent. -> number of rows deleted"""
    if not path(root).exists(): return 0
    with _lock, _db(root) as con:
        return con.execute("DELETE FROM samples WHERE device = ?", (device,)).rowcount


def around(root, day):
    """Every cached sample that can bear on local `day`: from two days before to two days after (time zones, and a
    night that began the evening before)."""
    if not path(root).exists(): return []
    d = dt.date.fromisoformat(str(day))
    a = (d - dt.timedelta(days=2)).isoformat(); b = (d + dt.timedelta(days=3)).isoformat()
    with _db(root) as con:
        rows = con.execute("SELECT body FROM samples WHERE stop >= ? AND start < ? ORDER BY start", (a, b)).fetchall()
    return [json.loads(r[0]) for r in rows]


def take_dirty(root):
    """The days waiting to be translated, clearing the list."""
    if not path(root).exists(): return []
    with _lock, _db(root) as con:
        days = [r[0] for r in con.execute("SELECT day FROM dirty ORDER BY day")]
        con.execute("DELETE FROM dirty")
    return days


def mark_dirty(root, days):
    with _lock, _db(root) as con:
        con.executemany("INSERT OR IGNORE INTO dirty VALUES (?)", [(str(d),) for d in days])


def cached_days(root):
    """Local days with any cached sample, for re-translating after a fix."""
    if not path(root).exists(): return []
    out = set()
    with _db(root) as con:
        for (b,) in con.execute("SELECT body FROM samples"): out |= A.days_touched(json.loads(b))
    return sorted(d.isoformat() for d in out)


def prune(root, now=None, keep_days=KEEP_DAYS):
    """Delete rows received more than `keep_days` ago. -> number deleted"""
    if not path(root).exists(): return 0
    cut = _now((now or dt.datetime.now(dt.timezone.utc)) - dt.timedelta(days=keep_days))
    with _lock, _db(root) as con:
        n = con.execute("DELETE FROM samples WHERE received < ?", (cut,)).rowcount
    return n


def count(root, device=None):
    if not path(root).exists(): return 0
    with _db(root) as con:
        q, a = ("SELECT COUNT(*) FROM samples WHERE device = ?", (device,)) if device else ("SELECT COUNT(*) FROM samples", ())
        return con.execute(q, a).fetchone()[0]
