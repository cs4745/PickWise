"""快乐 8「选十」：官方奖级数学、理论返奖率，以及新闻模式的原玩法复刻。

规则来源：中国福彩网《中国福利彩票快乐8游戏规则》
https://www.cwl.gov.cn/html5/fcpz/yxjs/kl8/
- 从 1~80 中选 1~10 个号码投注，每注 2 元；每期开出 20 个号码。
- 选十奖级：中10 最高 500 万（浮动）、中9 8000、中8 720、中7 80、中6 5、中5 3、中0 2。
- 彩票奖金按销售额 58% 计提（57% 当期奖金 + 1% 调节基金）。
"""

from __future__ import annotations

import math
import random

from .analyze import load_draws
from .config import game_of
from .recommend import _weighted_sample, _weights_for


def prize_math(game_key="kl8"):
    """按超几何分布计算各命中个数的概率、期望奖金与理论返奖率。"""
    g = game_of(game_key)
    n_all, n_draw, pick = g.front.slots, g.front.size, g.pick_size
    total = math.comb(n_all, pick)
    rows, expected = [], 0.0
    for k in range(pick + 1):
        p = math.comb(n_draw, k) * math.comb(n_all - n_draw, pick - k) / total
        money = g.prize_map.get(k, 0)
        expected += p * money
        level = next((label for h, _, label in g.prize_levels if h == k), "未中奖")
        rows.append({
            "hits": k,
            "label": f"中{k}",
            "level": level,
            "probability": p,
            "odds": f"1 / {round(1 / p):,}" if p > 0 else "—",
            "prize": money,
            "contribution": round(p * money, 6),
        })
    return {
        "rows": rows,
        "total_combos": total,
        "jackpot_odds": f"1 / {round(1 / rows[pick]['probability']):,}",
        "expected_prize": round(expected, 6),
        "price": g.price,
        "return_rate": round(expected / g.price * 100, 4),
        "official_rate": 58.0,
        "official_note": g.prize_note,
        "note": "理论期望奖金 ≈ ¥%.4f / 注，返奖率 ≈ %.2f%%；与官方「57%% 当期奖金 + 1%% 调节基金」口径一致，"
                "差额来自调节基金与浮动奖封顶。长期期望为负，购买越多亏损越接近确定。"
                % (expected, expected / g.price * 100),
    }


def prize_for_hits(game_key, hits):
    return game_of(game_key).prize_map.get(hits, 0)


# ---------------------------------------------------------------- 新闻模式（原玩法复刻）
def _pool_structure(pick, prev):
    """对应新闻里的「重号、连号、分布」人工修正。"""
    thirds = tuple(sum(1 for x in pick if 20 * i < x <= 20 * (i + 1)) for i in range(4))
    return {
        "sum": sum(pick),
        "repeat": len(set(pick) & set(prev)),          # 与上期 20 个开奖号的重叠数
        "consecutive": sum(1 for a, b in zip(pick, pick[1:]) if b - a == 1),
        "four_zone": f"{thirds[0]}:{thirds[1]}:{thirds[2]}:{thirds[3]}",
        "odd": sum(1 for x in pick if x % 2),
    }


def _passes(st, require_consecutive=True):
    parts = [int(x) for x in st["four_zone"].split(":")]
    return (
        0 <= st["repeat"] <= 5          # 重号：独立随机的期望为 2.5
        and (not require_consecutive or st["consecutive"] >= 1)
        and min(parts) >= 1             # 分布：四个 20 号区间都至少覆盖 1 个
        and max(parts) <= 5
        and 1 <= st["odd"] <= 9
    )


def news_strategy_pool(game_key="kl8", groups=6, window=100, seed=20261105, draws=None):
    """完全按新闻结构复刻：80 → 20 候选 → 人工修正 → 6 组 11 码选十复式（66 注 / ¥132）。"""
    g = game_of(game_key)
    draws = draws if draws is not None else load_draws(game_key)
    if len(draws) < 60:
        raise RuntimeError("历史数据不足，请先运行 fetch")
    rng = random.Random(seed)
    weights = _weights_for(draws, "front", g, "balanced", window)
    # 第一层：80 个号缩到 20 个候选（25%，与新闻完全一致）
    pool = sorted(sorted(g.front.numbers, key=lambda n: (-weights[n - g.front.low], n))[:20])
    prev = draws[-1]["front"]
    pw = [weights[n - g.front.low] for n in pool]

    # 第二层：重号 / 连号 / 分布修正，生成 6 组单式（每组选 10 个）
    singles, seen = [], set()
    for i in range(groups):
        for relax in range(3):
            for _ in range(400):
                pick = sorted(_weighted_sample(rng, pool, pw, g.pick_size))
                key = tuple(pick)
                if key in seen:
                    continue
                st = _pool_structure(pick, prev)
                if relax < 2 and not _passes(st, require_consecutive=(i % 2 == 0 and relax == 0)):
                    continue
                seen.add(key)
                singles.append({
                    "index": len(singles) + 1,
                    "front": pick, "back": [],
                    "front_text": " ".join(f"{x:02d}" for x in pick),
                    "back_text": "",
                    "structure": st,
                })
                break
            if len(singles) > i:
                break

    # 第三层：6 组 11 码「选十」复式 —— 与新闻中「自己又选了 6 组 11 选十」一致
    groups_out, used = [], set()
    for i in range(groups):
        for _ in range(200):
            eleven = sorted(_weighted_sample(rng, pool, pw, 11))
            key = tuple(eleven)
            if key in used:
                continue
            used.add(key)
            groups_out.append({
                "index": i + 1,
                "numbers": eleven,
                "text": " ".join(f"{x:02d}" for x in eleven),
                "bets": math.comb(11, 10),
                "cost": math.comb(11, 10) * g.price,
            })
            break

    bets_per = math.comb(11, 10)
    total_bets = bets_per * groups
    total_cost = total_bets * g.price
    total_combos = math.comb(g.front.slots, g.pick_size)
    pmath = prize_math(game_key)

    # 主推复式 = 第 1 组 11 码
    multi = {
        "front": groups_out[0]["numbers"] if groups_out else pool[:11],
        "back": [],
        "front_text": groups_out[0]["text"] if groups_out else "",
        "back_text": "",
        "bets": bets_per,
        "cost": bets_per * g.price,
        "formula": f"C(11,10) = {bets_per} 注",
        "odds": f"{bets_per} / {total_combos:,}",
        "coverage": "11 码选十复式",
    }
    return {
        "game": game_key,
        "name": g.name,
        "seed": seed,
        "window": window,
        "is_pool": True,
        "pool": {
            "front": pool, "back": [], "front_all": g.front.slots,
            "back_all": 0, "by_position": False, "pool_size": len(pool),
        },
        "singles": singles,
        "multiple": multi,
        "multiple_groups": groups_out,
        "total_bets": total_bets,
        "total_cost": total_cost,
        "news_match": total_cost == 132 and total_bets == 66,
        "base_odds": pmath["jackpot_odds"],
        "cost_table": [
            {"label": "单式 1 注", "bets": 1, "cost": g.price, "multiple": 1},
            {"label": f"单式 {len(singles)} 组", "bets": len(singles),
             "cost": len(singles) * g.price, "multiple": len(singles)},
            {"label": "1 组 11 码复式", "bets": bets_per,
             "cost": bets_per * g.price, "multiple": bets_per},
            {"label": f"{groups} 组 11 码复式（新闻同款）", "bets": total_bets,
             "cost": total_cost, "multiple": total_bets},
        ],
        "price": g.price,
        "notice": "6 组 11 码复式 = 66 注 = ¥132，与新闻中「130 多块钱」完全对应。"
                  "但注数、成本、概率同倍数放大，每注期望奖金恒为 ¥%.4f（返奖率 %.2f%%），"
                  "没有任何技巧优势；新闻中的中奖是偶然事件。" % (pmath["expected_prize"], pmath["return_rate"]),
        "layers": [
            f"缩池：1~{g.front.slots} 共 {g.front.slots} 个号 → 按统计评分取 {len(pool)} 个候选（25%，与新闻一致）",
            "人工修正：按与上期重号 0~5、含连号、四个 20 号区间各至少 1 个、奇偶比筛选",
            f"打包：{len(singles)} 组单式 + {len(groups_out)} 组 11 码复式（共 {total_bets} 注 ¥{total_cost}）",
        ],
    }
