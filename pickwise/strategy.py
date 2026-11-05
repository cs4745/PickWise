"""「候选池 → 结构修正 → 复式覆盖」模式（借鉴 2026-10-30 中奖新闻的做法）。

新闻还原与重要前提见 NEWS / NEWS_INFERENCE。
本模块只是把该模式迁移到本项目三个彩种做统计演示：
- 不改变任何一注的中奖概率；
- 复式只是把更多单式打包购买，注数与成本同倍数增加，每元期望不变；
- 新闻原文末尾已有官方提醒：中奖属偶然，AI 选号不能提升中奖概率，切勿跟风模仿。
"""

from __future__ import annotations

import math
import random
from collections import Counter

from .analyze import load_draws
from .config import game_of
from .recommend import _weighted_sample, _weights_for, jackpot_odds

NEWS = {
    "title": "男子借助AI买彩票，中了508万元；本人回应：让AI选出20个号码，根据重号、连号、分布，人工再修正",
    "source": "法治日报综合 / 环球网，2026-10-30（微信公众号转载）",
    "url": "https://mp.weixin.qq.com/s/uruOstnwwWnhWbI3B0mLwA",
    "game": "快乐8 · 选十（第 2026230 期，陕西西安）",
    "facts": [
        "购彩者用 AI 辅助编写选号小程序，先从 80 个号码里选出 20 个。",
        "再按「重号、连号、分布」由人工修正这 20 个候选号。",
        "从候选号中自选 6 组「11 选十」复式票，晚上 8:27 出票，花费 130 多元。",
        "当期全国开出「选十中十」1 注；其中一张票中「选十中十」1 注 +「选十中九」10 注，合计 508 万元。",
    ],
    "official_warning": "本次中奖属于偶然事件，AI 生成彩票号码并不能提升中奖概率，更无法预测开奖结果；"
                        "AI 选号本质上只是随机数字组合，彩票开奖完全随机，不存在可以稳赢的选号方式，切勿迷信 AI 工具、不要盲目跟风模仿。",
}


def news_inference():
    """对新闻中的投注结构做可验算的还原（数字由组合数学推出，非猜测）。"""
    bets_per_ticket = math.comb(11, 10)
    cost_per_ticket = bets_per_ticket * 2
    return {
        "pool_all": 80,
        "pool_picked": 20,
        "pool_ratio": 0.25,
        "groups": 6,
        "ticket_numbers": 11,
        "bets_per_ticket": bets_per_ticket,
        "cost_per_ticket": cost_per_ticket,
        "total_bets": bets_per_ticket * 6,
        "total_cost": cost_per_ticket * 6,
        "checks": [
            "11 码「选十」复式 = C(11,10) = 11 注 × 2 元 = 22 元/组；6 组 = 132 元，与「130 多块钱」吻合。",
            "若开奖 20 个号包含该票 11 个号中的 10 个：去掉未中的 1 个 → 中十 1 注；去掉已中的 10 个之一 → 中九 10 注。"
            "合计 11 注，与「中十 1 注 + 中九 10 注」完全吻合。",
            "由 508 万 − 500 万 = 8 万，反推中九 10 注 × 8000 元/注，奖金结构自洽。",
        ],
        "layers": [
            "第一层 · 缩池：从全号域 80 个按程序评分取 20 个（25%），即「AI 选 20 个」。",
            "第二层 · 人工修正：在候选池内按重号、连号、分布等历史结构形态做筛选。",
            "第三层 · 复式覆盖：从候选池组 6 组 11 码复式，用 66 注覆盖更多组合，而非押 6 注单式。",
        ],
        "honest_note": "这三层都只是「怎么把号挑出来、怎么打包买」，没有一层改变每注的随机概率。"
                       "他中的是全国唯一一注，属于典型的幸存者偏差；同样的买法在其他人身上不会复制这个结果。",
    }


# ---------------------------------------------------------------- 候选池
def _position_weights(draws, zone_key, game, window):
    """排列型选号区：按每个数位的近期出现频率给权重（带拉普拉斯平滑）。"""
    zone = getattr(game, zone_key)
    sub = draws[-window:] if len(draws) > window else draws
    counts = [[1.0] * zone.slots for _ in range(zone.size)]
    for d in sub:
        for pos, v in enumerate(d[zone_key][:zone.size]):
            counts[pos][v - zone.low] += 1
    return [[c / sum(row) for c in row] for row in counts]


def candidate_pool(game_key, draws, window=100, extra=5, back_extra=2, per_position=3):
    """第一层：从全号域缩到候选池（对应新闻里的「AI 选 20 个」）。"""
    game = game_of(game_key)
    out = {}
    for field in ("front", "back"):
        zone = getattr(game, field)
        if zone.combination:
            weights = _weights_for(draws, field, game, "balanced", window)
            k = min(zone.slots, zone.size + (extra if field == "front" else back_extra))
            ranked = sorted(zone.numbers, key=lambda n: (-weights[n - zone.low], n))[:k]
            out[field] = {"numbers": sorted(ranked), "by_position": False,
                          "weights": [weights[n - zone.low] for n in sorted(ranked)]}
        else:
            wrows = _position_weights(draws, field, game, window)
            per_pos = []
            for row in wrows:
                k = min(zone.slots, per_position)
                ranked = sorted(zone.numbers, key=lambda n: (-row[n - zone.low], n))[:k]
                per_pos.append(sorted(ranked))
            out[field] = {"numbers": per_pos, "by_position": True,
                          "weights": wrows}
    out["front_all"] = game.front.slots
    out["back_all"] = game.back.slots
    return out


# ---------------------------------------------------------------- 结构修正
def _structure_of(front, prev, game):
    if not game.front.combination:
        return {
            "sum": sum(front),
            "repeat": sum(1 for a, b in zip(front, prev) if a == b),
            "consecutive": sum(1 for a, b in zip(front, front[1:]) if abs(a - b) == 1),
            "third_ratio": None,
            "odd": None,
        }
    third = game.front.slots / 3
    thirds = tuple(sum(1 for x in front if third * i <= x - game.front.low < third * (i + 1))
                   for i in range(3))
    return {
        "sum": sum(front),
        "odd": sum(1 for x in front if x % 2),
        "repeat": len(set(front) & set(prev)),
        "consecutive": sum(1 for a, b in zip(front, front[1:]) if b - a == 1),
        "third_ratio": f"{thirds[0]}:{thirds[1]}:{thirds[2]}",
    }


def _passes_structure(st, game, p10, p90, require_consecutive):
    if not (p10 <= st["sum"] <= p90):
        return False
    size = game.front.size
    if game.front.combination:
        if not (1 <= st["odd"] <= size - 1):
            return False
        if max(int(x) for x in st["third_ratio"].split(":")) > size - 2:
            return False
    if st["repeat"] > 2:                       # 重号：不超过 2 个
        return False
    if require_consecutive and st["consecutive"] == 0:   # 连号：部分组合要求含连号
        return False
    return True


def _sample_single(game, pool, rng, field):
    zone = getattr(game, field)
    p = pool[field]
    if p["by_position"]:
        return [rng.choices(pos, weights=[p["weights"][i][n - zone.low] for n in pos], k=1)[0]
                for i, pos in enumerate(p["numbers"])]
    return sorted(_weighted_sample(rng, p["numbers"], p["weights"], zone.size))


# ---------------------------------------------------------------- 主流程
def news_strategy(game_key, groups=6, expand=2, window=100, seed=20261105, draws=None):
    """生成「单式 + 复式」推荐，并给出注数、金额与理论概率。"""
    game = game_of(game_key)
    draws = draws if draws is not None else load_draws(game_key)
    if len(draws) < 60:
        raise RuntimeError("历史数据不足，请先运行 fetch")
    rng = random.Random(seed)
    pool = candidate_pool(game_key, draws, window=window)
    sums = sorted(sum(d["front"]) for d in draws)
    p10, p90 = sums[int(len(sums) * .1)], sums[int(len(sums) * .9)]
    prev = draws[-1]["front"]

    # 第二层：结构修正（重号 / 连号 / 分布 / 和值），对应「人工再修正」
    singles, seen, back_used = [], set(), Counter()
    # 分级放宽：优先完整结构约束；若某组在约束下凑不出，逐步放宽连号 / 后区重复 / 和值区间，
    # 保证任意种子与窗口下都能稳定产出 groups 组（候选池组合数远大于 groups）。
    for i in range(groups):
        picked = None
        for relax in range(4):
            lo = p10 - (p90 - p10) if relax >= 2 else p10
            hi = p90 + (p90 - p10) if relax >= 2 else p90
            for _ in range(400):
                f = _sample_single(game, pool, rng, "front")
                b = _sample_single(game, pool, rng, "back")
                key = (tuple(f), tuple(b))
                if key in seen:
                    continue
                st = _structure_of(f, prev, game)
                if relax < 3 and not _passes_structure(
                        st, game, lo, hi,
                        require_consecutive=(i % 2 == 0 and relax == 0)):
                    continue
                if relax == 0 and back_used[tuple(b)] >= 2:
                    continue
                picked = (f, b, st, key)
                break
            if picked:
                break
        if not picked:
            continue
        f, b, st, key = picked
        seen.add(key)
        back_used[tuple(b)] += 1
        singles.append({
            "index": len(singles) + 1,
            "front": f, "back": b,
            "front_text": " ".join(f"{x:02d}" for x in f),
            "back_text": " ".join(f"{x:02d}" for x in b),
            "structure": st,
        })

    # 第三层：复式覆盖
    if game.front.combination:
        mf = min(game.front.slots, game.front.size + expand)
        mb = min(game.back.slots, game.back.size + 1)
        fnums = pool["front"]["numbers"]
        fset = sorted(sorted(fnums, key=lambda n: (-pool["front"]["weights"][fnums.index(n)], n))[:mf])
        bnums = pool["back"]["numbers"]
        bset = sorted(sorted(bnums, key=lambda n: (-pool["back"]["weights"][bnums.index(n)], n))[:mb])
        bets = math.comb(len(fset), game.front.size) * math.comb(len(bset), game.back.size)
        total_combos = (math.comb(game.front.slots, game.front.size)
                        * math.comb(game.back.slots, game.back.size))
        multi = {
            "front": fset, "back": bset,
            "front_text": " ".join(f"{x:02d}" for x in fset),
            "back_text": " ".join(f"{x:02d}" for x in bset),
            "bets": bets, "cost": bets * game.price,
            "formula": f"C({len(fset)},{game.front.size}) × C({len(bset)},{game.back.size}) = {bets} 注",
            "odds": f"{bets} / {total_combos:,}",
            "coverage": f"{game.front.name} {len(fset)} 码 + {game.back.name} {len(bset)} 码",
        }
    else:
        # 排列型：定位复式，扩展 expand 个数位（每位 2 个候选），特别位固定 1 个
        frows = []
        for i, pos in enumerate(pool["front"]["numbers"]):
            take = 2 if i < expand else 1
            frows.append(sorted(pos, key=lambda n: (-pool["front"]["weights"][i][n - game.front.low], n))[:take])
        brow = sorted(pool["back"]["numbers"][0],
                      key=lambda n: -pool["back"]["weights"][0][n - game.back.low])[:1]
        bets = math.prod(len(r) for r in frows) * len(brow)
        total_combos = (game.front.slots ** game.front.size) * game.back.slots
        multi = {
            "front": frows, "back": brow,
            "front_text": " · ".join(f"第{i + 1}位 {'/'.join(str(x) for x in row)}"
                                    for i, row in enumerate(frows)),
            "back_text": " ".join(f"{x:02d}" for x in brow),
            "bets": bets, "cost": bets * game.price,
            "formula": " × ".join(str(len(r)) for r in frows) + f" × {len(brow)} = {bets} 注",
            "odds": f"{bets} / {total_combos:,}",
            "coverage": f"前 {expand} 位各双选 + 其余位单选 + 特别位 {brow[0]}",
        }

    single_bets = len(singles)
    base_odds = jackpot_odds(game_key)
    cost_table = [
        {"label": "单式 1 注", "bets": 1, "cost": game.price, "multiple": 1},
        {"label": f"单式 {single_bets} 组", "bets": single_bets,
         "cost": single_bets * game.price, "multiple": single_bets},
        {"label": f"复式（{multi['coverage']}）", "bets": multi["bets"],
         "cost": multi["cost"], "multiple": multi["bets"]},
    ]
    return {
        "game": game_key,
        "name": game.name,
        "seed": seed,
        "window": window,
        "pool": {
            "front": pool["front"]["numbers"],
            "back": pool["back"]["numbers"],
            "front_all": pool["front_all"],
            "back_all": pool["back_all"],
            "by_position": pool["front"]["by_position"],
        },
        "singles": singles,
        "multiple": multi,
        "base_odds": base_odds,
        "cost_table": cost_table,
        "price": game.price,
        "notice": "复式把注数与成本同倍数放大，中奖概率也同倍数放大，但每一注的期望回报不变；"
                  "它只是打包买更多组合，不是更聪明的选号。新闻中的中奖属偶然事件，不可复制。",
        "layers": [
            f"缩池：{game.front.name} {pool['front_all']} 个 → 候选 {len(pool['front']['numbers'])} 个"
            if not pool["front"]["by_position"] else
            f"缩池：前六位每位 10 个数字 → 每位候选 {len(pool['front']['numbers'][0])} 个",
            "人工修正：按重号 ≤2、连号形态、区间分布、和值 10%~90% 分位筛选",
            f"打包：{len(singles)} 组单式 + 1 组复式（{multi['bets']} 注）",
        ],
    }


def news_strategy_all(keys=None, **kwargs):
    keys = keys or ("ssq", "dlt", "qxc")
    return {k: news_strategy(k, **kwargs) for k in keys}
