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


class BodyComposition(unittest.TestCase):
    def test_scale_fields_and_fat_mass(self):
        import data
        B = data.body()
        for p in B["scale"]:
            self.assertTrue(set(p) <= {"date", "kg", "fasted", "note", "fat_kg", *data.SCALE_FIELDS})
            if p.get("bf_pct"): self.assertAlmostEqual(p["fat_kg"], p["kg"] * p["bf_pct"] / 100, places=2)
        self.assertIn("bands", B)


class DemoTemplate(unittest.TestCase):
    def test_demo_reference_files_match_the_template(self):
        """tools/make_demo.py copies demo-template/ into demo/, so a fix made only in demo/ is lost on the next rebuild."""
        for f in (ROOT / "demo-template").glob("*.yaml"):
            if f.name == "settings.yaml": continue   # the demo adds its person's profile
            with self.subTest(file=f.name):
                self.assertEqual(f.read_text(encoding="utf-8"), (ROOT / "demo" / f.name).read_text(encoding="utf-8"))


class ThresholdsPage(unittest.TestCase):
    def test_builds_from_the_demo_folder(self):
        T = thresholds.build()
        self.assertTrue(T["rules"] and T["markers"] and T["athlete"]["domains"])
        self.assertTrue(all(len(r) == 5 for _, rows in thresholds.RULES for r in rows))



class FoodsPage(unittest.TestCase):
    def test_totals_add_up(self):
        import foods
        F = foods.build()
        self.assertTrue(F["foods"])
        self.assertEqual(F["counts"]["foods"], len(F["foods"]))
        for f in F["foods"]:
            self.assertGreaterEqual(f["times"], f["w_times"])
            self.assertGreaterEqual(f["days"], 1)
            self.assertLessEqual(f["first"], f["last"])
        for k, s in F["sources"].items():
            with self.subTest(source=k):
                week = sum((f["w_totals"] or {}).get(k, 0) for f in F["foods"])
                self.assertAlmostEqual(s["total"], week, delta=1)
                self.assertTrue(all(0 <= t["share"] <= 1 for t in s["top"]))

    def test_extras(self):
        import foods, nutrition
        F = foods.build()
        P = F["plants"]
        self.assertEqual(P["this_week"], len(P["plants"])); self.assertEqual(len(P["history"]), 8)
        sec = foods._section_map()
        self.assertFalse(foods.is_plant("whey", {"name": "Nutrex 100% Whey chocolate"}, sec))   # "nut" inside a brand name
        self.assertTrue(foods.is_plant("oats-rolled", {"name": "Rolled oats"}, sec))
        self.assertFalse(foods.is_plant("x", {"name": "oats", "plant": False}, sec))           # explicit override wins
        self.assertEqual([s["slot"] for s in F["slots"]["slots"]], list(foods.SLOTS)) if F["slots"]["days"] else None
        self.assertEqual(len(F["weekdays"]["days"]), 7)
        for s in F["swaps"]:
            for c in s["swaps"]: self.assertGreater(c["saves_sf"], 0)


class SleepPage(unittest.TestCase):
    def test_builds_from_the_demo_folder(self):
        import sleep
        S = sleep.build()
        self.assertTrue(S["available"])
        L = S["last"]
        self.assertLess(L["start"], L["end"])
        self.assertTrue(all(n["asleep"] > 0 for n in S["nights"]))
        for f in S["factors"]:
            self.assertGreater(f["a"]["n"], 0); self.assertGreater(f["b"]["n"], 0)
        self.assertTrue(S["general"])
        G = S["stages"]
        if G["available"]:
            self.assertAlmostEqual(sum(G["pct"].values()), 100, delta=3)   # deep + light + REM share of time asleep
            self.assertTrue(all(p["title"] and p["text"] for p in G["patterns"]))
            self.assertEqual(sum(h["count"] for h in G["wake"]["by_hour"]), sum(h["count"] for h in G["wake"]["by_hours_in"]))
        T = S["tonight"]
        if T: self.assertRegex(T["in_bed"], r"^\d\d:\d\d$")

    def test_tonight_works_back_from_the_weekday_wake_time(self):
        import sleep
        rows = [{"start": -60, "end": 6 * 60, "awake": 20, "weekend_morning": False}] * 5 + \
               [{"start": 0, "end": 8 * 60, "awake": 20, "weekend_morning": True}] * 2
        T = sleep.tonight(rows, 450, rows)
        self.assertEqual(T["wake"], "06:00")
        self.assertEqual(T["in_bed"], "21:55")   # 06:00 - 7h30 - 20 min awake - 15 min to fall asleep


class FixedClock(unittest.TestCase):
    def test_ft_now_fixes_the_time(self):
        old = os.environ.get("FT_NOW")
        os.environ["FT_NOW"] = "2026-11-07T22:30"
        try:
            n = bkenv.now()
            self.assertEqual((n.date().isoformat(), n.hour, n.minute), ("2026-11-07", 22, 30))
            self.assertEqual(bkenv.today().isoformat(), "2026-11-07")
            self.assertIsNotNone(n.tzinfo)
        finally:
            if old is None: os.environ.pop("FT_NOW", None)
            else: os.environ["FT_NOW"] = old


class Experiments(unittest.TestCase):
    def setUp(self):
        import experiments as X
        self.X = X
        self.cat = X.catalogue({"screens_off": {"type": "time"}})

    def test_rules(self):
        X, cat = self.X, self.cat
        row = {"night.bedtime": -100, "day.session_end": 18 * 60, "day.last_meal": 21 * 60, "day.caffeine_last": 15 * 60,
               "day.satfat": 18, "day.steps": 9000, "habit.screens_off": 21 * 60 + 15, "food.creatine": True}
        def ok(rule):
            comb, conds, outs, errs = X.check({"start": "2026-11-01", "rule": rule}, cat)
            self.assertEqual(errs, [], rule); return X.kept(row, comb, conds, cat)
        self.assertTrue(ok({"bedtime_by": "22:30"}))                      # asleep 22:20
        self.assertFalse(ok({"bedtime_by": "22:00"}))
        self.assertTrue(ok({"session_end_by": "19:00"}))
        self.assertFalse(ok({"last_meal_by": "20:30"}))
        self.assertFalse(ok({"caffeine_cutoff": "14:00"}))
        self.assertTrue(ok({"all": [{"var": "day.satfat", "op": "<=", "value": 20}, {"var": "day.steps", "op": ">=", "value": 7000}]}))
        self.assertTrue(ok({"all": [{"var": "habit.screens_off", "op": "<=", "value": "21:30"}, {"var": "food.creatine", "op": "=", "value": True}]}))
        self.assertTrue(ok({"any": [{"var": "day.satfat", "op": ">", "value": 30}, {"var": "night.bedtime", "op": "<=", "value": "22:30"}]}))
        # a time that didn't happen keeps a "by" rule; a missing number can't be judged
        self.assertTrue(X.kept({"night.bedtime": -100}, "all", [{"var": "day.session_end", "op": "<=", "parsed": 19 * 60}], cat))
        self.assertIsNone(X.kept({}, "all", [{"var": "day.satfat", "op": "<=", "parsed": 20}], cat))

    def test_anything_else_is_rejected(self):
        X, cat = self.X, self.cat
        bad = {"start": "2026-11-01", "days": 90, "rule": {"all": [
            {"var": "day.protien", "op": ">=", "value": 150}, {"var": "habit.reading", "op": "=", "value": True},
            {"var": "food.no-such-food", "op": "=", "value": True}, {"var": "day.trained", "op": "<=", "value": 1},
            {"var": "night.bedtime", "op": "<=", "value": "late"}, {"var": "day.kcal", "op": "~", "value": 1}]},
            "outcomes": ["day.kcal"]}
        errs = X.check(bad, cat)[3]
        self.assertEqual(len(errs), 8, errs)   # six bad conditions, a bad outcome, a bad length
        self.assertTrue(X.check({"start": "2026-11-01", "rule": {"screens_by": "21:00"}}, cat)[3])   # unknown shorthand
        self.assertTrue(X.check({"start": "soon", "rule": {"bedtime_by": "22:30"}}, cat)[3])

    def test_wording(self):
        X, cat = self.X, self.cat
        comb, conds, _, _ = X.check({"start": "2026-11-01", "rule": {"all": [{"var": "night.bedtime", "op": "<=", "value": "22:30"},
                                                                              {"var": "day.caffeine_last", "op": "<=", "value": "14:00"}]}}, cat)
        self.assertEqual(X.rule_text(cat, comb, conds), "Asleep by 22:30 and no caffeine after 14:00")

    def test_compare_needs_clear_evidence(self):
        X, cat = self.X, self.cat
        base = [{"night.asleep": 400 + (i % 5) * 10} for i in range(20)]
        same = [{"night.asleep": 400 + (i % 5) * 10} for i in range(10)]
        more = [{"night.asleep": 470 + (i % 5) * 10} for i in range(10)]
        self.assertEqual(X.compare(same, base, "night.asleep", 1, cat)["verdict"], "unclear")
        self.assertEqual(X.compare(more, base, "night.asleep", 1, cat)["verdict"], "better")
        self.assertEqual(X.compare(more[:3], base, "night.asleep", 1, cat)["verdict"], "too early")
        r = X.compare(more, base, "night.asleep", 1, cat); self.assertLess(r["lo"], r["diff"]); self.assertLess(r["diff"], r["hi"])

    def test_demo_experiments(self):
        B = self.X.build()
        self.assertEqual(len(B["experiments"]), 3)
        for e in B["experiments"]:
            self.assertNotEqual(e["verdict"], "invalid", e.get("errors"))
            self.assertEqual(len(e["calendar"]), e["days"])
            self.assertEqual(e["kept"] + e["missed"], sum(c["state"] in ("kept", "missed") for c in e["calendar"]))
        self.assertIn("habit.screens_off", B["catalogue"]); self.assertIn("habit.screens_off", B["table"]["cols"])
        self.assertTrue(any(m.get("supplement") for m in B["catalogue"].values()))
        # the salt experiment rode a blood pressure that was already falling: the trend guard has to say so
        salt = next(e for e in B["experiments"] if e["id"] == "salt")
        self.assertEqual(salt["type"], "period"); self.assertEqual(salt["verdict"], "trend")
        self.assertTrue(any(r.get("trend_note") for r in salt["results"]))
        self.assertTrue(all(sum(c["ramp"] for c in e["calendar"]) == e["ramp_days"] for e in B["experiments"] if e["type"] == "period"))
        self.assertIn("bp.morning_sys", B["daily"]["cols"])

    def test_period_rules(self):
        X, cat = self.X, self.cat
        good = {"type": "period", "start": "2026-11-01", "days": 21, "daily": {"all": [{"var": "day.sodium", "op": "<=", "value": 2000}]},
                "outcomes": ["bp.morning_sys", {"var": "weight.kg", "better": "lower"}]}
        self.assertEqual(X.check(good, cat)[3], [])
        errs = lambda **kw: X.check({**good, **kw}, cat)[3]
        self.assertTrue(errs(daily={"all": [{"var": "bp.morning_sys", "op": "<=", "value": 120}]}))   # a result isn't a daily habit
        self.assertTrue(errs(rule={"bedtime_by": "22:30"}))                                              # rule: belongs to night experiments
        self.assertTrue(errs(outcomes=[]))
        self.assertTrue(errs(outcomes=["weight.kg"]))                                                    # which way is better?
        self.assertTrue(errs(ramp_days=30))
        self.assertTrue(errs(requires=["screen_time"]))
        self.assertEqual(errs(requires=["bp.evening", "habit.screens_off"]), [])
        # bp.* only works as a period outcome
        self.assertTrue(X.check({"start": "2026-11-01", "rule": {"bedtime_by": "22:30"}, "outcomes": ["bp.morning_sys"]}, cat)[3])

    def test_requirements(self):
        X, cat = self.X, self.cat
        e = {"type": "period", "start": "2026-11-01", "days": 21, "requires": ["bp.evening"],
             "daily": {"all": [{"var": "food.creatine", "op": "=", "value": True}, {"var": "habit.screens_off", "op": "<=", "value": "22:00"},
                               {"var": "day.sodium", "op": "<=", "value": 2000}, {"var": "day.protein", "op": ">=", "value": 150}]},
             "outcomes": ["bp.morning_sys", {"var": "weight.kg", "better": "lower"}]}
        row = {"bp.morning_sys": 121, "day.sodium": 2400, "day.protein": 90, "habit.screens_off": 21 * 60 + 40}
        at = lambda hm, status="active": {i["key"]: i for i in X.requirements(e, {"status": status}, row, cat, X._hm(hm))}
        T = at("09:00")
        self.assertEqual(list(T)[:3], ["bp.morning", "weight", "bp.evening"])
        self.assertEqual((T["bp.morning"]["state"], T["weight"]["state"], T["bp.evening"]["state"]), ("done", "todo", "todo"))
        self.assertEqual((T["food.creatine"]["state"], T["habit.screens_off"]["state"]), ("todo", "done"))
        self.assertEqual((T["day.sodium"]["state"], T["day.protein"]["state"]), ("missed", "todo"))
        self.assertFalse(any(i["remind"] for i in T.values()))              # nothing due at 9am
        T = at("21:45")
        self.assertEqual({k for k, i in T.items() if i["remind"]}, {"weight", "bp.evening", "food.creatine"})
        self.assertEqual(list(at("21:45", "planned")), ["bp.morning", "weight", "bp.evening"])   # before the start: readings only
        self.assertEqual(at("21:45", "done"), {})
        night = {"start": "2026-11-01", "rule": {"bedtime_by": "22:30"}}
        bed = lambda hm: X.requirements(night, {"status": "active"}, {}, cat, X._hm(hm))[1]
        self.assertEqual((bed("21:50")["due"], bed("21:50")["remind"], bed("21:00")["remind"]), ("21:45", True, False))
        self.assertFalse(bed("22:40")["remind"])                           # too late to help

    def test_progress_and_what_next(self):
        X = self.X
        cal = lambda kept, missed, left: [{"state": "kept"}] * kept + [{"state": "missed"}] * missed + [{"state": "future"}] * left
        P = lambda typ, k, m, left: X.progress({"status": "active", "type": typ, "kept": k, "missed": m, "calendar": cal(k, m, left)})
        self.assertEqual(P("night", 5, 2, 7)["can_miss"], 3)     # 9 of 14 kept is 64%: one more miss would be 57%
        self.assertEqual(P("night", 2, 0, 3)["can_miss"], 0)     # needs 5 kept nights, has 2 with 3 to go
        self.assertLess(P("period", 10, 8, 3)["can_miss"], 0)    # can't reach 75% any more
        self.assertEqual(P("night", 5, 2, 7)["left"], 7)
        self.assertIsNone(X.progress({"status": "done"}))
        self.assertEqual(set(X.NEXT), {"worked", "worse", "no effect", "trend", "inconclusive"})
        B = X.build()
        for e in B["experiments"]:
            if e["status"] == "done": self.assertTrue(e["next"]); self.assertTrue(e["finished_on"])
            if e["status"] == "active": self.assertFalse(any(r.get("lean") and r["verdict"] == "unclear" for r in e["results"]))

    def test_sparse_columns(self):
        rows = [{"date": f"2026-10-{i + 1:02d}", "day.kcal": 2000 + i, "food.creatine": True if i == 3 else None} for i in range(10)]
        C = self.X._cols(rows, self.cat)["cols"]
        self.assertEqual(len(C["day.kcal"]), 10); self.assertEqual(C["food.creatine"], {"s": [[3, True]]})
