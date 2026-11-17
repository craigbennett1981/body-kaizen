"""Map raw Garmin Connect JSON (as saved by garmin_pull.py) into the day-file schema, and merge.

Kept separate from the network code so it can be tested against saved raw files and fixed
without re-pulling: rerun `garmin_pull.py --remap` after changing anything here.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bkenv  # noqa: E402

import records as R           # noqa: E402
import source_garmin as G     # noqa: E402

ACTIVITY_TYPES = G.ACTIVITY_TYPES
KEEP = R.KEEP


def map_day(raw):
    """raw = {"summary":..., "sleep":..., "hrv":..., "activities":[...]} -> {"steps", "energy", "recovery", "sessions"}

    Goes through the shared translation layer: Garmin -> records (source_garmin.py) -> day-file fields (records.py)."""
    return R.to_day(G.records(raw))


def merge_day(day, mapped):
    """Merge mapped Garmin data into a loaded day dict in place. Returns a short list of what changed."""
    return R.merge_into_day(day, mapped, "garmin")
