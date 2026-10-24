"""Where things live, and the user's settings.

CODE  the Body Kaizen code (this repository)
DATA  your data folder: FT_DATA if set, otherwise the code folder (a single-folder setup)

settings.yaml in the data folder holds your profile (name, start date), timezone and options.
"""
import datetime as dt, os, pathlib, re
import yaml

CODE = pathlib.Path(__file__).resolve().parent.parent
DATA = pathlib.Path(os.environ.get("FT_DATA") or CODE).expanduser().resolve()
SETTINGS = DATA / "settings.yaml"

_cache = {"mtime": None, "data": {}}

def settings():
    try: m = SETTINGS.stat().st_mtime
    except FileNotFoundError: return {}
    if m != _cache["mtime"]:
        _cache["data"] = yaml.safe_load(SETTINGS.read_text()) or {}; _cache["mtime"] = m
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

def save_profile(name, start, timezone):
    """Write profile + timezone into settings.yaml, keeping the rest of the file (and its comments) as it is."""
    txt = SETTINGS.read_text() if SETTINGS.exists() else ""
    txt = re.sub(r"(?m)^profile:.*\n(?:[ \t]+.*\n?)*", "", txt)          # drop an old profile block
    txt = re.sub(r"(?m)^timezone:.*\n?", "", txt)
    block = yaml.safe_dump({"profile": {"name": str(name).strip(), "start_date": str(start)}, "timezone": timezone},
                           sort_keys=False, allow_unicode=True)
    SETTINGS.write_text(block + ("\n" + txt.lstrip("\n") if txt.strip() else ""))
    _cache["mtime"] = None

# Libre login: config file and keychain service. New installs use ~/.body-kaizen; an earlier
# ~/.foodtracker login keeps working (read only) until libre_login.py is run again.
LIBRE_CFG_NEW = pathlib.Path("~/.body-kaizen/libre.json").expanduser()
LIBRE_CFG_OLD = pathlib.Path("~/.foodtracker/libre.json").expanduser()
LIBRE_SERVICE_NEW, LIBRE_SERVICE_OLD = "body-kaizen-librelinkup", "foodtracker-librelinkup"

def libre_cfg():
    return LIBRE_CFG_NEW if LIBRE_CFG_NEW.exists() or not LIBRE_CFG_OLD.exists() else LIBRE_CFG_OLD

def libre_service():
    return LIBRE_SERVICE_NEW if libre_cfg() == LIBRE_CFG_NEW else LIBRE_SERVICE_OLD
