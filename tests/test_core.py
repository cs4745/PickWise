"""核心逻辑单元测试（不联网）。

运行：python -m unittest discover -s tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pickwise.analyze import chi2_sf, load_draws, omission_stats, zone_counts  # noqa: E402
from pickwise.config import DATA_DIR, GAMES, GAME_ORDER, game_of  # noqa: E402
from pickwise.fetch import cross_check, issue_sort_key, validate_draws  # noqa: E402
from pickwise.recommend import STRATEGIES, jackpot_odds, recommend  # noqa: E402
from pickwise.report import extract_top_pick  # noqa: E402

HAS_DATA = all((DATA_DIR / f"{k}.csv").exists() for k in GAME_ORDER)


def draw(game_key, front, back, issue="2026001", date="2026-01-01"):
    return {"issue": issue, "date": date, "front": list(front), "back": list(back),
            "source": "test"}


class TestMath(unittest.TestCase):
    def test_chi2_critical_values(self):
        self.assertAlmostEqual(chi2_sf(3.8414588, 1), 0.05, places=4)
        self.assertAlmostEqual(chi2_sf(5.9914645, 2), 0.05, places=4)
        self.assertEqual(chi2_sf(0, 5), 1.0)
        self.assertLess(chi2_sf(30, 1), 0.0001)

    def test_issue_sort_key(self):
        self.assertLess(issue_sort_key("2003001"), issue_sort_key("2026126"))
        self.assertLess(issue_sort_key("07001"), issue_sort_key("26126"))

    def test_jackpot_odds(self):
        self.assertEqual(jackpot_odds("ssq"), "1 / 17,721,088")
        self.assertEqual(jackpot_odds("dlt"), "1 / 21,425,712")
        self.assertEqual(jackpot_odds("qxc"), "1 / 15,000,000")


class TestValidation(unittest.TestCase):
    def test_valid_draws(self):
        errors, _ = validate_draws("ssq", [draw("ssq", [1, 2, 3, 4, 5, 6], [7])])
        self.assertEqual(errors, [])

    def test_catches_out_of_range(self):
        errors, _ = validate_draws("ssq", [draw("ssq", [1, 2, 3, 4, 5, 34], [7])])
        self.assertTrue(any("越界" in e for e in errors))

    def test_catches_duplicate_and_unsorted(self):
        errors, _ = validate_draws("ssq", [draw("ssq", [6, 2, 3, 4, 5, 6], [7])])
        self.assertTrue(any("重复" in e for e in errors))
        self.assertTrue(any("升序" in e for e in errors))

    def test_catches_wrong_length(self):
        errors, _ = validate_draws("dlt", [draw("dlt", [1, 2, 3, 4], [1, 2])])
        self.assertTrue(any("个数" in e for e in errors))

    def test_qxc_allows_repeated_digits(self):
        errors, _ = validate_draws("qxc", [draw("qxc", [1, 1, 1, 1, 1, 1], [14])])
        self.assertEqual(errors, [])

    def test_cross_check_detects_conflict(self):
        a = [draw("ssq", [1, 2, 3, 4, 5, 6], [7])]
        b = [draw("ssq", [1, 2, 3, 4, 5, 6], [8])]
        self.assertEqual(cross_check(a, a)["conflict_count"], 0)
        self.assertEqual(cross_check(a, b)["conflict_count"], 1)


class TestCounters(unittest.TestCase):
    def test_frequency_and_omission(self):
        g = game_of("ssq")
        draws = [draw("ssq", [1, 2, 3, 4, 5, 6], [7], issue=str(2026000 + i))
                 for i in range(1, 6)]
        draws[-1]["front"] = [1, 2, 3, 4, 5, 7]
        counts = zone_counts(draws, "front", g)
        self.assertEqual(counts[0], 5)   # 01 出现 5 次
        self.assertEqual(counts[5], 4)   # 06 出现 4 次
        om = omission_stats(draws, "front", g)
        self.assertEqual(om[6]["current"], 1)
        self.assertEqual(om[1]["current"], 0)


class TestTopPick(unittest.TestCase):
    @staticmethod
    def combo(front, back, idx=1):
        return {"index": idx, "front": front, "back": back,
                "front_text": "", "back_text": "", "reason": ""}

    def test_combination_picks_most_frequent(self):
        recs = {
            "a": {"combos": [self.combo([1, 2, 3, 4, 5, 6], [7], 1),
                             self.combo([1, 2, 3, 4, 5, 7], [8], 2)]},
            "b": {"combos": [self.combo([1, 2, 3, 4, 5, 6], [7], 1)]},
        }
        tp = extract_top_pick(game_of("ssq"), recs)
        self.assertEqual(tp["total_combos"], 3)
        self.assertEqual(tp["front"], [1, 2, 3, 4, 5, 6])
        self.assertEqual(tp["back"], [7])
        self.assertEqual(tp["front_support"][0]["count"], 3)
        self.assertEqual(len(set(tp["front"])), 6)

    def test_digit_game_picks_by_position(self):
        recs = {
            "a": {"combos": [self.combo([1] * 6, [5]), self.combo([1] * 6, [6])]},
            "b": {"combos": [self.combo([2] * 6, [5])]},
        }
        tp = extract_top_pick(game_of("qxc"), recs)
        self.assertEqual(tp["front"], [1] * 6)
        self.assertEqual(tp["back"], [5])
        self.assertEqual(tp["front_support"][0]["position"], 1)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            extract_top_pick(game_of("ssq"), {})


@unittest.skipUnless(HAS_DATA, "需要先运行 python pickwise.py fetch")
class TestWithRealData(unittest.TestCase):
    def test_all_draws_pass_validation(self):
        for k in GAME_ORDER:
            errors, _ = validate_draws(k, load_draws(k))
            self.assertEqual(errors[:5], [], f"{k} 数据校验失败")

    def test_recommendations_are_valid(self):
        for k in GAME_ORDER:
            g = game_of(k)
            for st in STRATEGIES:
                r = recommend(k, strategy=st, count=2, seed=42)
                for c in r["combos"]:
                    self.assertEqual(len(c["front"]), g.front.size)
                    self.assertEqual(len(c["back"]), g.back.size)
                    self.assertTrue(all(g.front.low <= x <= g.front.high for x in c["front"]))
                    self.assertTrue(all(g.back.low <= x <= g.back.high for x in c["back"]))
                    if g.front.combination:
                        self.assertEqual(len(set(c["front"])), g.front.size)
                        self.assertEqual(c["front"], sorted(c["front"]))

    def test_reproducible_seed(self):
        a = recommend("ssq", count=3, seed=7)
        b = recommend("ssq", count=3, seed=7)
        self.assertEqual([c["front"] for c in a["combos"]],
                         [c["front"] for c in b["combos"]])

    def test_backtest_structure(self):
        from pickwise.backtest import backtest
        b = backtest("ssq", rounds=12, window=80, seed=1)
        self.assertEqual(b["rounds"], 12)
        self.assertIn("random", b["strategies"])
        self.assertIn("conclusion", b)
        s = b["strategies"]["random"]
        dist_total = sum(s["distribution"].values())
        self.assertEqual(dist_total, b["rounds"])
        recomputed = sum(int(k) * v for k, v in s["distribution"].items()) / b["rounds"]
        self.assertAlmostEqual(s["mean_hits"], recomputed, places=3)

    def test_build_data_has_full_history_and_top_pick(self):
        from pickwise.report import build_data
        data = build_data(keys=["ssq"], rec_count=2, rounds=20, window=80, seed=1)
        g = data["games"]["ssq"]
        self.assertEqual(len(g["history"]), g["analysis"]["count"])
        self.assertEqual(len(g["recent"]), 10)
        self.assertEqual(len(g["top_pick"]["front"]), 6)
        self.assertEqual(len(g["top_pick"]["back"]), 1)
        self.assertEqual(g["top_pick"]["total_combos"], 8)  # 4 策略 × 2 组
        self.assertTrue(g["history"][0][0] >= g["history"][-1][0])

    def test_report_generation(self):
        from pickwise.report import generate
        with tempfile.TemporaryDirectory() as td, patch("pickwise.report.OUTPUT_DIR", Path(td)):
            path, _ = generate({"meta": {"version": "test", "generated_at": "2026-01-01",
                                         "disclaimer": "仅用于测试"}, "games": {}})
            text = path.read_text(encoding="utf-8")
            self.assertIn("买什么", text)
            self.assertNotIn("__DATA__", text)
            self.assertNotIn("__DISCLAIMER__", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
