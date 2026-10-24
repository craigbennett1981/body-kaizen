#!/usr/bin/env python3
"""One-time Garmin Connect login. Saves an auto-refreshing token to ~/.garminconnect.

Your password is used once and never stored. Rerun this only if the token expires
(roughly yearly) or the pull reports an auth error.
"""
import getpass, pathlib, sys

TOKENS = str(pathlib.Path("~/.garminconnect").expanduser())

def main():
    try:
        from garminconnect import Garmin
    except ImportError:
        sys.exit("garminconnect isn't installed in this Python. Run scripts/setup_mac.sh first, then use .venv/bin/python.")
    email = input("Garmin email: ").strip()
    password = getpass.getpass("Garmin password (not stored): ")
    api = Garmin(email=email, password=password, prompt_mfa=lambda: input("MFA code from your phone/email: ").strip())
    api.login(TOKENS)
    name = api.get_full_name() if hasattr(api, "get_full_name") else "ok"
    print(f"Logged in as {name}. Token saved to {TOKENS} — the scheduled pull will use it from now on.")

if __name__ == "__main__":
    main()
