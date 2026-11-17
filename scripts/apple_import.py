"""Apple Health -> day files: translate the days the iPhone's uploads touched, from the raw cache.

For each day: the adapter (source_apple.py) turns the cached samples into records, the shared layer (records.py)
merges them into the day file exactly as it does Garmin's, and the detail the charts draw (sleep stages, per-minute
heart rate, 15-minute steps, workout traces) goes to imports/apple/YYYY/YYYY-MM-DD.json for app/series.py.

The receiver runs this a little after uploads stop. By hand, to re-apply a translation fix to what is still cached:

    FT_DATA=~/body-kaizen-data python scripts/apple_import.py --remap
"""
import argparse, datetime as dt, json, pathlib, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import yaml               # noqa: E402
import bkenv              # noqa: E402
import records as R       # noqa: E402
import source_apple as A  # noqa: E402
import apple_cache as C   # noqa: E402


def detail_path(root, day): return pathlib.Path(root) / "imports" / "apple" / day[:4] / f"{day}.json"


def day_path(root, day): return pathlib.Path(root) / "days" / day[:4] / f"{day}.yaml"


def max_hr(root):
    """The Training tab's max heart rate: the higher of 175 and the highest session max on record."""
    best = 175
    for p in (pathlib.Path(root) / "days").glob("*/*.yaml"):
        try: d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception: continue
        for e in d.get("exercise") or []:
            m = (e.get("hr") or {}).get("max") if isinstance(e, dict) else None
            if isinstance(m, (int, float)) and m > best: best = m
    return best


def _write_detail(root, day, new, gone=()):
    """Write the day's detail. Parts the cache has nothing for keep what was there (the cache only holds 14 days, so a
    late sample for an older day mustn't wipe its charts); workouts deleted on the phone go."""
    p = detail_path(root, day)
    try: old = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError): old = {}
    out = {**old, **new}
    if "workouts" in old or "workouts" in new:
        out["workouts"] = {k: v for k, v in {**old.get("workouts", {}), **new.get("workouts", {})}.items() if k not in gone}
        if not out["workouts"]: out.pop("workouts")
    if out == old: return False
    bkenv.private_dir(p.parent)
    p.write_text(json.dumps(out, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    return True


def _drop_workouts(day, gone):
    """Sessions whose Apple workout was deleted on the phone: removed, unless something was logged on them by hand,
    in which case only the Apple link goes."""
    changes = []
    for e in list(day.get("exercise") or []):
        if e.get("apple_id") not in gone: continue
        if any(e.get(k) for k in R.KEEP): e.pop("apple_id", None); e.pop("source", None) if e.get("source") == "apple" else None
        else: day["exercise"].remove(e)
        changes.append(f"{e.get('type')} removed")
    if "exercise" in day and not day["exercise"]: day.pop("exercise")
    return changes


def translate(root, days, gone=(), mhr=None, process=True):
    """Re-translate local `days` (YYYY-MM-DD) from the cache into day files and detail files.
    `gone`: workout UUIDs deleted on the phone. -> ([changed paths], [summary lines])"""
    root = pathlib.Path(root); gone = set(gone)
    mhr = mhr or max_hr(root)
    touched, summary = [], []
    for day in sorted(set(map(str, days))):
        samples = C.around(root, day)
        recs = A.records(samples, day, mhr)
        if _write_detail(root, day, A.detail(samples, day), gone): touched.append(detail_path(root, day))
        p = day_path(root, day)
        if not recs and not (gone and p.exists()): continue
        d = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {
            "date": dt.date.fromisoformat(day), "status": "unlogged", "meals": {"breakfast": [], "lunch": [], "dinner": [], "snacks": []}}
        changes = _drop_workouts(d, gone) + R.merge_into_day(d, R.to_day(recs), A.SOURCE)
        if changes or not p.exists():
            bkenv.private_dir(p.parent)
            p.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True, default_flow_style=None, width=200), encoding="utf-8")
            if process:
                import compute
                compute.process(p)
            touched.append(p)
            if changes: summary.append(f"{dt.date.fromisoformat(day).strftime('%d %b')} {', '.join(changes)}")
    return touched, summary


def commit(root, paths, summary):
    """Commit the changed day and detail files to the data folder's git repository, as the Garmin pull does
    (settings.yaml git.auto_commit, on by default; never pushed from here). Never in demo data or the code folder."""
    root = pathlib.Path(root)
    if not paths or not bkenv.git_options()["auto_commit"] or bkenv.is_demo(root) or bkenv.in_code_repo(root): return False
    exe = bkenv.git_exe()
    if not exe: return False
    run = lambda *a: subprocess.run([exe, *a], cwd=root, capture_output=True, text=True, timeout=90)
    if run("rev-parse", "--is-inside-work-tree").returncode != 0: return False
    rel = [str(pathlib.Path(p).relative_to(root)) for p in paths]
    run("add", "--", *rel)
    if run("diff", "--cached", "--quiet").returncode == 0: return False
    return run("commit", "-m", f"apple: {'; '.join(summary) or 'detail'}"[:2000], "--", *rel).returncode == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--remap", action="store_true", help="re-translate every day still in the cache")
    ap.add_argument("--prune", action="store_true", help="delete cached rows older than 14 days")
    ap.add_argument("--no-git", action="store_true")
    a = ap.parse_args()
    root = bkenv.DATA
    if bkenv.sync_blocked(): sys.exit(f"Not translating: {bkenv.sync_blocked()}")
    if a.prune: print(f"pruned {C.prune(root)} cached samples")
    days = C.cached_days(root) if a.remap else C.take_dirty(root)
    paths, summary = translate(root, days)
    for s in summary: print(s)
    if not a.no_git: commit(root, paths, summary)
    print(f"{len(days)} days translated, {len(paths)} files changed")


if __name__ == "__main__":
    main()
