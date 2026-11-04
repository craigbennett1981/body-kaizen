"""The Connections page: log in to LibreLinkUp and Garmin Connect from the dashboard instead of the console.

Passwords arrive once in a POST that only the dashboard's own page can make (server._write_ok), go straight to the
login code and the computer's keychain, and are never logged, stored in a file or sent back.
"""
import os, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import libre_login  # noqa: E402
import garmin_login  # noqa: E402
import bkenv  # noqa: E402
import scheduler  # noqa: E402


def status():
    return {"libre": {**libre_login.status(), "pulling": scheduler.libre_running()}, "garmin": garmin_status()}


def garmin_status():
    st = scheduler._state()
    keep = ("last_success", "last_error", "last_error_at", "last_attempt")
    return {"installed": garmin_login.installed(), "connected": garmin_login.TOKEN_FILE.exists(),
            "pulling": scheduler._running, "blocked": bkenv.sync_blocked(), **{k: st.get(k) for k in keep}}


def garmin_connect(body):
    try:
        res = (garmin_login.finish(body.get("login_id"), body.get("code")) if body.get("login_id") else
               garmin_login.start(body.get("email"), body.get("password")))
    except garmin_login.LoginError as e:
        return 400, {"error": str(e)}
    if res.get("needs_mfa"): return 200, {"needs_mfa": True, "login_id": res["login_id"]}
    pulled = False if os.environ.get("FT_NO_SYNC") or bkenv.sync_blocked() else scheduler.run_pull_async()
    return 200, {**status(), "connected_as": res, "pull_started": pulled}


def garmin_disconnect():
    garmin_login.disconnect()
    return 200, status()


def garmin_pull():
    st = garmin_status()
    if not st["connected"]: return 409, {"error": "Connect Garmin first."}
    if st["blocked"]: return 409, {"error": f"Sync is off: {st['blocked']}"}
    if os.environ.get("FT_NO_SYNC"): return 202, {**status(), "pull_started": False}
    return 202, {**status(), "pull_started": scheduler.run_pull_async()}


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
