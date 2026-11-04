#!/usr/bin/env python3
"""FreeStyle Libre (LibreLinkUp) login: once, from the dashboard's Connections page or from here.

Your LibreLinkUp password goes into your computer's keychain (macOS Keychain, Windows Credential Locker or the
Secret Service on Linux), never into the code or data folder; the email, region and patient id go to
~/.body-kaizen/libre.json (private to you). Rerun if you change the password.
"""
import getpass, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bkenv  # noqa: E402
CFG = bkenv.LIBRE_CFG_NEW
SERVICE = bkenv.LIBRE_SERVICE_NEW
NO_SHARE = ("Logged in, but no one is sharing glucose with this account. In the LibreLink app: Menu > Connected Apps > "
            "LibreLinkUp > Add connection, then accept the invite in the LibreLinkUp app and try again.")


class LoginError(Exception):
    """A problem to show the user as it is. Never contains the password."""


def installed():
    try:
        import keyring, pylibrelinkup  # noqa: F401
        return True
    except ImportError:
        return False


def connect(email, password):
    """Log in, find who is sharing with this account, save the password to the keychain and the rest to
    libre.json. Returns {email, region, patient, latest}. Raises LoginError with a message for the user."""
    email = str(email or "").strip(); password = str(password or "")
    if "@" not in email or not password: raise LoginError("Enter your LibreLinkUp email and password.")
    try:
        import keyring
        from pylibrelinkup import PyLibreLinkUp, APIUrl
        from pylibrelinkup import exceptions as X
    except ImportError:
        raise LoginError("The Libre packages aren't installed. Run: pip install 'body-kaizen[libre]' "
                         "(or .venv/bin/pip install -r requirements.txt in a clone), then restart the dashboard.")
    region, c = APIUrl.AP, None
    try:
        for _ in range(3):
            try:
                c = PyLibreLinkUp(email=email, password=password, api_url=region); c.authenticate(); break
            except X.RedirectError as e:
                region = e.region
        else:
            raise LoginError("LibreLinkUp kept redirecting between regions. Try again in a minute.")
        patients = c.get_patients()
    except X.AuthenticationError:
        raise LoginError("LibreLinkUp didn't accept that email and password. Check them in the LibreLinkUp app.")
    except (X.TermsOfUseError, X.PrivacyPolicyError):
        raise LoginError("LibreLinkUp wants you to accept its updated terms. Open the LibreLinkUp app, accept them, then try again.")
    except X.EmailVerificationError:
        raise LoginError("LibreLinkUp wants you to verify your email first. Open the LibreLinkUp app, verify, then try again.")
    except LoginError:
        raise
    except Exception as e:   # network and API errors: the type and status only, never the request
        raise LoginError(f"Couldn't reach LibreLinkUp ({type(e).__name__}). Check your internet connection and try again.")
    if not patients: raise LoginError(NO_SHARE)
    p = patients[0]
    try: keyring.set_password(SERVICE, email, password)
    except Exception as e:
        raise LoginError(f"Logged in, but couldn't save the password to this computer's keychain ({type(e).__name__}).")
    CFG.parent.mkdir(parents=True, exist_ok=True)
    CFG.write_text(json.dumps({"email": email, "region": region.name, "patient_id": str(p.patient_id)}, indent=2), encoding="utf-8")
    try: CFG.chmod(0o600)
    except OSError: pass
    latest = None
    try:
        import libre_pull
        r = libre_pull.parse_graph(c._get_graph_data_json(p.patient_id))
        if r: latest = {"time": r[-1][0].isoformat(timespec="minutes"), "mmol": r[-1][1]}
    except Exception:
        pass   # saved anyway; the scheduled pull reports problems
    name = " ".join(x for x in (getattr(p, "first_name", ""), getattr(p, "last_name", "")) if x).strip()
    return {"email": email, "region": region.name, "patient": name or None, "latest": latest}


def status():
    """What the Connections page shows. No secrets."""
    cfg_path = bkenv.libre_cfg()
    try: cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, ValueError): cfg = None
    try: st = json.loads((bkenv.DATA / "imports" / "libre" / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError): st = {}
    keep = ("last_attempt", "last_success", "last_error", "last_error_at", "last_reading", "latest_mmol")
    return {"installed": installed(), "connected": bool(cfg and cfg.get("email")), "email": (cfg or {}).get("email"),
            "region": (cfg or {}).get("region"), "legacy": cfg_path != CFG and cfg is not None,
            "blocked": bkenv.sync_blocked(), **{k: st.get(k) for k in keep}}


def disconnect():
    """Forget the login: the keychain password and libre.json (new and old locations). Readings already
    pulled stay in your data folder."""
    for path, service in ((bkenv.LIBRE_CFG_NEW, bkenv.LIBRE_SERVICE_NEW), (bkenv.LIBRE_CFG_OLD, bkenv.LIBRE_SERVICE_OLD)):
        try: email = json.loads(path.read_text(encoding="utf-8")).get("email")
        except (OSError, ValueError): continue
        try:
            import keyring
            if email: keyring.delete_password(service, email)
        except Exception:
            pass   # not there, or no keychain: nothing to forget
        path.unlink(missing_ok=True)
    return status()


def main():
    if not installed(): sys.exit("Missing packages. Run: .venv/bin/pip install -r requirements.txt")
    email = input("LibreLinkUp email: ").strip()
    password = getpass.getpass("LibreLinkUp password (saved to your keychain): ")
    try: r = connect(email, password)
    except LoginError as e: sys.exit(str(e))
    if r["region"] != "AP": print(f"Your account lives in region {r['region']}.")
    if r["latest"]: print(f"Connected. Latest reading {r['latest']['mmol']:.1f} mmol/L at {r['latest']['time'][11:16]}. The dashboard will pull every 30 minutes.")
    else: print("Connected and saved. No readings yet (the sensor is still warming up); the dashboard will start pulling every 30 minutes once they arrive.")

if __name__ == "__main__":
    main()
