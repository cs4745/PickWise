"""样本外回测：检验「按历史冷热号选号」是否真的比纯随机更准。

做法：对最近 N 期中的每一期，只用该期之前的历史数据生成参考组合，
再与该期真实开奖号比对（严格样本外，无未来函数），并与均匀随机基线配对比较。
"""

from __future__ import annotations

import math
import random
import statistics
from collections import Counter

from .analyze import load_draws
from .config import game_of
from .recommend import STRATEGIES, _weights_for, generate_one

DEFAULT_STRATEGIES = ("balanced", "hot", "cold", "random")


def match_counts(game, pred_front, pred_back, actual_front, actual_back):
    if game.front.combination:
        fh = len(set(pred_front) & set(actual_front))
        bh = len(set(pred_back) & set(actual_back))
    else:
        fh = sum(1 for a, b in zip(pred_front, actual_front) if a == b)
        bh = sum(1 for a, b in zip(pred_back, actual_back) if a == b)
    return fh, bh


def theoretical_hits(game):
    if game.front.combination:
        fe = game.front.size ** 2 / game.front.slots
        be = game.back.size ** 2 / game.back.slots
    else:
        fe = game.front.size / game.front.slots
        be = game.back.size / game.back.slots
    return round(fe + be, 4)


def backtest(game_key, rounds=200, window=250, strategies=DEFAULT_STRATEGIES, seed=20261105):
    game = game_of(game_key)
    draws = load_draws(game_key)
    max_rounds = len(draws) - 100
    rounds = max(10, min(rounds, max_rounds))
    start = len(draws) - rounds
    results = {s: {"hits": [], "front_hits": [], "back_hits": [], "combos": 0}
               for s in strategies}
    structure = None
    for i in range(start, len(draws)):
        train = draws[max(0, i - window):i]
        actual = draws[i]
        # 结构约束只用训练期数据，避免未来函数
        if game.front.combination:
            ss = sorted(sum(d["front"]) for d in train)
            structure = {"type": "combination",
                         "sum": {"p10": ss[int(len(ss) * .1)], "p90": ss[int(len(ss) * .9)]}}
        for si, st in enumerate(strategies):
            rng = random.Random(seed + i * 977 + si * 31)
            weights = (_weights_for(train, "front", game, st, window),
                       _weights_for(train, "back", game, st, window))
            front, back = generate_one(game_key, st, train, rng, window, structure,
                                       use_filter=(st != "random"), weights=weights)
            fh, bh = match_counts(game, front, back, actual["front"], actual["back"])
            results[st]["hits"].append(fh + bh)
            results[st]["front_hits"].append(fh)
            results[st]["back_hits"].append(bh)
            results[st]["combos"] += 1

    base = results["random"]["hits"] if "random" in results else None
    summary = {}
    for st, r in results.items():
        h = r["hits"]
        item = {
            "strategy": st,
            "label": STRATEGIES[st]["label"],
            "rounds": len(h),
            "mean_hits": round(statistics.mean(h), 4),
            "mean_front_hits": round(statistics.mean(r["front_hits"]), 4),
            "mean_back_hits": round(statistics.mean(r["back_hits"]), 4),
            "max_hits": max(h),
            "high_hit_rounds": sum(1 for x in h if x >= 4),
            "full_matches": sum(1 for x in h if x == game.front.size + game.back.size),
            "distribution": {str(k): r["hits"].count(k) for k in range(game.front.size + game.back.size + 1)},
        }
        if base is not None:
            diffs = [a - b for a, b in zip(h, base)]
            mean_d = statistics.mean(diffs)
            sd = statistics.pstdev(diffs)
            se = sd / math.sqrt(len(diffs)) if len(diffs) > 1 else 0
            item["diff_vs_random"] = round(mean_d, 4)
            item["z_vs_random"] = round(mean_d / se, 3) if se else 0.0
            item["significant"] = abs(item["z_vs_random"]) >= 2
        summary[st] = item

    exp = theoretical_hits(game)
    beats = [s for s in summary.values() if s.get("significant") and s.get("diff_vs_random", 0) > 0]
    conclusion = (
        f"最近 {rounds} 期严格样本外回测：纯随机基线平均命中 {summary['random']['mean_hits'] if 'random' in summary else 'N/A'} 个，"
        f"理论期望 {exp} 个。"
        + (f"策略 {', '.join(STRATEGIES[s]['label'] for s in beats)} 出现统计显著优势，需警惕多重比较与样本量不足。"
           if beats else
           "其余各策略与随机基线的差异均未达到统计显著（|z|<2），说明历史冷热号加权没有带来超过随机的命中能力。")
        + " 回测只统计号码命中个数，不换算奖金；命中个数与奖级奖金并非线性关系。"
    )
    return {
        "game": game_key,
        "name": game.name,
        "rounds": rounds,
        "window": window,
        "seed": seed,
        "theoretical_mean_hits": exp,
        "strategies": summary,
        "conclusion": conclusion,
    }


def backtest_all(keys=None, rounds=200, window=250, seed=20261105):
    keys = keys or ("ssq", "dlt", "qxc")
    return {k: backtest(k, rounds=rounds, window=window, seed=seed) for k in keys}
