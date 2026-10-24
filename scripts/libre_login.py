#!/usr/bin/env python3
"""One-time FreeStyle Libre (LibreLinkUp) login.

Your LibreLinkUp password goes into the macOS Keychain (never into the repo); the email, region and
patient id go to ~/.body-kaizen/libre.json. Rerun if you change the password.
"""
import getpass, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bkenv  # noqa: E402
CFG = bkenv.LIBRE_CFG_NEW
SERVICE = bkenv.LIBRE_SERVICE_NEW

def main():
    try:
        import keyring
        from pylibrelinkup import PyLibreLinkUp, APIUrl
        from pylibrelinkup.exceptions import RedirectError
    except ImportError:
        sys.exit("Missing packages. Run: .venv/bin/pip install -r requirements.txt")
    email = input("LibreLinkUp email: ").strip()
    password = getpass.getpass("LibreLinkUp password (saved to your Keychain): ")
    region = APIUrl.AP
    for _ in range(3):
        try:
            c = PyLibreLinkUp(email=email, password=password, api_url=region); c.authenticate(); break
        except RedirectError as e:
            region = e.region; print(f"Your account lives in region {region.name}; retrying there.")
    patients = c.get_patients()
    if not patients:
        sys.exit("Logged in, but no one is sharing with this account. In the LibreLink app: Menu > Connected Apps > LibreLinkUp > Add connection, then accept the invite in LibreLinkUp.")
    p = patients[0]
    keyring.set_password(SERVICE, email, password)
    CFG.parent.mkdir(parents=True, exist_ok=True)
    CFG.write_text(json.dumps({"email": email, "region": region.name, "patient_id": str(p.patient_id)}, indent=2))
    CFG.chmod(0o600)
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import libre_pull
    r = libre_pull.parse_graph(c._get_graph_data_json(p.patient_id))
    if r: print(f"Connected. Latest reading {r[-1][1]:.1f} mmol/L at {r[-1][0]:%H:%M}. The dashboard will pull every 30 minutes.")
    else: print("Connected and saved. No readings yet (the sensor is still warming up); the dashboard will start pulling every 30 minutes once they arrive.")

if __name__ == "__main__":
    main()
