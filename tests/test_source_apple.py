"""The Apple Health adapter: HealthKit samples (as the iPhone app sends them) -> Body Kaizen records, and the day-file
fields they become. Demo samples only (tests/applephone.py)."""
import copy, os, pathlib, sys, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("FT_DATA", str(ROOT / "demo"))
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "app"), str(ROOT / "tests")]
import records as R, source_apple as A   # noqa: E402
from applephone import Samples, demo_day, WATCH, PHONE, OTHER   # noqa: E402

DAY = "2026-11-17"


def kind(recs, k): return [r for r in recs if r["kind"] == k]


class Translate(unittest.TestCase):
    def setUp(self):
        self.recs = A.records(demo_day(DAY), DAY)

    def test_every_record_is_one_of_ours(self):
        for r in self.recs: R.check(r)
        self.assertEqual([len(kind(self.recs, k)) for k in ("night", "day", "workout")], [1, 1, 1])

    def test_night(self):
        n = kind(self.recs, "night")[0]
        self.assertEqual(n["asleep_s"], 425 * 60)                     # stages only: the awake spell and in-bed aren't sleep
        self.assertEqual((n["deep_s"], n["light_s"], n["rem_s"], n["awake_s"]), (4200, 17100, 4200, 900))   # core is light
        self.assertEqual((n["start"], n["end"]), ("2026-11-16T23:10", "2026-11-17T06:30"))
        self.assertEqual((n["hrv_ms"], n["hrv_method"]), (50, "sdnn"))   # Apple's HRV is SDNN, and says so
        self.assertEqual((n["respiration"], n["spo2_low"]), (14.5, 93))
        self.assertTrue(50 <= n["overnight_hr"] <= 56)

    def test_day_prefers_the_watch(self):
        d = kind(self.recs, "day")[0]
        # 56 watch buckets of 300; the phone's 250s are dropped where the watch counted, kept for the hour it didn't
        self.assertEqual(d["steps"], 56 * 300 + 4 * 250)
        self.assertEqual((d["energy_active"], d["energy_bmr"], d["energy_total"], d["rhr"]), (672, 1728, 2400, 49))

    def test_workout_and_our_zones(self):
        w = kind(self.recs, "workout")[0]
        self.assertEqual((w["type"], w["mode"], w["start"], w["duration_s"], w["distance_m"]), ("run", "outdoor", "18:00", 2400, 7000.0))
        self.assertEqual((w["hr_avg"], w["hr_max"]), (round(sum(110 + min(i // 30, 40) for i in range(0, 2400, 5)) / 480), 150))
        # bounds at max HR 175: z2 from 105, z3 from 122, z4 from 140 (the Training tab's 60/70/80%)
        self.assertEqual(w["zones_s"], {"z2": 360, "z3": 540, "z4": 1500})
        self.assertEqual((w["kcal_total"], w["kcal_bmr"]), (468, 48))   # Apple's active energy plus the resting part

    def test_to_day(self):
        out = R.to_day(self.recs)
        self.assertEqual(out["recovery"]["sleep"], "7h05m")
        self.assertEqual(out["recovery"]["sleep_stages_min"], {"deep": 70, "light": 285, "rem": 70})
        self.assertEqual(out["recovery"]["hrv_method"], "sdnn")
        s = out["sessions"][0]
        self.assertEqual((s["source"], s["distance_km"], s["time"], s["zones_min"]), ("apple", 7.0, "40:00", {"z2": 6, "z3": 9, "z4": 25}))
        self.assertEqual(out["weight"], {"kg": 78.4, "time": "07:05", "bf_pct": 19.5})
        self.assertEqual(out["vitals"], {"bp": [{"time": "07:30", "sys": 117, "dia": 76}]})
        self.assertEqual(out["fitness"], {"vo2max": 47.3})


class Sleep(unittest.TestCase):
    def test_unspecified_counts_as_asleep_with_no_stage(self):
        S = Samples().sleep([("2026-11-16T23:00", "2026-11-17T07:00", "asleep")], OTHER)
        n = kind(A.records(S.out, DAY), "night")[0]
        self.assertEqual(n["asleep_s"], 8 * 3600)
        self.assertFalse({"deep_s", "light_s", "rem_s"} & set(n))
        self.assertNotIn("sleep_stages_min", R.to_day([n])["recovery"])

    def test_the_watch_beats_another_app(self):
        S = Samples().sleep([("2026-11-16T23:00", "2026-11-17T07:00", "core")], WATCH)
        S.sleep([("2026-11-16T22:00", "2026-11-17T08:00", "asleep")], OTHER)
        self.assertEqual(kind(A.records(S.out, DAY), "night")[0]["asleep_s"], 8 * 3600)

    def test_in_bed_alone_is_no_night(self):
        S = Samples().sleep([("2026-11-16T23:00", "2026-11-17T07:00", "in_bed")], PHONE)
        self.assertEqual(kind(A.records(S.out, DAY), "night"), [])

    def test_a_nap_isnt_the_night(self):
        S = Samples().sleep([("2026-11-16T23:30", "2026-11-17T06:30", "core"), ("2026-11-17T14:00", "2026-11-17T14:40", "core")])
        n = kind(A.records(S.out, DAY), "night")[0]
        self.assertEqual((n["start"], n["asleep_s"]), ("2026-11-16T23:30", 7 * 3600))


class TimeZones(unittest.TestCase):
    def test_days_follow_the_samples_own_zone(self):
        """A night slept in Tokyo is dated by the Tokyo morning, whatever this computer's time zone: it ends at
        06:30 on the 17th there, 21:30 UTC on the 16th."""
        S = Samples("Asia/Tokyo").sleep([("2026-11-16T23:00", "2026-11-17T06:30", "core")])
        S.add("steps", "2026-11-17T08:00", "2026-11-17T08:15", 500, "count")
        recs = A.records(S.out, DAY)
        self.assertEqual(kind(recs, "night")[0]["end"], "2026-11-17T06:30")
        self.assertEqual(kind(recs, "day")[0]["steps"], 500)
        self.assertEqual(A.records(S.out, "2026-11-16"), [])


class Checks(unittest.TestCase):
    def test_bad_samples_are_skipped(self):
        S = Samples()
        good = S.add("steps", "2026-11-17T08:00", "2026-11-17T08:15", 500, "count")
        for bad in ({"unit": "kg"}, {"value": "lots"}, {"value": -5}, {"type": "medications"}, {"start": "2026-11-17T08:00"},
                    {"end": "2026-11-17T07:00:00+00:00"}):
            with self.subTest(bad=bad): self.assertIsNotNone(A.valid({**copy.deepcopy(good), **bad}))
        self.assertIsNone(A.valid(good))
        self.assertIsNotNone(A.valid({**S.add("oxygen_saturation", "2026-11-17T03:00", None, 0.96, "%")}))   # a fraction, not %
        self.assertIsNone(A.valid(S.add("blood_glucose", "2026-11-17T08:00", None, 95, "mg/dL")))

    def test_units_are_converted(self):
        S = Samples()
        S.add("body_mass", "2026-11-17T07:00", None, 172.0, "lb")
        S.add("blood_glucose", "2026-11-17T08:00", None, 90, "mg/dL")
        m = kind(A.records(S.out, DAY), "measurement")
        self.assertEqual((m[0]["weight_kg"], m[1]["glucose_mmol"]), (78.02, 5.0))


class Merge(unittest.TestCase):
    def test_a_weigh_in_logged_another_way_is_kept(self):
        day = {"date": DAY, "weight": {"kg": 78.9, "fasted": True, "time": "06:58", "source": "scale-app"}}
        R.merge_into_day(day, R.to_day(A.records(demo_day(DAY), DAY)), "apple")
        self.assertEqual(day["weight"]["kg"], 78.9)
        empty = {"date": DAY}
        R.merge_into_day(empty, R.to_day(A.records(demo_day(DAY), DAY)), "apple")
        self.assertEqual((empty["weight"]["kg"], empty["weight"]["source"]), (78.4, "apple"))

    def test_blood_pressure_is_added_once(self):
        day = {"date": DAY, "vitals": {"bp": [{"time": "21:30", "sys": 120, "dia": 80}]}}
        mapped = R.to_day(A.records(demo_day(DAY), DAY))
        R.merge_into_day(day, copy.deepcopy(mapped), "apple")
        self.assertEqual([b["time"] for b in day["vitals"]["bp"]], ["07:30", "21:30"])
        once = copy.deepcopy(day)
        self.assertEqual(R.merge_into_day(day, copy.deepcopy(mapped), "apple"), [])
        self.assertEqual(day, once)

    def test_garmin_keeps_what_it_had_first(self):
        day = {"date": DAY}
        R.merge_into_day(day, R.to_day([{"kind": "night", "source": "garmin", "asleep_s": 25000, "hrv_ms": 60, "hrv_method": "rmssd"}]), "garmin")
        R.merge_into_day(day, R.to_day(A.records(demo_day(DAY), DAY)), "apple")
        self.assertEqual((day["recovery"]["source"], day["recovery"]["hrv_ms"]), ("garmin", 60))   # SDNN never lands on RMSSD
        self.assertEqual(day["exercise"][0]["apple_id"], kind(A.records(demo_day(DAY), DAY), "workout")[0]["source_id"])


class Detail(unittest.TestCase):
    def test_detail_for_the_charts(self):
        d = A.detail(demo_day(DAY), DAY)
        self.assertEqual([x[2] for x in d["sleep"][:3]], ["light", "deep", "awake"])
        self.assertEqual(len(d["steps"]), 60)
        self.assertEqual(d["extras"]["steps"], 17800)
        self.assertEqual(len(next(iter(d["workouts"].values()))["samples"]), 480)
        self.assertTrue(all(len(x) == 2 for x in d["hr"]))
        self.assertNotIn("Watch7,3", str(d))           # no device names or sample IDs in what is kept
        self.assertFalse(any(s["uuid"] in str(d) for s in demo_day(DAY) if s["type"] != "workout"))


class Series(unittest.TestCase):
    """app/series.py reads Apple's detail files where Garmin has none (and first, if settings.yaml says so)."""
    def test_series_reads_apple_detail(self):
        import json, tempfile, data, series
        from unittest import mock
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t); p = root / "imports" / "apple" / "2026" / f"{DAY}.json"
            p.parent.mkdir(parents=True); p.write_text(json.dumps(A.detail(demo_day(DAY), DAY)))
            run = next(s for s in demo_day(DAY) if s["type"] == "workout")
            with mock.patch.object(data, "ROOT", root):
                st = series.sleep_stages(DAY)
                self.assertEqual((st[0][2], st[0][0].tzinfo is not None), ("light", True))
                self.assertEqual(sum(v for _, v in series.steps_timeline(DAY)), 17800)
                self.assertEqual(series.day_extras(DAY)["steps"], 17800)
                self.assertIsNone(series.day_extras(DAY)["body_battery_now"])     # Garmin-only figures stay empty
                self.assertGreater(len(series.heart_rate(DAY)), 100)
                self.assertEqual(series.recent_days(), [DAY])
                self.assertEqual(len(series.workout_detail({"apple_id": run["uuid"]}, DAY)["samples"]), 480)
                self.assertIsNone(series.workout_detail({"apple_id": run["uuid"]}))   # without its day it can't be found
                self.assertIsNotNone(series.stamp(DAY))


if __name__ == "__main__":
    unittest.main()
