"""历史开奖数据的统计分析。

指标：出现频率、热号/冷号、当前遗漏与最大遗漏、卡方均匀性检验、
和值/奇偶/大小/区间/连号/重号等结构分布、近期间隔自相关。

所有指标只描述「已经发生过什么」，不含任何对未来的预测能力。
"""

from __future__ import annotations

import math
import statistics
from collections import Counter

from .config import GAMES, GAME_ORDER, game_of
from .fetch import read_csv

WINDOWS = (30, 100, 300)
TREND_LEN = 120

# 已知的历史口径问题，报告中如实标注，避免把数据问题误读成「规律」
DATA_NOTES = {
    "ssq": "2013 年之前的开奖日期官方接口未提供（CSV 中日期留空）；2003 年起的号码已与 500 彩票网历史数据逐期交叉校验一致。",
    "dlt": "分段检验显示 2007–2010 年前区号码分布明显偏向大号，两个独立数据源的号码完全一致，说明并非采集错误，而是历史口径/摇奖方式差异；2019 年后与均匀假设一致。该偏离不提供任何预测能力。",
    "qxc": "七星彩第 7 位自 2020 年起由 0~9 扩展为 0~14，因此「全历史特别位」的均匀性检验必然显著偏离，应看分段结果；前六位不受影响。",
}


# ---------------------------------------------------------------- 卡方分布
def _gamma_p(a: float, x: float) -> float:
    """正则化下不完全伽马 P(a,x)，级数展开。"""
    if x <= 0:
        return 0.0
    ap, total, delta = a, 1.0 / a, 1.0 / a
    for _ in range(1000):
        ap += 1
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * 1e-14:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gamma_q(a: float, x: float) -> float:
    """正则化上不完全伽马 Q(a,x)，连分数展开。"""
    tiny = 1e-300
    b, c, d = x + 1 - a, 1 / tiny, 1 / (x + 1 - a)
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-14:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def chi2_sf(stat: float, df: int) -> float:
    """卡方分布上尾概率 P(X > stat)。"""
    if stat <= 0:
        return 1.0
    a, x = df / 2.0, stat / 2.0
    return 1.0 - _gamma_p(a, x) if x < a + 1 else _gamma_q(a, x)


def chi_square_uniform(counts, expected_each):
    observed = list(counts)
    stat = sum((o - expected_each) ** 2 / expected_each for o in observed) if expected_each else 0.0
    df = max(1, len(observed) - 1)
    p = chi2_sf(stat, df)
    if p < 0.01:
        conclusion = "与均匀分布存在显著偏离（p<0.01），多半源于历史规则调整或数据口径差异，不代表可利用的规律"
    elif p < 0.05:
        conclusion = "与均匀分布有轻度偏离（p<0.05），在多重比较下属正常波动"
    else:
        conclusion = "无法拒绝『各号等概率』假设（p≥0.05），即与独立均匀随机抽取一致"
    return {"stat": round(stat, 3), "df": df, "pvalue": round(p, 6), "conclusion": conclusion}


# ---------------------------------------------------------------- 基础工具
def load_draws(game_key: str):
    """按时间升序返回（最老 -> 最新）。"""
    rows = read_csv(game_key)
    return sorted(rows, key=lambda d: (int(d["issue"][:4]) if len(d["issue"]) >= 7 else 2000 + int(d["issue"][:2]),
                                      int(d["issue"][4:] if len(d["issue"]) >= 7 else d["issue"][2:])))


def zone_counts(draws, zone_key: str, game):
    """每个号码在历史中的出现次数，按号码升序返回。"""
    zone = getattr(game, zone_key)
    counter = Counter()
    for d in draws:
        for v in d[zone_key]:
            counter[v] += 1
    return [counter.get(n, 0) for n in zone.numbers]


def omission_stats(draws, zone_key: str, game):
    """当前遗漏、历史最大遗漏、平均遗漏间隔。"""
    zone = getattr(game, zone_key)
    result = {}
    for n in zone.numbers:
        gaps, since = [], 0
        last_seen = None
        for idx, d in enumerate(draws):
            if n in d[zone_key]:
                if last_seen is not None:
                    gaps.append(idx - last_seen - 1)
                last_seen = idx
                since = 0
            else:
                since += 1
        # since = 距最近一次出现已过去的期数（最新期出现则为 0）
        result[n] = {
            "current": since,
            "max": max(gaps) if gaps else since,
            "avg": round(sum(gaps) / len(gaps), 2) if gaps else None,
            "times": sum(1 for d in draws if n in d[zone_key]),
        }
    return result


def pearson_corr(xs, ys):
    if len(xs) < 3:
        return 0.0
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return round(num / (dx * dy), 4) if dx and dy else 0.0


# ---------------------------------------------------------------- 结构统计
def _structure_combination(draws, game):
    zone = game.front
    mid = (zone.low + zone.high + 1) // 2
    third = zone.slots / 3
    sums, odds, bigs, spans, acs, cons, repeats, thirds = [], [], [], [], [], [], [], []
    prev = None
    for d in draws:
        v = d["front"]
        sums.append(sum(v))
        odds.append(sum(1 for x in v if x % 2))
        bigs.append(sum(1 for x in v if x >= mid))
        spans.append(max(v) - min(v))
        acs.append(len({abs(a - b) for i, a in enumerate(v) for b in v[i + 1:]}) - (len(v) - 1))
        cons.append(sum(1 for a, b in zip(v, v[1:]) if b - a == 1))
        if prev is not None:
            repeats.append(len(set(v) & set(prev)))
        thirds.append(tuple(sum(1 for x in v if (x - zone.low) < third * (i + 1) and (x - zone.low) >= third * i)
                            for i in range(3)))
        prev = v
    theoretical_repeat = zone.size ** 2 / zone.slots
    return {
        "type": "combination",
        "sum": {"values": sums[-TREND_LEN:], "mean": round(statistics.mean(sums), 2),
                "min": min(sums), "max": max(sums),
                "p10": sorted(sums)[int(len(sums) * .1)], "p90": sorted(sums)[int(len(sums) * .9)],
                "hist": _histogram(sums, 12)},
        "odd_count": _count_dist(odds, zone.size + 1),
        "big_count": _count_dist(bigs, zone.size + 1),
        "span": {"mean": round(statistics.mean(spans), 2)},
        "ac": _count_dist(acs, max(acs) + 1),
        "consecutive_rate": round(sum(1 for c in cons if c) / len(cons), 4),
        "repeat_mean": round(statistics.mean(repeats), 4) if repeats else None,
        "repeat_theoretical": round(theoretical_repeat, 4),
        "third_ratio_top": [{"ratio": f"{a}:{b}:{c}", "count": n}
                            for (a, b, c), n in Counter(thirds).most_common(6)],
        "sum_lag1_corr": pearson_corr(sums[:-1], sums[1:]),
    }


def _structure_digits(draws, game):
    sums, distinct, hits = [], [], []
    prev = None
    for d in draws:
        v = d["front"]
        sums.append(sum(v))
        distinct.append(len(set(v)))
        if prev is not None:
            hits.append(sum(1 for a, b in zip(v, prev) if a == b))
        prev = v
    return {
        "type": "digits",
        "sum": {"values": sums[-TREND_LEN:], "mean": round(statistics.mean(sums), 2),
                "min": min(sums), "max": max(sums),
                "p10": sorted(sums)[int(len(sums) * .1)], "p90": sorted(sums)[int(len(sums) * .9)],
                "hist": _histogram(sums, 12)},
        "distinct_mean": round(statistics.mean(distinct), 3),
        "position_hit_mean": round(statistics.mean(hits), 4) if hits else None,
        "position_hit_theoretical": round(game.front.size / game.front.slots, 4),
        "sum_lag1_corr": pearson_corr(sums[:-1], sums[1:]),
    }


def _histogram(values, bins):
    lo, hi = min(values), max(values)
    width = (hi - lo + 1) / bins
    counts = [0] * bins
    for v in values:
        counts[min(bins - 1, int((v - lo) / width))] += 1
    return {"labels": [f"{lo + width * i:.0f}~{lo + width * (i + 1) - 1:.0f}" for i in range(bins)],
            "counts": counts}


def _count_dist(values, size):
    c = Counter(values)
    return {"labels": [str(i) for i in range(size)],
            "counts": [c.get(i, 0) for i in range(size)]}


# ---------------------------------------------------------------- 分段检验
def _year_of(issue: str):
    s = str(issue)
    if len(s) >= 7:
        return int(s[:4])
    yy = int(s[:2])
    return 1900 + yy if yy >= 90 else 2000 + yy


def era_check(draws, game, zone_key="front", span=3):
    """按 3 年一段做均匀性检验，用于发现历史规则调整 / 数据口径变化。"""
    zone = getattr(game, zone_key)
    buckets = {}
    for d in draws:
        buckets.setdefault((_year_of(d["issue"]) // span) * span, []).append(d)
    out = []
    for start_year in sorted(buckets):
        sub = buckets[start_year]
        if len(sub) < 30:
            continue
        counts = zone_counts(sub, zone_key, game)
        expected = len(sub) * zone.size / zone.slots
        chi = chi_square_uniform(counts, expected)
        out.append({
            "label": f"{start_year}~{start_year + span - 1}",
            "count": len(sub),
            "chi2": chi["stat"],
            "pvalue": chi["pvalue"],
            "deviates": chi["pvalue"] < 0.05,
        })
    return out


# ---------------------------------------------------------------- 单彩种分析
def _zone_analysis(draws, zone_key, game, windows):
    zone = getattr(game, zone_key)
    numbers = zone.numbers
    counts = zone_counts(draws, zone_key, game)
    n = len(draws)
    # 组合型每期抽 size 个且不重复；排列型每期每个位置独立抽 1 次
    expected = n * zone.size / zone.slots if zone.combination else n * zone.size / zone.slots
    omissions = omission_stats(draws, zone_key, game)

    recent = {}
    for w in windows:
        sub = draws[-w:] if w <= n else draws
        recent[w] = zone_counts(sub, zone_key, game)

    main_w = min(windows, key=lambda w: abs(w - 100))
    rc = recent[main_w]
    by_count = sorted(range(len(numbers)), key=lambda i: (-rc[i], numbers[i]))
    # 小号域（如七星彩 0~9）时避免热号 / 冷号列表出现重叠
    k = min(8, max(3, len(numbers) // 2))
    hot_idx, cold_idx = by_count[:k], list(reversed(by_count[-k:]))

    def detail(i):
        num = numbers[i]
        return {
            "number": num,
            "count": counts[i],
            "rate": round(counts[i] / n, 5),
            "recent": rc[i],
            "recent_expected": round(main_w * zone.size / zone.slots, 2),
            "deviation": round(counts[i] - expected, 2),
            "omission": omissions[num],
        }

    out = {
        "name": zone.name,
        "low": zone.low,
        "high": zone.high,
        "size": zone.size,
        "combination": zone.combination,
        "numbers": numbers,
        "counts": counts,
        "expected": round(expected, 2),
        "rates": [round(c / n, 5) for c in counts],
        "recent_counts": {str(w): v for w, v in recent.items()},
        "recent_window": main_w,
        "omission": {str(k): v for k, v in omissions.items()},
        "hot": [detail(i) for i in hot_idx],
        "cold": [detail(i) for i in cold_idx],
        "chi2": chi_square_uniform(counts, expected),
    }
    if not zone.combination and zone_key == "front":
        # 七星彩按位统计：6 个位置 x 10 个数字
        out["by_position"] = [
            [sum(1 for d in draws if d["front"][pos] == num) for num in numbers]
            for pos in range(zone.size)
        ]
    return out


def analyze_game(game_key: str, windows=WINDOWS):
    game = game_of(game_key)
    draws = load_draws(game_key)
    if len(draws) < 30:
        raise RuntimeError(f"{game.name} 数据不足（{len(draws)} 期），请先运行 fetch")
    structure = (_structure_combination(draws, game) if game.front.combination
                 else _structure_digits(draws, game))
    trend = []
    for d in draws[-TREND_LEN:]:
        trend.append({
            "issue": d["issue"], "date": d["date"],
            "front": d["front"], "back": d["back"],
            "sum": sum(d["front"]),
            "odd": sum(1 for x in d["front"] if x % 2) if game.front.combination else None,
        })
    return {
        "game": game_key,
        "name": game.name,
        "org": game.org,
        "price": game.price,
        "draw_days": game.draw_days,
        "source_desc": game.source_desc,
        "rules": f"{game.front.name} {game.front.size} 个（{game.front.low}~{game.front.high}"
                 + ("，不重复）" if game.front.combination else "，按位可重复）")
                 + f" + {game.back.name} {game.back.size} 个（{game.back.low}~{game.back.high}）",
        "count": len(draws),
        "latest": {"issue": draws[-1]["issue"], "date": draws[-1]["date"],
                   "front": draws[-1]["front"], "back": draws[-1]["back"]},
        "earliest": {"issue": draws[0]["issue"], "date": draws[0]["date"]},
        "windows": list(windows),
        "data_notes": DATA_NOTES.get(game_key, ""),
        "zones": {"front": _zone_analysis(draws, "front", game, windows),
                  "back": _zone_analysis(draws, "back", game, windows)},
        "era_check": {"front": era_check(draws, game, "front"),
                      "back": era_check(draws, game, "back")},
        "structure": structure,
        "trend": trend,
    }


def analyze_all(keys=None):
    keys = keys or list(GAME_ORDER)
    return {k: analyze_game(k) for k in keys}
