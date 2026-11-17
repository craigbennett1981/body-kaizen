"""The Connections page: log in to LibreLinkUp and Garmin Connect from the dashboard instead of the console, and
pair iPhones running Body Kaizen Sync (app/syncreceiver.py).

Passwords arrive once in a POST that only the dashboard's own page can make (server._write_ok), go straight to the
login code and the computer's keychain, and are never logged, stored in a file or sent back.
"""
import json, os, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import libre_login  # noqa: E402
import garmin_login  # noqa: E402
import bkenv  # noqa: E402
import scheduler  # noqa: E402
import syncreceiver  # noqa: E402


def status():
    return {"libre": {**libre_login.status(), "pulling": scheduler.libre_running()}, "garmin": garmin_status(),
            "iphone": iphone_status()}


# ---------- iPhone (Body Kaizen Sync) ----------

def iphone_status():
    """Paired phones and whether the receiver is listening. Never a token, a pairing code or the key."""
    if not syncreceiver.installed():
        return {"installed": False, "blocked": syncreceiver.why_off(), "devices": [], "listening": False, "port": syncreceiver.PORT}
    return {**syncreceiver.receiver().status(), "blocked": syncreceiver.why_off()}


def iphone_pair(body):
    """Make a pairing code and its QR code, and listen until it's used or expires."""
    off = syncreceiver.why_off()
    if off: return 409, {"error": f"Can't pair here: {off}."}
    try: r = syncreceiver.receiver().start_pairing()
    except OSError as e:
        return 409, {"error": f"Couldn't listen on port {syncreceiver.PORT}: {e.strerror or e}. Is something else using it? "
                              "Set FT_SYNC_PORT to another port and restart the dashboard."}
    import segno
    qr = segno.make(json.dumps(r["payload"], separators=(",", ":")), error="m")
    p = r["payload"]
    return 200, {"qr": qr.svg_data_uri(scale=5, border=2, dark="#000", light="#fff"), "typed": r["typed"],
                 "expires_in": r["expires_in"], "name": p["name"], "port": p["port"], "addrs": p["addrs"], **status()}


def iphone_cancel():
    if syncreceiver.installed(): syncreceiver.receiver().cancel_pairing()
    return 200, status()


def iphone_remove(body):
    if not syncreceiver.installed(): return 409, {"error": "The iPhone packages aren't installed."}
    if not syncreceiver.receiver().remove(str(body.get("id") or "")): return 404, {"error": "No such phone."}
    return 200, status()


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
