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
from pickwise.strategy import NEWS, news_inference, news_strategy  # noqa: E402

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
        self.assertEqual(jackpot_odds("kl8"), "1 / 8,911,711")


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


class TestNewsStrategy(unittest.TestCase):
    def test_news_inference_is_self_consistent(self):
        f = news_inference()
        self.assertEqual(f["bets_per_ticket"], 11)
        self.assertEqual(f["total_bets"], 66)
        self.assertEqual(f["total_cost"], 132)
        self.assertEqual(f["pool_ratio"], 0.25)
        self.assertEqual(len(f["layers"]), 3)
        self.assertIn("不能提升中奖概率", NEWS["official_warning"])

    def test_strategy_output_is_valid(self):
        import math
        for k in GAME_ORDER:
            g = game_of(k)
            s = news_strategy(k, groups=6, expand=2, seed=7)
            n_front = g.pick_size if g.is_pool else g.front.size
            n_back = 0 if g.is_pool else g.back.size
            self.assertEqual(len(s["singles"]), 6)
            self.assertGreater(s["multiple"]["bets"], 1)
            self.assertEqual(s["multiple"]["cost"], s["multiple"]["bets"] * g.price)
            for c in s["singles"]:
                self.assertEqual(len(c["front"]), n_front)
                self.assertEqual(len(c["back"]), n_back)
                self.assertTrue(all(g.front.low <= x <= g.front.high for x in c["front"]))
                if g.front.combination:
                    self.assertEqual(c["front"], sorted(c["front"]))
                    self.assertEqual(len(set(c["front"])), n_front)
            m = s["multiple"]
            if g.is_pool:
                self.assertEqual(len(m["front"]), 11)
                self.assertEqual(m["bets"], 11)
                self.assertEqual(s["total_bets"], 66)
                self.assertEqual(s["total_cost"], 132)
                self.assertTrue(s["news_match"])
                self.assertEqual(len(s["multiple_groups"]), 6)
                self.assertEqual(len(s["pool"]["front"]), 20)
            elif g.front.combination:
                self.assertEqual(m["front"], sorted(m["front"]))
                self.assertEqual(m["bets"], math.comb(len(m["front"]), g.front.size)
                                 * math.comb(len(m["back"]), g.back.size))
                self.assertEqual(len(s["cost_table"]), 3)
            else:
                self.assertEqual(m["bets"], 4)  # 2 个数位各双选
                self.assertEqual(len(s["cost_table"]), 3)

    def test_kl8_prize_math(self):
        from pickwise.kl8 import prize_math
        p = prize_math("kl8")
        self.assertEqual(p["jackpot_odds"], "1 / 8,911,711")
        self.assertAlmostEqual(p["return_rate"], 56.984, places=2)
        self.assertAlmostEqual(p["expected_prize"], 1.139679, places=5)
        self.assertEqual(len(p["rows"]), 11)
        self.assertEqual(p["rows"][9]["prize"], 8000)
        self.assertEqual(p["rows"][10]["prize"], 5_000_000)

    def test_kl8_draws_and_recommendations(self):
        from pickwise.analyze import analyze_game
        from pickwise.fetch import validate_draws
        from pickwise.analyze import load_draws
        rows = load_draws("kl8")
        errors, _ = validate_draws("kl8", rows)
        self.assertEqual(errors[:5], [])
        for d in rows:
            self.assertEqual(len(d["front"]), 20)
            self.assertEqual(d["back"], [])
            self.assertEqual(d["front"], sorted(set(d["front"])))
        a = analyze_game("kl8")
        self.assertTrue(a["is_pool"])
        self.assertEqual(a["pick_size"], 10)
        self.assertEqual(a["structure"]["type"], "pool")
        self.assertEqual(a["zones"]["back"]["not_applicable"], True)

    def test_reproducible(self):
        a = news_strategy("ssq", seed=99)
        b = news_strategy("ssq", seed=99)
        self.assertEqual([x["front"] for x in a["singles"]],
                         [x["front"] for x in b["singles"]])


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


class TestServe(unittest.TestCase):
    def test_serve_default_host_and_custom_port(self):
        from pickwise.cli import build_parser
        a = build_parser().parse_args(["serve"])
        self.assertEqual((a.host, a.port), ("0.0.0.0", 8765))
        b = build_parser().parse_args(["serve", "--host", "127.0.0.1", "--port", "9000"])
        self.assertEqual((b.host, b.port), ("127.0.0.1", 9000))

    def test_cli_no_fetch_flag(self):
        from pickwise.cli import build_parser
        self.assertFalse(build_parser().parse_args(["serve"]).no_fetch)
        b = build_parser().parse_args(["serve", "--no-fetch", "--port", "8801"])
        self.assertTrue(b.no_fetch)
        self.assertEqual(b.port, 8801)

    def test_run_update_skip_fetch_never_calls_network(self):
        from unittest.mock import patch
        import pickwise.serve as s
        from pickwise.config import GAME_ORDER
        fake = {"games": {k: {"analysis": {"name": k, "latest": {"issue": "x"}}}
                          for k in GAME_ORDER}, "meta": {}}
        opts = {"skip_fetch": True, "rec_count": 1, "rounds": 1,
                "window": 50, "seed": 1}
        with patch.object(s, "_DEFAULTS", opts), \
                patch("pickwise.fetch.fetch_all") as mf, \
                patch("pickwise.report.build_data", return_value=fake) as mb, \
                patch("pickwise.report.generate") as mg:
            _, msg = s.run_update()
        self.assertFalse(mf.called)
        self.assertTrue(mb.called)
        self.assertTrue(mg.called)
        self.assertIn("未采集", msg)
        self.assertIn("--no-fetch", msg)

    def test_friendly_error_explains_http_403(self):
        from pickwise.serve import friendly_error
        msg = friendly_error(RuntimeError(
            "请求失败（重试 3 次）: https://www.cwl.gov.cn/...\nHTTP Error 403: Forbidden"))
        self.assertIn("403", msg)
        self.assertIn("HTTPS_PROXY", msg)
        self.assertIn("fetch --incremental", msg)
        self.assertIn("与监听地址、端口", msg)

    def test_friendly_error_explains_timeout_and_permission(self):
        from pickwise.serve import friendly_error
        self.assertIn("出站网络", friendly_error(TimeoutError("timed out")))
        self.assertIn("写权限", friendly_error(PermissionError("denied")))

    def test_update_ui_parses_server_error_body(self):
        """页面必须先读响应体再判断 res.ok，不能只显示 HTTP 500。"""
        from pickwise.report import TEMPLATE
        self.assertIn("out.error||'服务端未给出原因'", TEMPLATE)
        self.assertNotIn("if(!res.ok)throw new Error('HTTP '+res.status);", TEMPLATE)

    def test_inject_update_api_is_same_origin(self):
        from pickwise.serve import UPDATE_API_TOKEN, inject_update_api
        out = inject_update_api("<script>const injected=" + UPDATE_API_TOKEN + ";</script>")
        self.assertIn("'/api/update'", out)
        self.assertNotIn("__PICKWISE_UPDATE_API__", out)

    def test_static_report_keeps_fallback_placeholder(self):
        """静态 HTML 保留占位符，双击/预览页才会回退到 8765。"""
        from pickwise.report import generate
        with tempfile.TemporaryDirectory() as td, patch("pickwise.report.OUTPUT_DIR", Path(td)):
            path, _ = generate({"meta": {"version": "test", "generated_at": "2026-01-01",
                                         "disclaimer": "仅用于测试"}, "games": {}})
            text = path.read_text(encoding="utf-8")
        self.assertIn("__PICKWISE_UPDATE_API__", text)
        self.assertNotIn("const injected='/api/update'", text)


@unittest.skipUnless(HAS_DATA, "需要先运行 python pickwise.py fetch")
class TestWithRealData(unittest.TestCase):
    def test_all_draws_pass_validation(self):
        for k in GAME_ORDER:
            errors, _ = validate_draws(k, load_draws(k))
            self.assertEqual(errors[:5], [], f"{k} 数据校验失败")

    def test_recommendations_are_valid(self):
        for k in GAME_ORDER:
            g = game_of(k)
            n_front = g.pick_size if g.is_pool else g.front.size
            n_back = 0 if g.is_pool else g.back.size
            for st in STRATEGIES:
                r = recommend(k, strategy=st, count=2, seed=42)
                for c in r["combos"]:
                    self.assertEqual(len(c["front"]), n_front)
                    self.assertEqual(len(c["back"]), n_back)
                    self.assertTrue(all(g.front.low <= x <= g.front.high for x in c["front"]))
                    self.assertTrue(all(g.back.low <= x <= g.back.high for x in c["back"]))
                    if g.front.combination:
                        self.assertEqual(len(set(c["front"])), n_front)
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

    def test_backtest_conclusion_handles_significant_result(self):
        """覆盖 |z|>=2 的结论分支，且该优势换种子后不可复现。"""
        from pickwise.backtest import backtest
        b = backtest("kl8", rounds=200, window=250, seed=20261105)
        self.assertIsInstance(b["conclusion"], str)
        self.assertIn("理论返奖率", b["conclusion"])
        self.assertNotIn("不换算奖金", b["conclusion"])
        if any(v.get("significant") for v in b["strategies"].values()):
            self.assertIn("假阳性", b["conclusion"])
        alt = [abs(backtest("kl8", rounds=200, window=250, seed=s)
                   ["strategies"]["balanced"]["z_vs_random"]) for s in (1, 42)]
        self.assertFalse(all(z >= 2 for z in alt), "显著优势不应在多个种子下稳定复现")

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
        self.assertIn("news", data)
        self.assertEqual(data["news"]["inference"]["total_cost"], 132)
        self.assertEqual(len(g["news_strategy"]["singles"]), 6)

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
