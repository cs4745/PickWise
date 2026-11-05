"""买什么 PickWise 命令行入口。"""

from __future__ import annotations

import argparse
import json
import sys

from . import DISCLAIMER, __version__


def _print_disclaimer():
    print("\n" + "=" * 78)
    print(DISCLAIMER)
    print("=" * 78 + "\n")


def cmd_fetch(args):
    from .config import parse_game_keys
    from .fetch import fetch_all
    keys = parse_game_keys(args.games)
    print(f"采集 {', '.join(keys)} 历史开奖数据（{'增量' if args.incremental else '全量'}）...")
    info = fetch_all(keys, full=not args.incremental)
    print(f"完成：{len(info['games'])} 个彩种，校验报告 data/validation.json")
    for k, v in info["games"].items():
        if "cross_check" in v:
            print(f"  {k} 双源交叉校验 {v['cross_check']['checked']} 期，冲突 {v['cross_check']['conflict_count']} 期")
    return 0


def cmd_analyze(args):
    from .analyze import analyze_all
    from .config import parse_game_keys
    keys = parse_game_keys(args.games)
    data = analyze_all(keys)
    for k, a in data.items():
        zf = a["zones"]["front"]
        print(f"\n【{a['name']}】{a['count']} 期，最新第 {a['latest']['issue']} 期"
              f"{'（' + a['latest']['date'] + '）' if a['latest']['date'] else ''}")
        print(f"  规则：{a['rules']}")
        print(f"  热号（近 {zf['recent_window']} 期）："
              + " ".join(f"{x['number']:02d}({x['recent']})" for x in zf["hot"]))
        print(f"  冷号（近 {zf['recent_window']} 期）："
              + " ".join(f"{x['number']:02d}({x['recent']})" for x in zf["cold"]))
        num, om = max(zf["omission"].items(), key=lambda kv: kv[1]["current"])
        print(f"  当前最大遗漏：{zf['name']} {num} 号，已 {om['current']} 期未出现（历史最大 {om['max']} 期）")
        print(f"  卡方检验：χ²={zf['chi2']['stat']}，p={zf['chi2']['pvalue']} -> {zf['chi2']['conclusion']}")
        if a.get("data_notes"):
            print(f"  数据口径提示：{a['data_notes']}")
        print(f"  和值均值 {a['structure']['sum']['mean']}，相邻期自相关 {a['structure']['sum_lag1_corr']}")
    if args.json:
        print(json.dumps(data, ensure_ascii=False))
    return 0


def cmd_recommend(args):
    from .config import parse_game_keys
    from .recommend import STRATEGIES, recommend
    _print_disclaimer()
    keys = parse_game_keys(args.games)
    for k in keys:
        r = recommend(k, strategy=args.strategy, count=args.count, seed=args.seed, window=args.window)
        print(f"\n【{r['name']}】{r['strategy_label']}型 参考组合（种子 {r['seed']}）")
        print(f"  一等奖理论概率：{r['jackpot_odds']}；{r['strategy_desc']}")
        for c in r["combos"]:
            print(f"  第 {c['index']} 组：{c['front_text']}  +  {c['back_text']}")
            print(f"      {c['reason']}")
        print(f"  {r['notice']}")
    print("\n【认真版购买建议】")
    print("  1. 不存在能提高中奖概率的选号方法：每期独立，任意号码的单注中奖概率相同。")
    print("  2. 长期期望回报低于投入（返奖奖金只占销售额的一部分），买得越多长期亏损越确定。")
    print("  3. 若仍想偶尔买：当娱乐消费，先定每月固定上限并严格执行，只用闲钱，")
    print("     不追号、不加倍、不借贷、不把「差一个号」当继续投入的理由。")
    print("  4. 超出预算、想回本、影响生活时请立即停止并寻求帮助；未满 18 周岁禁止购彩。")
    print("  最优的「买什么」是量力而行，或者不买。")
    return 0


def cmd_backtest(args):
    from .backtest import backtest
    from .config import parse_game_keys
    keys = parse_game_keys(args.games)
    for k in keys:
        b = backtest(k, rounds=args.rounds, window=args.window, seed=args.seed)
        print(f"\n【{b['name']}】样本外回测 {b['rounds']} 期（训练窗口 {b['window']} 期）")
        print(f"  {'策略':<8}{'平均命中':>10}{'与随机差':>10}{'z 值':>9}{'显著':>8}")
        for s in b["strategies"].values():
            print(f"  {s['label']:<8}{s['mean_hits']:>10.4f}"
                  f"{(s.get('diff_vs_random') or 0):>10.4f}"
                  f"{(s.get('z_vs_random') or 0):>9.3f}"
                  f"{('是' if s.get('significant') else '否'):>8}")
        print(f"  独立随机理论期望命中数：{b['theoretical_mean_hits']}")
        print(f"  结论：{b['conclusion']}")
    return 0


def cmd_report(args):
    from .report import build_data, generate
    print("生成分析报告（含回测，可能需要十几秒）...")
    data = build_data(rec_count=args.count, rounds=args.rounds, window=args.window, seed=args.seed)
    path, _ = generate(data)
    print(f"报告已生成：{path}")
    print(f"结构化数据：{path.parent / 'analysis.json'}")
    _print_disclaimer()
    return 0


def cmd_all(args):
    from .config import GAME_ORDER, parse_game_keys
    from .fetch import fetch_all
    from .report import build_data, generate
    keys = parse_game_keys(args.games)
    print("1/2 采集数据...")
    fetch_all(keys, full=not args.incremental)
    print("2/2 分析并生成报告...")
    data = build_data(keys=keys, rec_count=args.count, rounds=args.rounds,
                      window=args.window, seed=args.seed)
    path, _ = generate(data)
    print(f"完成：{path}")
    _print_disclaimer()
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="pickwise",
        description="买什么 PickWise —— 双色球 / 大乐透 / 七星彩历史开奖数据统计分析与随机性研究工具（仅供娱乐，不构成投注建议）",
    )
    p.add_argument("--version", action="version", version=f"买什么 PickWise {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def add_games(sp):
        sp.add_argument("--games", default="all", help="彩种：all / ssq / dlt / qxc，逗号分隔（默认 all）")

    f = sub.add_parser("fetch", help="采集历史开奖数据")
    add_games(f)
    f.add_argument("--incremental", action="store_true", help="增量更新（只抓到已存在期号为止）")
    f.set_defaults(func=cmd_fetch)

    a = sub.add_parser("analyze", help="输出热号、冷号、遗漏、卡方检验等统计结果")
    add_games(a)
    a.add_argument("--json", action="store_true", help="同时输出完整 JSON")
    a.set_defaults(func=cmd_analyze)

    r = sub.add_parser("recommend", help="生成参考组合（娱乐演示，非购买建议）")
    add_games(r)
    r.add_argument("--strategy", default="balanced", choices=["balanced", "hot", "cold", "random"])
    r.add_argument("--count", type=int, default=5, help="每组数（默认 5）")
    r.add_argument("--window", type=int, default=100, help="近期统计窗口（默认 100 期）")
    r.add_argument("--seed", type=int, default=20261105, help="随机种子，保证可复现")
    r.set_defaults(func=cmd_recommend)

    b = sub.add_parser("backtest", help="样本外回测，对比统计选号与纯随机")
    add_games(b)
    b.add_argument("--rounds", type=int, default=200, help="回测期数（默认 200）")
    b.add_argument("--window", type=int, default=250, help="训练窗口（默认 250 期）")
    b.add_argument("--seed", type=int, default=20261105)
    b.set_defaults(func=cmd_backtest)

    rp = sub.add_parser("report", help="生成自包含 HTML 分析报告")
    rp.add_argument("--count", type=int, default=3, help="每种策略生成几组（默认 3）")
    rp.add_argument("--rounds", type=int, default=200)
    rp.add_argument("--window", type=int, default=250)
    rp.add_argument("--seed", type=int, default=20261105)
    rp.set_defaults(func=cmd_report)

    al = sub.add_parser("all", help="一键：采集数据 + 生成报告")
    add_games(al)
    al.add_argument("--incremental", action="store_true")
    al.add_argument("--count", type=int, default=3)
    al.add_argument("--rounds", type=int, default=200)
    al.add_argument("--window", type=int, default=250)
    al.add_argument("--seed", type=int, default=20261105)
    al.set_defaults(func=cmd_all)
    return p


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    args = build_parser().parse_args(argv)
    return args.func(args)
