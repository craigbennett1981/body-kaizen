"""The translation layer: every source becomes Body Kaizen records, and records become day-file fields the same way
whatever the source. Runs against the demo data folder."""
import copy, hashlib, json, os, pathlib, sys, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("FT_DATA", str(ROOT / "demo"))
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "app")]
import records as R, source_garmin as G, garmin_map as M   # noqa: E402

DEMO = pathlib.Path(os.environ["FT_DATA"])
RAW = sorted(p for p in (DEMO / "imports" / "garmin").glob("*/*.json") if p.parent.name.isdigit())


class Check(unittest.TestCase):
    def test_good_records_pass(self):
        R.check({"kind": "night", "source": "apple", "asleep_s": 26000, "hrv_ms": 41.5, "hrv_method": "sdnn"})
        R.check({"kind": "workout", "source": "apple", "type": "run", "start": "06:40", "zones_s": {"z2": 1200}})

    def test_bad_records_are_refused(self):
        for bad in ({"kind": "lunch", "source": "x"}, {"kind": "day", "steps": 5},
                    {"kind": "day", "source": "x", "sleep_score": 80},             # a night field on a day
                    {"kind": "workout", "source": "x", "type": "parkour"},
                    {"kind": "night", "source": "x", "hrv_ms": 50},               # HRV without its method
                    {"kind": "day", "source": "x", "steps": "lots"},
                    {"kind": "workout", "source": "x", "type": "run", "zones_s": {"z9": 60}}):
            with self.subTest(bad=bad), self.assertRaises(ValueError): R.check(bad)


class Garmin(unittest.TestCase):
    def test_every_demo_day_translates(self):
        self.assertGreater(len(RAW), 30)
        for p in RAW:
            recs = G.records(json.loads(p.read_text(encoding="utf-8")))
            for r in recs: R.check(r)
            self.assertLessEqual(sum(r["kind"] == "night" for r in recs), 1)
            self.assertLessEqual(sum(r["kind"] == "day" for r in recs), 1)

    def test_output_unchanged(self):
        """Moving Garmin onto the shared layer changed nothing: each demo day maps exactly as before (hashes frozen
        from the code before the layer existed)."""
        want = json.loads((ROOT / "tests" / "fixtures" / "garmin_map_demo.json").read_text())
        got = {p.stem: hashlib.sha256(json.dumps(M.map_day(json.loads(p.read_text(encoding="utf-8"))), default=str).encode()).hexdigest()[:16]
               for p in RAW}
        self.assertEqual({d: got.get(d) for d in want}, want)

    def test_garmin_hrv_is_rmssd(self):
        for p in RAW:
            n = next((r for r in G.records(json.loads(p.read_text(encoding="utf-8"))) if r["kind"] == "night"), {})
            if "hrv_ms" in n: self.assertEqual(n["hrv_method"], "rmssd"); return
        self.skipTest("no HRV in the demo")


class ToDay(unittest.TestCase):
    def test_other_sources_look_the_same(self):
        recs = [{"kind": "night", "source": "apple", "asleep_s": 27000, "deep_s": 4200, "light_s": 15000, "rem_s": 6000,
                 "awake_s": 1800, "start": "2026-11-16T22:40", "end": "2026-11-17T06:10", "hrv_ms": 44, "hrv_method": "sdnn"},
                {"kind": "day", "source": "apple", "steps": 9100, "rhr": 47},
                {"kind": "workout", "source": "apple", "type": "run", "source_id": "A1", "start": "17:05",
                 "duration_s": 2640, "distance_m": 7000, "hr_avg": 139.4}]
        out = R.to_day(recs)
        self.assertEqual(out["recovery"]["sleep"], "7h30m")
        self.assertEqual(out["recovery"]["in_bed"], "22:40–06:10")
        self.assertEqual(out["recovery"]["hrv_method"], "sdnn")      # never mistaken for Garmin's RMSSD
        self.assertEqual(out["steps"], 9100)
        s = out["sessions"][0]
        self.assertEqual((s["apple_id"], s["distance_km"], s["time"], s["hr"]["avg"]), ("A1", 7.0, "44:00", 139))


class Merge(unittest.TestCase):
    def test_one_source_per_section(self):
        day = {"date": "2026-11-17"}
        R.merge_into_day(day, R.to_day([{"kind": "night", "source": "garmin", "asleep_s": 25000}]), "garmin")
        R.merge_into_day(day, R.to_day([{"kind": "night", "source": "apple", "asleep_s": 20000}]), "apple")
        self.assertEqual((day["recovery"]["sleep"], day["recovery"]["source"]), ("6h56m", "garmin"))   # first come keeps it

    def test_hand_entries_are_kept(self):
        day = {"date": "2026-11-17", "exercise": [{"type": "run", "start": "17:00", "effort": "easy", "note": "felt good"}]}
        R.merge_into_day(day, R.to_day([{"kind": "workout", "source": "apple", "type": "run", "source_id": "A1",
                                         "start": "17:05", "duration_s": 1800}]), "apple")
        e = day["exercise"][0]
        self.assertEqual((len(day["exercise"]), e["apple_id"], e["effort"], e["note"]), (1, "A1", "easy", "felt good"))

    def test_merging_twice_changes_nothing(self):
        p = RAW[-1]; mapped = M.map_day(json.loads(p.read_text(encoding="utf-8")))
        day = {"date": p.stem}; M.merge_day(day, copy.deepcopy(mapped)); once = copy.deepcopy(day)
        self.assertEqual(M.merge_day(day, copy.deepcopy(mapped)), [])
        self.assertEqual(day, once)


if __name__ == "__main__":
    unittest.main()
