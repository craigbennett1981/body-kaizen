"""Where things live, and the user's settings.

CODE  the Body Kaizen code (this repository, or the installed body_kaizen package)
DATA  your data folder: FT_DATA if set; else the folder chosen in the dashboard's first-run setup (saved in
      ~/.body-kaizen/config.json); else the code folder when run from a clone (a single-folder setup), or
      ~/body-kaizen-data when installed from PyPI

settings.yaml in the data folder holds your profile (name, start date), timezone and options.
"""
import datetime as dt, json, os, pathlib, re, shutil
import yaml

CODE = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_DATA = CODE if (CODE / "pyproject.toml").exists() else pathlib.Path("~/body-kaizen-data")
# Your choice of data folder from the first-run setup. BK_CONFIG moves it (tests use a temporary one).
CONFIG = pathlib.Path(os.environ.get("BK_CONFIG") or "~/.body-kaizen/config.json").expanduser()
DATA_DIRS = ("days", "imports", "measurements")   # the dated part of a data folder; the rest is reference files

def read_config():
    try: c = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}
    return c if isinstance(c, dict) else {}

def resolve_data(env=None, cfg=None):
    """FT_DATA wins; then the folder saved by the first-run setup; then the default."""
    env = os.environ if env is None else env
    cfg = read_config() if cfg is None else cfg
    return pathlib.Path(env.get("FT_DATA") or cfg.get("data_dir") or DEFAULT_DATA).expanduser().resolve()

DATA = resolve_data()
SETTINGS = DATA / "settings.yaml"

_cache = {"mtime": None, "data": {}}

def settings():
    try: m = SETTINGS.stat().st_mtime
    except FileNotFoundError: return {}
    if m != _cache["mtime"]:
        _cache["data"] = yaml.safe_load(SETTINGS.read_text(encoding="utf-8")) or {}; _cache["mtime"] = m
    return _cache["data"]

def local_tz_name():
    """IANA name of this computer's timezone (TZ, else /etc/localtime), or None."""
    if os.environ.get("TZ") and "/" in os.environ["TZ"]: return os.environ["TZ"].lstrip(":")
    try:
        link = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in link: return link.split("zoneinfo/", 1)[1]
    except OSError: pass
    return None

def tz_name():
    return settings().get("timezone") or local_tz_name() or "UTC"

def tz():
    """The user's timezone: settings.yaml `timezone`, else this computer's."""
    from zoneinfo import ZoneInfo
    try: return ZoneInfo(tz_name())
    except Exception: return dt.datetime.now().astimezone().tzinfo

def now():
    """The current time in the user's timezone. FT_NOW (YYYY-MM-DDTHH:MM, local) fixes it: the static demo is exported
    as of one moment, so its timelines, pace and "now" line all agree."""
    fixed = os.environ.get("FT_NOW")
    if fixed:
        return dt.datetime.fromisoformat(fixed[:16]).replace(tzinfo=tz())
    return dt.datetime.now(tz())

def today():
    return now().date()

def profile():
    """{name, start_date}; empty until first-run setup has been done."""
    return settings().get("profile") or {}

def first_day():
    """Earliest day file, used as the default start date."""
    days = sorted((DATA / "days").rglob("*.yaml"))
    return days[0].stem if days else None

def start_date():
    s = profile().get("start_date") or first_day()
    return dt.date.fromisoformat(str(s)) if s else today()

def git_options():
    g = settings().get("git") or {}
    return {"auto_commit": g.get("auto_commit", True), "auto_push": g.get("auto_push", False)}

def in_code_repo(data=None):
    """True when the data folder sits inside the code folder without being it (demo/, or a stray demo/demo/).
    The single-folder setup (data folder == code folder) is not counted."""
    data = pathlib.Path(data or DATA).resolve()
    return data != CODE and data.is_relative_to(CODE)

def is_demo(data=None):
    """The repo's demo/ folder, or any folder whose settings say it's the demo person."""
    data = pathlib.Path(data or DATA).resolve()
    if data == CODE / "demo": return True
    try: s = settings() if data == DATA else yaml.safe_load((data / "settings.yaml").read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError): s = {}
    return "(demo)" in str((s.get("profile") or {}).get("name") or "")

def sync_blocked():
    """Why Garmin/Libre syncs must not run against this data folder, or None if they may."""
    if is_demo(): return "this is demo data: syncing would pull your real health data into it"
    if in_code_repo(): return "the data folder is inside the code repository: syncing would put health data in it"
    return None

def child_env():
    """Environment for sync subprocesses: FT_DATA made absolute, so a relative FT_DATA can't resolve twice
    against the child's working directory. Output in UTF-8 everywhere (Windows otherwise uses the local code page
    for redirected output, and a '→' in a log line would crash the child)."""
    return {**os.environ, "FT_DATA": str(DATA), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}

def save_profile(name, start, timezone):
    """Write profile + timezone into settings.yaml, keeping the rest of the file (and its comments) as it is."""
    txt = SETTINGS.read_text(encoding="utf-8") if SETTINGS.exists() else ""
    txt = re.sub(r"(?m)^profile:.*\n(?:[ \t]+.*\n?)*", "", txt)          # drop an old profile block
    txt = re.sub(r"(?m)^timezone:.*\n?", "", txt)
    block = yaml.safe_dump({"profile": {"name": str(name).strip(), "start_date": str(start)}, "timezone": timezone},
                           sort_keys=False, allow_unicode=True)
    SETTINGS.write_text(block + ("\n" + txt.lstrip("\n") if txt.strip() else ""), encoding="utf-8")
    _cache["mtime"] = None

# Libre login: config file and keychain service. New installs use ~/.body-kaizen; an earlier
# ~/.foodtracker login keeps working (read only) until libre_login.py is run again.
LIBRE_CFG_NEW = CONFIG.parent / "libre.json"   # beside config.json (BK_CONFIG moves both: tests)
LIBRE_CFG_OLD = pathlib.Path("~/.foodtracker/libre.json").expanduser()
LIBRE_SERVICE_NEW, LIBRE_SERVICE_OLD = "body-kaizen-librelinkup", "foodtracker-librelinkup"

def libre_cfg():
    return LIBRE_CFG_NEW if LIBRE_CFG_NEW.exists() or not LIBRE_CFG_OLD.exists() else LIBRE_CFG_OLD

def libre_service():
    return LIBRE_SERVICE_NEW if libre_cfg() == LIBRE_CFG_NEW else LIBRE_SERVICE_OLD


# ---------- the data folder itself ----------
def is_data_folder(path):
    """A folder that already holds Body Kaizen data (its settings or targets file)."""
    p = pathlib.Path(path)
    return (p / "settings.yaml").exists() or (p / "targets.yaml").exists()

def needs_data_setup():
    """True until there is a data folder to read: the dashboard then shows the first-run folder setup."""
    return not is_data_folder(DATA)

def init_data_folder(out, template=None):
    """A new data folder from the demo's reference files (targets, settings, markers...), without the demo
    person or any dated data. `out` must be missing or empty."""
    out = pathlib.Path(out).expanduser().resolve()
    if out.exists() and any(out.iterdir()): raise FileExistsError(f"{out} isn't empty")
    template = pathlib.Path(template or CODE / "demo")
    shutil.copytree(template, out, ignore=shutil.ignore_patterns(*DATA_DIRS, "__pycache__", "*.pyc"), dirs_exist_ok=True)
    for d in DATA_DIRS: (out / d).mkdir(exist_ok=True)
    s = out / "settings.yaml"   # forget the demo person: the dashboard asks for your own name, start date and timezone
    if s.exists():
        s.write_text(re.sub(r"(?m)^timezone:.*\n?", "", re.sub(r"(?m)^profile:.*\n(?:[ \t]+.*\n?)*", "", s.read_text(encoding="utf-8"))).lstrip("\n"), encoding="utf-8")
    return out

def save_config(**values):
    """Merge values into ~/.body-kaizen/config.json (private to you: 0600)."""
    c = {**read_config(), **values}
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(c, indent=2) + "\n", encoding="utf-8")
    try: CONFIG.chmod(0o600)
    except OSError: pass
    return c
