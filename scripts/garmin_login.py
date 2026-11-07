#!/usr/bin/env python3
"""Garmin Connect login: once, from the dashboard's Connections page or from here. Saves an auto-refreshing token
to ~/.garminconnect (owner-only); your password is used once and never stored. Log in again only if the token
expires (roughly yearly) or the pull reports an auth error.

With two-step verification the login is in two halves: start() signs in and Garmin sends a code; finish() takes
the code. Between them the half-finished login is held in this process's memory only (never on disk), for at most
10 minutes and 5 tries.
"""
import getpass, pathlib, secrets, sys, threading, time

TOKENS = str(pathlib.Path("~/.garminconnect").expanduser())
TOKEN_FILE = pathlib.Path(TOKENS) / "garmin_tokens.json"
PENDING_TTL, MAX_TRIES = 600, 5
_pending = {}            # login_id -> {"api", "state", "at", "tries"}
_lock = threading.Lock()


class LoginError(Exception):
    """A problem to show the user as it is. Never contains the password or the code."""


def installed():
    try:
        import garminconnect  # noqa: F401
        return True
    except ImportError:
        return False


def _lib():
    try:
        from garminconnect import (Garmin, GarminConnectAuthenticationError as Auth, GarminConnectConnectionError as Conn,
                                   GarminConnectTooManyRequestsError as Busy)
    except ImportError:
        raise LoginError("The Garmin library isn't installed. Run: pip install 'body-kaizen[garmin]' "
                         "(or scripts/setup_mac.sh in a clone), then restart the dashboard.")
    return Garmin, Auth, Conn, Busy


def _done(api):
    """Save the token and say who we are."""
    import os
    try:
        os.makedirs(TOKENS, mode=0o700, exist_ok=True); os.chmod(TOKENS, 0o700)   # private before the token lands in it
    except OSError: pass
    try:
        api.client.dump(TOKENS)
    except Exception as e:
        raise LoginError(f"Logged in, but couldn't save the Garmin token to ~/.garminconnect ({type(e).__name__}).")
    for f in pathlib.Path(TOKENS).glob("*.json"):
        try: f.chmod(0o600)
        except OSError: pass
    name = None
    try:
        if not getattr(api, "full_name", None) and hasattr(api, "_load_profile_and_settings"): api._load_profile_and_settings()
        name = api.get_full_name()
    except Exception:
        pass   # the token is saved; the name is only for the message
    return {"connected": True, "name": name}


def start(email, password):
    """Sign in. Returns {"connected": True, "name"} or {"needs_mfa": True, "login_id"}. Raises LoginError."""
    email = str(email or "").strip(); password = str(password or "")
    if "@" not in email or not password: raise LoginError("Enter your Garmin email and password.")
    Garmin, Auth, Conn, Busy = _lib()
    api = Garmin(email=email, password=password, return_on_mfa=True)
    try:
        status, state = api.login()
    except Busy:
        raise LoginError("Garmin is limiting logins from this computer just now. Wait an hour, then try again.")
    except Auth:
        raise LoginError("Garmin didn't accept that email and password. Check them at connect.garmin.com.")
    except Exception as e:   # Conn, network, Cloudflare: the type only, never the request
        raise LoginError(f"Couldn't reach Garmin Connect ({type(e).__name__}). Check your internet connection and try again.")
    finally:
        api.password = None
    if status != "needs_mfa": return _done(api)
    lid = secrets.token_urlsafe(16)
    with _lock:
        _pending.clear()   # one login at a time
        _pending[lid] = {"api": api, "state": state, "at": time.monotonic(), "tries": 0}
    return {"needs_mfa": True, "login_id": lid}


def finish(login_id, code):
    """Finish a two-step login with the code Garmin sent. Raises LoginError; a wrong code can be retried."""
    code = "".join(str(code or "").split())
    with _lock:
        p = _pending.get(str(login_id or ""))
        if p and time.monotonic() - p["at"] > PENDING_TTL: _pending.clear(); p = None
        if not p: raise LoginError("That login has expired. Start again with your email and password.")
        p["tries"] += 1
        if p["tries"] > MAX_TRIES: _pending.clear(); raise LoginError("Too many wrong codes. Start again with your email and password.")
    if not code.isdigit() or not 4 <= len(code) <= 10: raise LoginError("Enter the code from Garmin's email or text: digits only.")
    Garmin, Auth, Conn, Busy = _lib()
    try:
        p["api"].resume_login(p["state"], code)
    except Busy:
        raise LoginError("Garmin is limiting attempts just now. Wait a few minutes, then try the code again.")
    except Auth:
        raise LoginError("That code didn't work. Check it (codes expire after a few minutes) and try again.")
    except Exception as e:
        with _lock: _pending.clear()
        raise LoginError(f"Garmin didn't finish the login ({type(e).__name__}). Start again with your email and password.")
    with _lock: _pending.clear()
    return _done(p["api"])


def cancel():
    with _lock: _pending.clear()


def disconnect():
    """Forget the Garmin token. Data already pulled stays in your data folder."""
    cancel()
    TOKEN_FILE.unlink(missing_ok=True)


def main():
    if not installed(): sys.exit("garminconnect isn't installed in this Python. Run scripts/setup_mac.sh first, then use .venv/bin/python.")
    email = input("Garmin email: ").strip()
    password = getpass.getpass("Garmin password (not stored): ")
    try:
        r = start(email, password)
        while r.get("needs_mfa"):
            try: r = finish(r["login_id"], input("Code from Garmin (email or text): "))
            except LoginError as e:
                print(e)
                if "Start again" in str(e): raise
    except LoginError as e:
        sys.exit(str(e))
    print(f"Logged in{' as ' + r['name'] if r.get('name') else ''}. Token saved to {TOKENS}; the scheduled pull will use it from now on.")

if __name__ == "__main__":
    main()
