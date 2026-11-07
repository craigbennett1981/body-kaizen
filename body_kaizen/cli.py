"""The `body-kaizen` command: the dashboard, the demo, a new data folder, and the sync/compute scripts.

Every subcommand runs the same file you would run from a clone (app/server.py, scripts/compute.py, ...),
so the installed package and a git checkout behave the same way.
"""
import argparse, os, pathlib, re, runpy, shutil, signal, socket, sys, tempfile, webbrowser

from . import __version__

HERE = pathlib.Path(__file__).resolve().parent
CODE = HERE if (HERE / "app").is_dir() else HERE.parent   # installed: app/ sits inside the package; clone: beside it

SCRIPTS = {   # subcommand -> (file, help)
    "compute": ("scripts/compute.py", "recompute food totals for every day, or the dates given"),
    "garmin-login": ("scripts/garmin_login.py", "log in to Garmin Connect once (needs the [garmin] extra)"),
    "garmin-pull": ("scripts/garmin_pull.py", "pull recent days from Garmin Connect"),
    "libre-login": ("scripts/libre_login.py", "log in to LibreLinkUp once (needs the [libre] extra)"),
    "libre-pull": ("scripts/libre_pull.py", "pull recent glucose readings from LibreLinkUp"),
    "hevy-import": ("scripts/hevy_import.py", "import a Hevy workout CSV export"),
}
DATA_DIRS = ("days", "imports", "measurements")   # the dated part of a data folder; the rest is reference files

def _run(rel, args):
    """Run one of the code's scripts as if from the command line."""
    path = CODE / rel
    sys.argv = [str(path), *args]
    runpy.run_path(str(path), run_name="__main__")

def _bkenv():
    sys.path.insert(0, str(CODE / "scripts")); import bkenv
    return bkenv

def _port(args):
    return int(getattr(args, "port", None) or os.environ.get("FT_PORT", "8765"))

def _up(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5): return True
    except OSError: return False

def _open(args):
    """Open the running dashboard in your browser, signed in. Once per browser: the cookie it sets lasts a year."""
    port = _port(args)
    if args.print:   # for a browser on another profile, or to copy by hand
        return print(_bkenv().signin_url(port))
    if not _up(port):
        sys.exit(f"The dashboard isn't running on port {port}. Start it with: body-kaizen")
    if not webbrowser.open(_bkenv().signin_url(port)):
        print("Couldn't open a browser. Run `body-kaizen open --print` and open the link it prints.")

def _serve(args):
    if args.data: os.environ["FT_DATA"] = str(pathlib.Path(args.data).expanduser())
    if args.port: os.environ["FT_PORT"] = str(args.port)
    if getattr(args, "no_browser", False): os.environ["FT_NO_BROWSER"] = "1"   # the server opens it otherwise
    # With no data folder yet the dashboard opens on its first-run setup, where you choose or create one.
    _run("app/server.py", [])

def _demo(args):
    """Serve a copy of the bundled demo data, so nothing is written inside the installed package."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="body-kaizen-demo-"))
    shutil.copytree(CODE / "demo", tmp, dirs_exist_ok=True)
    os.environ.update(FT_DATA=str(tmp), FT_NO_SYNC="1")
    if args.port: os.environ["FT_PORT"] = str(args.port)
    print(f"Demo data copied to {tmp} (made-up data for a fictional person).", flush=True)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))   # clean up on kill as well as Ctrl+C
    try: _run("app/server.py", [])
    except KeyboardInterrupt: pass
    finally: shutil.rmtree(tmp, ignore_errors=True)

def _init(args):
    """A new data folder: the demo's reference files (targets, settings, markers...), without the demo person."""
    out = pathlib.Path(args.dir).expanduser().resolve()
    if out.exists() and any(out.iterdir()):
        sys.exit(f"{out} already exists and isn't empty: choose another folder.")
    _bkenv().init_data_folder(out, CODE / "demo")   # the same as the dashboard's setup: private folder, .gitignore, no Sam
    print(f"""Created {out}

Next:
  1. Set your targets in targets.yaml and your defaults in settings.yaml.
  2. Keep the folder in a PRIVATE git repository (or none):  cd {out} && git init
  3. Start the dashboard:  body-kaizen{'' if out == pathlib.Path('~/body-kaizen-data').expanduser() else f' --data {out}'}""")

def main(argv=None):
    ap = argparse.ArgumentParser(prog="body-kaizen", description="A private, local dashboard for your health data.")
    ap.add_argument("--version", action="version", version=f"body-kaizen {__version__}")
    sub = ap.add_subparsers(dest="cmd", metavar="COMMAND")
    for p in (ap, sub.add_parser("serve", help="start the dashboard (the default)")):
        p.add_argument("--data", metavar="DIR", help="your data folder (default: FT_DATA, else ~/body-kaizen-data)")
        p.add_argument("--port", type=int, help="port to listen on (default 8765)")
        p.add_argument("--no-browser", action="store_true", help="don't open the browser")
    p = sub.add_parser("open", help="open the running dashboard in your browser, signed in")
    p.add_argument("--port", type=int, help="the dashboard's port (default 8765)")
    p.add_argument("--print", action="store_true", help="print the sign-in link instead of opening it")
    p = sub.add_parser("demo", help="start the dashboard on made-up demo data")
    p.add_argument("--port", type=int, help="port to listen on (default 8765)")
    p = sub.add_parser("init", help="create a new data folder")
    p.add_argument("dir", nargs="?", default="~/body-kaizen-data", help="where (default ~/body-kaizen-data)")
    for name, (_, help) in SCRIPTS.items():
        sub.add_parser(name, help=help, add_help=False)   # the script parses its own arguments, --help included

    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in SCRIPTS:
        return _run(SCRIPTS[argv[0]][0], argv[1:])
    args = ap.parse_args(argv)
    {"demo": _demo, "init": _init, "open": _open}.get(args.cmd, _serve)(args)
