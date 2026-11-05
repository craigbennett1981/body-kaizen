"""Unit tests for the pieces most likely to break quietly: the food matcher, brand eras, pace windows and the
lift planner. They run against the demo data folder (FT_DATA must point at demo/; CI sets it)."""
import datetime as dt, os, pathlib, subprocess, sys, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("FT_DATA", str(ROOT / "demo"))
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "app")]
import nutrition as N   # noqa: E402
import pace, planner, muscles, workouts, thresholds, energybalance   # noqa: E402
import bkenv, garmin_pull, scheduler   # noqa: E402


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


class CircuitMatching(unittest.TestCase):
    SESSION = {"circuits": [["smith-squat", "chin-up"], ["leg-curl"]],
               "lifts": [{"ex": "smith-squat", "sets": ["60x10", "70x10"]}, {"ex": "chin-up", "sets": ["0x8", "0x6"]},
                         {"ex": "leg-curl", "sets": ["77x10", "77x10"]}]}

    def test_set_order_loops_each_circuit(self):
        blocks, by_circuit = workouts._set_order(self.SESSION)
        self.assertTrue(by_circuit)
        self.assertEqual([[(x["ex"], x["set"]) for x in b] for b in blocks],
                         [[("smith-squat", 1), ("chin-up", 1), ("smith-squat", 2), ("chin-up", 2)], [("leg-curl", 1), ("leg-curl", 2)]])

    def test_extra_peak_dropped_and_blocks_split_at_the_gap(self):
        blocks, _ = workouts._set_order(self.SESSION)
        # a warm-up bump, four sets of the first circuit, a long walk to the next machine, then two sets
        efforts = [[0.5, 100], [2, 120], [3, 125], [4, 122], [5, 128], [9, 118], [10.5, 121]]
        labels, fit = workouts._label_efforts(efforts, blocks)
        self.assertIsNone(labels[0])
        self.assertEqual([(l["ex"], l["set"]) for l in labels[1:]],
                         [("smith-squat", 1), ("chin-up", 1), ("smith-squat", 2), ("chin-up", 2), ("leg-curl", 1), ("leg-curl", 2)])
        self.assertEqual((fit["matched"], fit["sets"]), (6, 6))



class DemoNeverSyncs(unittest.TestCase):
    """Running the dashboard on demo data must never pull or commit real health data into the code repo."""
    def test_demo_and_folders_inside_the_repo_are_recognised(self):
        self.assertTrue(bkenv.is_demo(ROOT / "demo"))
        self.assertTrue(bkenv.in_code_repo(ROOT / "demo"))
        self.assertTrue(bkenv.in_code_repo(ROOT / "demo" / "demo"))
        self.assertFalse(bkenv.in_code_repo(ROOT))   # the single-folder setup may commit
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            self.assertFalse(bkenv.in_code_repo(d))
            (d / "settings.yaml").write_text("profile: {name: Alex, start_date: '2026-01-01'}\n")
            self.assertFalse(bkenv.is_demo(d))
            (d / "settings.yaml").write_text("profile: {name: Sam (demo), start_date: '2026-01-01'}\n")
            self.assertTrue(bkenv.is_demo(d))   # a copy of demo/ that hasn't been made your own yet

    def test_sync_is_blocked_on_demo_data(self):
        self.assertEqual(bkenv.DATA, (ROOT / "demo").resolve())
        self.assertTrue(bkenv.sync_blocked())
        self.assertFalse(scheduler.start())
        self.assertTrue(scheduler.status()["blocked"])
        self.assertFalse(scheduler.status()["ready"])
        real_run = subprocess.run
        def no_run(*a, **k): raise AssertionError("a sync subprocess was started on demo data")
        subprocess.run = no_run
        try:
            self.assertFalse(scheduler.run_pull())
        finally:
            subprocess.run = real_run

    def test_no_commit_inside_the_code_repo(self):
        real_git = garmin_pull.git
        def no_git(*a, **k): raise AssertionError("git was called for a data folder inside the code repo")
        garmin_pull.git = no_git
        try:
            self.assertIsNone(garmin_pull.commit_and_push([ROOT / "demo" / "todo.yaml"], "test"))
        finally:
            garmin_pull.git = real_git

    def test_relative_data_folder_resolves_once_in_a_sync_child(self):
        # Sync children run with cwd = the data folder, so a relative FT_DATA=demo would resolve to demo/demo/.
        def child_data(env):
            env = {**env, "PYTHONPATH": str(ROOT / "scripts")}
            return subprocess.run([sys.executable, "-c", "import bkenv; print(bkenv.DATA)"], cwd=bkenv.DATA, env=env,
                                  capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(child_data({**os.environ, "FT_DATA": "demo"}), str(bkenv.DATA / "demo"))   # the old bug
        self.assertTrue(pathlib.Path(bkenv.child_env()["FT_DATA"]).is_absolute())
        self.assertEqual(child_data(bkenv.child_env()), str(bkenv.DATA))


class EnergyBalance(unittest.TestCase):
    def test_fit_and_history(self):
        b, a = energybalance._fit([(0, 76.0), (10, 75.0), (20, 74.0), (30, 73.0)])
        self.assertAlmostEqual(b, -0.1); self.assertAlmostEqual(a, 76.0)
        self.assertIsNone(energybalance._fit([(0, 76.0), (1, 75.9)]))
        H = energybalance.history(end="2026-10-24")
        counted = [d for d in H["days"] if d["deficit"] is not None]
        self.assertTrue(counted)
        for d in counted: self.assertLessEqual(abs(d["deficit"] - (d["burnt"] - d["eaten"])), 1)
        self.assertAlmostEqual(H["expected_kg"], -H["avg_deficit"] * 30 / 7700, places=2)
        if "actual_kg" in H: self.assertEqual(H["gap_kcal_day"], H["avg_deficit"] - H["actual_avg_deficit"])

    def test_today_projection_adds_up(self):
        last = sorted((pathlib.Path(os.environ["FT_DATA"]) / "days").rglob("*.yaml"))[-1].stem
        T = energybalance.today(last)
        if not T["available"]: self.skipTest("no Garmin day in the demo")
        self.assertEqual(T["projected"], T["burnt_so_far"] + T["rest_of_day_resting"] + (T["rest_of_day_active"] or 0))
        self.assertEqual(T["deficit_so_far"], T["burnt_so_far"] - T["eaten"])
        self.assertEqual(T["deficit_day"], T["projected"] - max(T["eaten"], T["target_mid"] or 0))
        self.assertGreaterEqual(T["projected"], T["burnt_so_far"])


class ThresholdsPage(unittest.TestCase):
    def test_builds_from_the_demo_folder(self):
        T = thresholds.build()
        self.assertTrue(T["rules"] and T["markers"] and T["athlete"]["domains"])
        self.assertTrue(all(len(r) == 5 for _, rows in thresholds.RULES for r in rows))

