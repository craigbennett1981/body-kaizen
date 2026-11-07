"""Weights and distances in the units the person chose (settings.yaml `units`: metric, the default, or imperial),
for text the server writes: advice, plans, the weekly summary, the day's notes. The files themselves stay metric."""
import data

LB, MI = 2.20462, 0.621371


def imperial():
    return data.bkenv.units() == "imperial"


def _n(v, d):
    v = round(v, d); return int(v) if float(v).is_integer() else v


def kg(v, d=1):
    """A body or lift weight with its unit: 79.1 kg, or 174.4 lb."""
    if v is None: return "–"
    return f"{_n(v * LB, d)} lb" if imperial() else f"{_n(v, d)} kg"


def km(v, d=2):
    """A distance with its unit: 7.21 km, or 4.48 mi."""
    if v is None: return "–"
    return f"{_n(v * MI, d)} mi" if imperial() else f"{_n(v, d)} km"
