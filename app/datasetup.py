"""First-run setup of the data folder, from the dashboard: where your personal data lives.

The dashboard starts in setup mode when there is no data folder yet (bkenv.needs_data_setup). The page offers a
default location, the computer's own folder picker, or a typed path; this module checks the choice, creates the
folder from the starter files (optionally as a git repository), saves the choice in ~/.body-kaizen/config.json
and restarts the server on it. FT_DATA, when set, still overrides the saved choice.
"""
import os, pathlib, platform, shutil, subprocess, sys, threading
import bkenv

DEFAULT = pathlib.Path("~/body-kaizen-data").expanduser()
PICK_TIMEOUT = 300   # seconds the folder picker may stay open


def _home(p):
    try: return "~/" + pathlib.Path(p).relative_to(pathlib.Path.home()).as_posix()
    except ValueError: return str(p)


def info():
    return {"needs_setup": bkenv.needs_data_setup(), "current": str(bkenv.DATA), "suggested": str(DEFAULT),
            "suggested_short": _home(DEFAULT), "picker": _picker() is not None, "git": shutil.which("git") is not None,
            "env_override": bool(os.environ.get("FT_DATA"))}


def _picker():
    """The command that opens this computer's own folder picker and prints the chosen path, or None."""
    prompt = "Choose where to keep your Body Kaizen data"
    sysname = platform.system()
    if sysname == "Darwin" and shutil.which("osascript"):
        return ["osascript", "-e", f'POSIX path of (choose folder with prompt "{prompt}")']
    if sysname == "Windows" and shutil.which("powershell"):
        return ["powershell", "-NoProfile", "-STA", "-Command",   # -STA: the Windows Forms dialog needs it
                "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "   # folder names outside the code page
                "Add-Type -AssemblyName System.Windows.Forms; $f = New-Object System.Windows.Forms.FolderBrowserDialog; "
                f"$f.Description = '{prompt}'; $f.ShowNewFolderButton = $true; "
                "$top = New-Object System.Windows.Forms.Form -Property @{TopMost = $true}; "   # in front of the browser
                "if ($f.ShowDialog($top) -eq 'OK') { $f.SelectedPath }"]
    for cmd in (["zenity", "--file-selection", "--directory", f"--title={prompt}"],
                ["kdialog", "--getexistingdirectory", str(pathlib.Path.home()), "--title", prompt]):
        if shutil.which(cmd[0]): return cmd
    return None


def pick():
    """Open the folder picker on this computer. {'path': ...}, {'cancelled': True} or {'error': ...}."""
    cmd = _picker()
    if not cmd: return {"error": "This computer has no folder picker the dashboard can open. Type the path instead."}
    try: r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=PICK_TIMEOUT)
    except subprocess.TimeoutExpired: return {"cancelled": True}
    path = r.stdout.strip()
    if r.returncode != 0 or not path: return {"cancelled": True}
    return {"path": str(pathlib.Path(path).expanduser().resolve())}


def check(path):
    """What would happen if this folder were chosen. Never creates anything."""
    raw = str(path or "").strip()
    if not raw: return {"ok": False, "error": "Choose or type a folder."}
    raw = os.path.expanduser(raw)
    if not os.path.isabs(raw): return {"ok": False, "error": "Use a full path, for example ~/body-kaizen-data."}
    # Normalise before touching the disk, and only ever look inside your home folder. realpath also gives Windows
    # paths their real case (c:\\users\\sam -> C:\\Users\\Sam), so the comparison isn't fooled by how it was typed.
    home = os.path.realpath(os.path.expanduser("~"))
    full = os.path.realpath(raw)
    if not full.startswith(home + os.sep):
        return {"ok": False, "error": "Choose a folder inside your home folder (~)."}
    p = pathlib.Path(full)
    out = {"path": str(p), "short": _home(p)}
    if bkenv.inside(p, bkenv.CODE):   # also ~/Repos/Body-Kaizen on macOS, where case doesn't matter
        return {**out, "ok": False, "error": "That's inside the Body Kaizen code folder. Keep your data separate, "
                "so it can never be published with the code."}
    if bkenv.is_data_folder(p):
        return {**out, "ok": True, "mode": "existing", "message": "This already holds Body Kaizen data: the dashboard will use it."}
    if p.exists() and not p.is_dir(): return {**out, "ok": False, "error": "That's a file, not a folder."}
    if p.exists() and any(p.iterdir()):
        sub = p / "Body Kaizen data"
        return {**out, "ok": False, "error": "That folder already has other files in it.",
                "suggest": str(sub), "suggest_short": _home(sub)}
    parent = p if p.exists() else next((a for a in p.parents if a.exists()), None)
    if parent is None or not os.access(parent, os.W_OK):
        return {**out, "ok": False, "error": "You can't write to that location."}
    return {**out, "ok": True, "mode": "new", "message": "A new data folder will be created here with starter targets and settings."}


def create(body):
    """Create or adopt the chosen folder, save the choice and restart the server on it."""
    c = check(body.get("path"))
    if not c.get("ok"): return c
    p = pathlib.Path(c["path"])
    storage = body.get("storage") or ("git" if body.get("git") else "files")   # `git: true` from older pages
    if storage not in STORAGE: return {**c, "ok": False, "error": "Choose how your data is kept."}
    if c["mode"] == "new":
        bkenv.init_data_folder(p)
        if storage != "files" and shutil.which("git") and not (p / ".git").exists():
            if subprocess.run(["git", "init", "-q", "-b", "main"], cwd=p, check=False).returncode:   # git older than 2.28
                subprocess.run(["git", "init", "-q"], cwd=p, check=False)
        if storage == "github": _github_todo(p)
    bkenv.save_config(data_dir=str(p))
    threading.Timer(0.6, _restart, (p,)).start()   # after the reply has gone out
    return {**c, "ok": True, "restarting": True, "git": bool((p / ".git").exists()), "storage": storage if c["mode"] == "new" else None}


STORAGE = ("files", "git", "github")
GITHUB_DOC = "https://github.com/craigbennett1981/body-kaizen/blob/main/docs/data-folder.md#a-private-backup-on-github"


def _github_todo(p):
    """The GitHub backup is finished by hand (an account, a private repository, one push): put the steps on the
    to-do list the Day page shows, so they aren't lost once setup is over."""
    item = ("- {id: github-backup, area: setup, priority: high, done: false, title: Back up your data to a private GitHub repository, "
            f"detail: 'Create a private repository on github.com (no README), then in your data folder: git remote add origin <its URL>, "
            f"git push -u origin main. Steps: {GITHUB_DOC}'}}\n")
    t = p / "todo.yaml"
    head = "# Things to do. Shown on the Day view; tick to mark done.\n" if not t.exists() else ""
    with open(t, "a", encoding="utf-8") as fh: fh.write(head + item)


def _restart(p):
    """Start this same server again, now on the chosen folder. On macOS and Linux the process replaces itself
    (same process id, so launchd or systemd keep tracking it). Windows has no such call: start a new server,
    which waits for this one to let go of the port, and exit."""
    os.environ["FT_DATA"] = str(p); os.environ["BK_RESTARTED"] = "1"
    sys.stdout.flush(); sys.stderr.flush()
    argv = [sys.executable, *sys.orig_argv[1:]]
    if os.name == "nt":
        subprocess.Popen(argv, env=os.environ.copy())
        os._exit(0)
    os.execv(sys.executable, argv)
