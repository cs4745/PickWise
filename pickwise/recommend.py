"""参考组合生成（娱乐性统计演示，不是预测、不是投注建议）。

所谓「热号 / 冷号 / 回补」只是对历史频率的不同加权方式。
每期开奖相互独立，任何加权都不改变下一期的中奖概率；
本模块同时提供纯随机对照组，用于说明这一点。
"""

from __future__ import annotations

import math
import random
import statistics
from collections import Counter

from .analyze import load_draws, zone_counts
from .config import GAMES, game_of

STRATEGIES = {
    "balanced": {"label": "均衡", "recent": 0.35, "long": 0.15, "omission": 0.20, "noise": 0.30,
                 "desc": "近期频率、长期频率与遗漏值混合加权，并用常见结构约束筛选"},
    "hot": {"label": "热号", "recent": 0.70, "long": 0.20, "omission": 0.00, "noise": 0.10,
            "desc": "偏向近期出现频率高的号码（追热，属于赌徒谬误）"},
    "cold": {"label": "冷号", "recent": -0.60, "long": -0.10, "omission": 0.60, "noise": 0.20,
             "desc": "偏向近期低频、长期遗漏的号码（赌回补，同样属于赌徒谬误）"},
    "random": {"label": "随机", "recent": 0.00, "long": 0.00, "omission": 0.00, "noise": 1.00,
               "desc": "完全均匀随机，作为对照基线；其数学期望与任何策略完全相同"},
}


def jackpot_odds(game_key: str) -> str:
    g = game_of(game_key)
    if g.front.combination:
        total = math.comb(g.front.slots, g.front.size) * math.comb(g.back.slots, g.back.size)
    else:
        total = (g.front.slots ** g.front.size) * (g.back.slots ** g.back.size)
    return f"1 / {total:,}"


def _z(values):
    mean = statistics.mean(values)
    sd = statistics.pstdev(values) or 1.0
    return [(v - mean) / sd for v in values]


def _weights_for(draws, zone_key, game, strategy: str, window: int):
    zone = getattr(game, zone_key)
    # 对照基线必须是严格均匀，不能混入任何历史统计信息
    if strategy == "random":
        return [1.0 / zone.slots] * zone.slots
    sub = draws[-window:] if len(draws) > window else draws
    recent = zone_counts(sub, zone_key, game)
    long = zone_counts(draws, zone_key, game)
    exp_recent = len(sub) * zone.size / zone.slots
    exp_long = len(draws) * zone.size / zone.slots
    # 当前遗漏：单次线性扫描记录每个号码最后一次出现的位置
    last_seen = {n: 0 for n in zone.numbers}
    for idx, d in enumerate(draws):
        for v in d[zone_key]:
            last_seen[v] = idx
    omissions = [len(draws) - 1 - last_seen[n] for n in zone.numbers]
    zo = _z(omissions)
    cfg = STRATEGIES[strategy]
    raw = []
    for i in range(len(zone.numbers)):
        base = (cfg["recent"] * (recent[i] - exp_recent) / max(1.0, math.sqrt(exp_recent))
                + cfg["long"] * (long[i] - exp_long) / max(1.0, math.sqrt(exp_long))
                + cfg["omission"] * zo[i] * 0.4)
        # softmax 风格平移，保证权重为正
        raw.append(math.exp(max(-8, min(8, base))))
    total = sum(raw)
    soft = [r / total for r in raw]
    # noise 表示「混入均匀随机」的比例，而非使用与频率相关的伪噪声
    uniform = 1.0 / zone.slots
    return [(1 - cfg["noise"]) * w + cfg["noise"] * uniform for w in soft]


def _weighted_sample(rng, numbers, weights, k, replace=False):
    chosen, pool, w = [], list(numbers), list(weights)
    for _ in range(k):
        if not pool:
            break
        pick = rng.choices(pool, weights=w, k=1)[0]
        chosen.append(pick)
        if not replace:
            i = pool.index(pick)
            pool.pop(i)
            w.pop(i)
    return chosen


def _structure_filter(front, structure):
    if not structure or structure.get("type") != "combination":
        return True
    s = structure["sum"]
    if not (s["p10"] <= sum(front) <= s["p90"]):
        return False
    odd = sum(1 for x in front if x % 2)
    if not (1 <= odd <= len(front) - 1):
        return False
    if max(front) - min(front) < len(front) + 2:
        return False
    return True


def generate_one(game_key, strategy, draws, rng, window=100, structure=None,
                 use_filter=True, weights=None):
    game = game_of(game_key)
    if weights is None:
        weights = (_weights_for(draws, "front", game, strategy, window),
                   _weights_for(draws, "back", game, strategy, window))
    wf, wb = weights

    front, back = None, None
    for attempt in range(300):
        if game.front.combination:
            f = sorted(_weighted_sample(rng, game.front.numbers, wf, game.front.size))
        else:
            f = _weighted_sample(rng, game.front.numbers, wf, game.front.size, replace=True)
        if not use_filter or _structure_filter(f, structure):
            front = f
            break
    if front is None:
        front = _weighted_sample(rng, game.front.numbers, wf, game.front.size,
                                 replace=not game.front.combination)
        if game.front.combination:
            front = sorted(front)
    if game.back.combination:
        back = sorted(_weighted_sample(rng, game.back.numbers, wb, game.back.size))
    else:
        back = _weighted_sample(rng, game.back.numbers, wb, game.back.size, replace=True)
    return front, back


def _reason(game_key, strategy, front, back, draws, window):
    game = game_of(game_key)
    sub = draws[-window:]
    fcount = Counter(v for d in sub for v in d["front"])
    hot = set(n for n, _ in fcount.most_common(max(1, game.front.slots // 3)))
    cold = set(n for n, _ in sorted(fcount.items(), key=lambda kv: kv[1])[:max(1, game.front.slots // 3)])
    hot_hit = [x for x in front if x in hot]
    cold_hit = [x for x in front if x in cold] if game.front.combination else []
    parts = [f"{STRATEGIES[strategy]['label']}策略：近 {len(sub)} 期热号命中 {len(hot_hit)} 个"]
    if game.front.combination:
        parts.append(f"冷号 {len(cold_hit)} 个，和值 {sum(front)}")
        parts.append(f"奇偶 {sum(1 for x in front if x % 2)}:{len(front) - sum(1 for x in front if x % 2)}")
    else:
        parts.append(f"数字和 {sum(front)}")
    parts.append(f"一等奖理论概率 {jackpot_odds(game_key)}")
    return "；".join(parts)


def recommend(game_key, strategy="balanced", count=5, seed=20261105, window=100, draws=None):
    """返回若干组参考号码。"""
    if strategy not in STRATEGIES:
        raise ValueError(f"未知策略 {strategy}，可选 {', '.join(STRATEGIES)}")
    draws = draws if draws is not None else load_draws(game_key)
    if len(draws) < 60:
        raise RuntimeError("历史数据不足，请先运行 fetch")
    game = game_of(game_key)
    # 结构约束基于全量历史（仅用于让组合看起来符合常见形态，不改变中奖概率）
    sums = [sum(d["front"]) for d in draws]
    ss = sorted(sums)
    structure = {"type": "combination" if game.front.combination else "digits",
                 "sum": {"p10": ss[int(len(ss) * .1)], "p90": ss[int(len(ss) * .9)]}}
    rng = random.Random(seed)
    out = []
    for i in range(count):
        front, back = generate_one(game_key, strategy, draws, rng, window, structure,
                                   use_filter=(strategy != "random"))
        out.append({
            "index": i + 1,
            "front": front,
            "back": back,
            "front_text": " ".join(f"{x:02d}" for x in front),
            "back_text": " ".join(f"{x:02d}" for x in back),
            "reason": _reason(game_key, strategy, front, back, draws, window),
        })
    return {
        "game": game_key,
        "name": game.name,
        "strategy": strategy,
        "strategy_label": STRATEGIES[strategy]["label"],
        "strategy_desc": STRATEGIES[strategy]["desc"],
        "seed": seed,
        "window": window,
        "jackpot_odds": jackpot_odds(game_key),
        "combos": out,
        "notice": "以上号码由历史统计加权随机生成，仅供娱乐。每注中奖概率与其他任何号码完全相同。",
    }


def recommend_all(keys=None, strategy="balanced", count=5, seed=20261105):
    keys = keys or list(GAMES)
    return {k: recommend(k, strategy=strategy, count=count, seed=seed) for k in keys}
