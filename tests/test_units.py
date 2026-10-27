"""Unit tests for the pieces most likely to break quietly: the food matcher, brand eras, pace windows and the
lift planner. They run against the demo data folder (FT_DATA must point at demo/; CI sets it)."""
import datetime as dt, os, pathlib, sys, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("FT_DATA", str(ROOT / "demo"))
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "app")]
import nutrition as N   # noqa: E402
import pace, planner, muscles   # noqa: E402


class FoodMatcher(unittest.TestCase):
    def test_weight_and_item(self):
        comps, problems = N.resolve("165g chicken breast", "2026-10-01")
        self.assertEqual(problems, [])
        self.assertEqual((comps[0]["item"], comps[0]["g"]), ("chicken-breast", 165))

    def test_combined_line_splits(self):
        comps, _ = N.resolve("155g yogurt + 90g soaked chia seeds", "2026-10-01")
        self.assertEqual([c["item"] for c in comps], ["yogurt", "chia-soaked"])

    def test_macros_scale_with_weight(self):
        a = N.macros({"item": "rice", "g": 100}); b = N.macros({"item": "rice", "g": 200})
        self.assertAlmostEqual(b["k"], 2 * a["k"])

    def test_unknown_food_is_reported(self):
        _, problems = N.resolve("200g zzzzunknownfood", "2026-10-01")
        self.assertTrue(problems)


class Eras(unittest.TestCase):
    def test_rules_pick_by_date_and_chain(self):
        old = N.ERAS
        N.ERAS = {"milk-lowfat": [{"from": "2026-10-20", "use": "milk-whole"}], "milk-whole": [{"from": "2026-11-01", "use": "milk-tea"}]}
        try:
            self.assertEqual(N.era_key("milk-lowfat", "2026-10-19"), "milk-lowfat")
            self.assertEqual(N.era_key("milk-lowfat", "2026-10-25"), "milk-whole")
            self.assertEqual(N.era_key("milk-lowfat", "2026-11-02"), "milk-tea")
        finally:
            N.ERAS = old


class Pace(unittest.TestCase):
    def test_windows_and_expected_share(self):
        last = sorted((pathlib.Path(os.environ["FT_DATA"]) / "days").rglob("*.yaml"))[-1].stem
        p = pace.build(last, "12:00")              # a finished day: judged against the whole target
        self.assertEqual(len(p["windows"]), 3)
        prot = p["macros"]["protein_g"]
        self.assertAlmostEqual(prot["expected"], 150, delta=0.5)
        self.assertAlmostEqual(sum(w["plan"] for w in prot["windows"]), 150, delta=1)   # the windows split the day's target


class Planner(unittest.TestCase):
    def test_double_progression(self):
        info = {"rep_range": [8, 12], "working_sets": 3}
        cat = {"lifts": {"row": {"increment_kg": 4.5}}}
        hit = planner.next_target("row", [("2026-10-01", [{"kg": 31.8, "reps": 12}] * 3)], cat, info)
        self.assertIn("36.3 kg", hit["target"])                          # all sets at the top: add a step, back to 8
        build = planner.next_target("row", [("2026-10-01", [{"kg": 31.8, "reps": 9}] * 3)], cat, info)
        self.assertIn("3 × 10 at 31.8 kg", build["target"])            # otherwise add a rep

    def test_bodyweight(self):
        info = {"rep_range": [6, 12], "working_sets": 3}
        t = planner.next_target("chin-up", [("2026-10-01", [{"kg": 0, "reps": 8}, {"kg": 0, "reps": 7}, {"kg": 0, "reps": 6}])], {"lifts": {}}, info)
        self.assertIn("21 total reps", t["target"])


if __name__ == "__main__":
    unittest.main()


class MuscleMap(unittest.TestCase):
    def test_tags_map_to_regions(self):
        self.assertEqual(muscles.regions_for("front-delts"), ["front-delts"])
        self.assertEqual(sorted(muscles.regions_for("shoulders")), ["front-delts", "rear-delts"])
        self.assertEqual(muscles.regions_for("not-a-muscle"), [])

    def test_week_counts_sets_and_lists_lifts(self):
        m = muscles.build(7, "2026-10-23")
        self.assertEqual(set(m["regions"]), set(muscles.REGIONS))
        trained = [r for r in m["regions"].values() if r["sets"]]
        self.assertTrue(trained)
        for r in trained: self.assertTrue(r["lifts"], "every shaded muscle names the lifts behind it")

    def test_cardio_counts_by_minutes(self):
        self.assertEqual(muscles._minutes({"time": "25:20"}), 25 + 20 / 60)
        self.assertEqual(muscles._minutes({"duration_min": 40}), 40.0)

