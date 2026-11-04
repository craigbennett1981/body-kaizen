"""The Connections page: log in to LibreLinkUp (and, next, Garmin) from the dashboard instead of the console.

Passwords arrive once in a POST that only the dashboard's own page can make (server._write_ok), go straight to the
login code and the computer's keychain, and are never logged, stored in a file or sent back.
"""
import os, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import libre_login  # noqa: E402
import scheduler  # noqa: E402


def status():
    return {"libre": {**libre_login.status(), "pulling": scheduler.libre_running()}}


def libre_connect(body):
    try: res = libre_login.connect(body.get("email"), body.get("password"))
    except libre_login.LoginError as e: return 400, {"error": str(e)}
    pulled = _pull()
    return 200, {**status(), "connected_as": res, "pull_started": pulled}


def libre_disconnect():
    libre_login.disconnect()
    return 200, status()


def libre_pull():
    st = libre_login.status()
    if not st["connected"]: return 409, {"error": "Connect LibreLinkUp first."}
    if st["blocked"]: return 409, {"error": f"Sync is off: {st['blocked']}"}
    return 202, {**status(), "pull_started": _pull()}


def _pull():
    if os.environ.get("FT_NO_SYNC"): return False   # tests and the demo never reach LibreLinkUp
    return scheduler.libre_pull_now()
