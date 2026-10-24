"""Your to-do list (todo.yaml): read, and toggle done from the dashboard."""
import datetime as dt, sys, threading, yaml
import data

PATH = data.ROOT / "todo.yaml"

def items():
    return data._jsonable(data._load(PATH) or [])

def toggle(item_id):
    text = PATH.read_text()
    rows = yaml.safe_load(text) or []
    hit = next((r for r in rows if r.get("id") == item_id), None)
    if not hit: return None
    hit["done"] = not hit.get("done")
    if hit["done"]: hit["done_on"] = data.bkenv.today().isoformat()
    else: hit.pop("done_on", None)
    header = "".join(l + "\n" for l in text.splitlines() if l.startswith("#"))
    PATH.write_text(header + yaml.safe_dump(rows, sort_keys=False, allow_unicode=True, default_flow_style=None, width=200))
    msg = f"{'done' if hit['done'] else 'reopened'} {item_id}"
    threading.Thread(target=_commit, args=(msg,), daemon=True).start()  # push can be slow on a hotspot
    return data._jsonable(hit)

def _commit(msg):
    try:
        sys.path.insert(0, str(data.bkenv.CODE / "scripts")); import garmin_pull
        garmin_pull.commit_and_push([PATH], msg, prefix="todo")
    except Exception as e:
        print("todo commit failed:", e, flush=True)
