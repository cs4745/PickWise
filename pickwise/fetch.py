"""历史开奖数据采集、交叉校验与增量更新。

数据源均为公开开奖公告，详见 config.py 的 source_desc。
采集结果落地为 data/<game>.csv，并生成 data/validation.json 记录校验与哈希。
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import re
import ssl
import time
import urllib.error
import urllib.request

from .config import (
    CWL500_API,
    CWL500_HEADERS,
    CWL_API,
    CWL_HEADERS,
    DATA_DIR,
    DLT500_API,
    DLT500_HEADERS,
    GAMES,
    REQUEST_INTERVAL,
    REQUEST_RETRIES,
    REQUEST_TIMEOUT,
    SPORTTERY_API,
    SPORTTERY_GAME_NO,
    SPORTTERY_HEADERS,
    game_of,
)

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def http_get(url: str, headers: dict, encoding: str = "utf-8") -> str:
    """带重试与限速的 GET，返回解码后的文本。"""
    last = None
    for attempt in range(REQUEST_RETRIES):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=_SSL_CTX) as resp:
                raw = resp.read()
            time.sleep(REQUEST_INTERVAL)
            return raw.decode(encoding, "replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(1.0 + attempt)
    raise RuntimeError(f"请求失败（重试 {REQUEST_RETRIES} 次）: {url}\n{last}")


def issue_sort_key(issue: str):
    """期号排序键，兼容 2026126（福彩）与 26126（体彩）。"""
    s = str(issue).strip()
    if len(s) >= 7:
        return (int(s[:4]), int(s[4:]))
    if len(s) >= 5:
        yy = int(s[:2])
        return (1900 + yy if yy >= 90 else 2000 + yy, int(s[2:]))
    return (0, int(s or 0))


def normalize_issue(issue: str, game_key: str) -> str:
    s = str(issue).strip()
    if game_key == "ssq" and len(s) == 5:
        # 500 彩票网早期用 03001，福彩官方用 2003001，统一为 7 位
        return "20" + s
    return s


def clean_date(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(text))
    if not m:
        return ""
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def _nums(text: str):
    return [int(x) for x in re.findall(r"\d+", str(text))]


def make_draw(game_key, issue, date, front, back, source):
    g = game_of(game_key)
    return {
        "issue": normalize_issue(issue, game_key),
        "date": clean_date(date),
        "front": sorted(int(x) for x in front) if g.front.combination else [int(x) for x in front],
        "back": sorted(int(x) for x in back) if g.back.combination else [int(x) for x in back],
        "source": source,
    }


# ------------------------------------------------------------------ 各数据源
def fetch_cwl_official(max_pages: int | None = None, stop_at: set | None = None):
    """中国福彩网双色球开奖公告（含日期）。返回 (draws, 停止原因)。"""
    out, reason = [], "complete"
    page = 1
    limit = max_pages or 30
    while page <= limit:
        data = json.loads(http_get(CWL_API.format(page=page), CWL_HEADERS))
        rows = data.get("result") or []
        if not rows:
            reason = "empty"
            break
        hit_old = False
        for r in rows:
            issue = normalize_issue(r.get("code", ""), "ssq")
            if stop_at and issue in stop_at:
                hit_old = True
                continue
            out.append(
                make_draw(
                    "ssq", issue, r.get("date"),
                    str(r.get("red", "")).split(","), [r.get("blue", "")],
                    "中国福彩网",
                )
            )
        total_pages = int(data.get("pageNum") or data.get("pages") or 0)
        if hit_old:
            reason = "incremental_stop"
            break
        if total_pages and page >= total_pages:
            break
        page += 1
    return out, reason


def fetch_500_ssq():
    """500 彩票网双色球全量历史（2003 年首期起，无开奖日期）。"""
    html = http_get(CWL500_API, CWL500_HEADERS, encoding="gb18030")
    out = []
    for row in re.findall(r"<tr[^>]*class=[\"']?t_tr1[\"']?[^>]*>(.*?)</tr>", html, re.S):
        tds = [re.sub(r"<[^>]+>", "", x).replace("&nbsp;", "").strip()
               for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(tds) < 9 or not re.fullmatch(r"\d{5}", tds[1]):
            continue
        reds = [int(x) for x in tds[2:8] if x.isdigit()]
        blues = [int(x) for x in tds[8:9] if x.isdigit()]
        if len(reds) != 6 or len(blues) != 1:
            continue
        out.append(make_draw("ssq", tds[1], "", reds, blues, "500彩票网"))
    return out


def fetch_500_dlt():
    """500 彩票网大乐透全量历史，用于与体彩官方数据逐期交叉校验。"""
    html = http_get(DLT500_API, DLT500_HEADERS, encoding="gb18030")
    out = []
    for row in re.findall(r"<tr[^>]*class=[\"']?t_tr1[\"']?[^>]*>(.*?)</tr>", html, re.S):
        tds = [re.sub(r"<[^>]+>", "", x).replace("&nbsp;", "").strip()
               for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(tds) < 9 or not re.fullmatch(r"\d{5}", tds[1]):
            continue
        front = [int(x) for x in tds[2:7] if x.isdigit()]
        back = [int(x) for x in tds[7:9] if x.isdigit()]
        if len(front) != 5 or len(back) != 2:
            continue
        out.append(make_draw("dlt", tds[1], "", front, back, "500彩票网"))
    return out


def fetch_sporttery(game_key: str, max_pages: int | None = None, stop_at: set | None = None):
    """中国体育彩票 webapi 历史开奖（大乐透 / 七星彩，含日期）。"""
    game_no = SPORTTERY_GAME_NO[game_key]
    out, reason = [], "complete"
    page = 1
    limit = max_pages or 60
    total_pages = None
    while page <= limit:
        data = json.loads(http_get(SPORTTERY_API.format(game_no=game_no, page=page), SPORTTERY_HEADERS))
        value = data.get("value") or {}
        rows = value.get("list") or []
        if total_pages is None:
            total = int(value.get("total") or 0)
            total_pages = max(1, (total + 99) // 100)
        if not rows:
            reason = "empty"
            break
        hit_old = False
        for r in rows:
            issue = str(r.get("lotteryDrawNum", "")).strip()
            if stop_at and issue in stop_at:
                hit_old = True
                continue
            nums = _nums(r.get("lotteryDrawResult", ""))
            g = game_of(game_key)
            size = g.front.size
            if len(nums) != size + g.back.size:
                continue
            out.append(make_draw(game_key, issue, r.get("lotteryDrawTime"),
                                 nums[:size], nums[size:], "中国体育彩票"))
        if hit_old:
            reason = "incremental_stop"
            break
        if page >= total_pages:
            break
        page += 1
    return out, reason


# ------------------------------------------------------------------ 本地读写
CSV_FIELDS = ["issue", "date", "front", "back", "source"]


def read_csv(game_key: str):
    path = game_of(game_key).csv_path
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                out.append({
                    "issue": row["issue"].strip(),
                    "date": row.get("date", "").strip(),
                    "front": _nums(row["front"]),
                    "back": _nums(row["back"]),
                    "source": row.get("source", "").strip(),
                })
            except (ValueError, KeyError):
                continue
    return out


def write_csv(game_key: str, draws):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = game_of(game_key).csv_path
    rows = sorted(draws, key=lambda d: issue_sort_key(d["issue"]), reverse=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for d in rows:
            w.writerow({
                "issue": d["issue"],
                "date": d["date"],
                "front": " ".join(f"{x:02d}" for x in d["front"]),
                "back": " ".join(f"{x:02d}" for x in d["back"]),
                "source": d["source"],
            })
    return rows


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ 校验
def validate_draws(game_key: str, draws):
    """返回 (errors, warnings)。严格检查号域、个数、重复、期号唯一性。"""
    g = game_of(game_key)
    errors, warnings = [], []
    seen = set()
    for d in draws:
        tag = d["issue"]
        if tag in seen:
            errors.append(f"{tag}: 期号重复")
        seen.add(tag)
        for zone_key, zone in (("front", g.front), ("back", g.back)):
            vals = d[zone_key]
            if len(vals) != zone.size:
                errors.append(f"{tag}: {zone.name}个数 {len(vals)} != {zone.size}")
                continue
            if any(v < zone.low or v > zone.high for v in vals):
                errors.append(f"{tag}: {zone.name}越界 {vals}")
            if zone.combination:
                if len(set(vals)) != len(vals):
                    errors.append(f"{tag}: {zone.name}存在重复 {vals}")
                if vals != sorted(vals):
                    errors.append(f"{tag}: {zone.name}未升序 {vals}")
        if d["date"]:
            try:
                dt.date.fromisoformat(d["date"])
            except ValueError:
                warnings.append(f"{tag}: 日期格式异常 {d['date']}")
        else:
            warnings.append(f"{tag}: 缺少开奖日期（数据源未提供）")
    return errors, warnings


def cross_check(official, third_party):
    """双色球两个数据源重叠期号逐期比对号码。"""
    idx = {d["issue"]: d for d in third_party}
    conflicts, checked = [], 0
    for d in official:
        other = idx.get(d["issue"])
        if not other:
            continue
        checked += 1
        if d["front"] != other["front"] or d["back"] != other["back"]:
            conflicts.append({
                "issue": d["issue"],
                "官方": {"front": d["front"], "back": d["back"]},
                "第三方": {"front": other["front"], "back": other["back"]},
            })
    return {"checked": checked, "conflicts": conflicts[:20], "conflict_count": len(conflicts)}


def merge_draws(*groups):
    """按期号合并，靠前的分组优先级更高。"""
    merged = {}
    for group in groups:
        for d in group:
            merged.setdefault(d["issue"], d)
    return list(merged.values())


# ------------------------------------------------------------------ 主流程
def fetch_game(game_key: str, full: bool = True, verbose: bool = True):
    local = read_csv(game_key)
    local_issues = {d["issue"] for d in local}
    new_draws, extra = [], {}
    reason = "full"

    if game_key == "ssq":
        official, reason = fetch_cwl_official(
            max_pages=None if full else 5,
            stop_at=None if full else local_issues,
        )
        # 早期数据（2003-2012）只在全量采集或本地无数据时补齐
        if full or not local:
            third = fetch_500_ssq()
            extra["cross_check"] = cross_check(official, third)
            official = merge_draws(official, third)  # 官方优先
            extra["source_rows"] = {"中国福彩网": len([d for d in official if d["source"] == "中国福彩网"]),
                                    "500彩票网": len([d for d in official if d["source"] == "500彩票网"])}
        new_draws = official
    else:
        new_draws, reason = fetch_sporttery(
            game_key,
            max_pages=None if full else 5,
            stop_at=None if full else local_issues,
        )
        if game_key == "dlt" and full:
            # 官方数据已覆盖全量，第三方仅用于逐期交叉校验，不覆盖官方结果
            third = fetch_500_dlt()
            extra["cross_check"] = cross_check(new_draws, third)
            extra["source_rows"] = {"中国体育彩票": len(new_draws), "500彩票网(仅校验)": len(third)}

    all_draws = merge_draws(new_draws, local)
    errors, warnings = validate_draws(game_key, all_draws)
    if errors:
        raise RuntimeError(f"{game_key} 数据校验失败（{len(errors)} 项）:\n" + "\n".join(errors[:10]))
    rows = write_csv(game_key, all_draws)
    info = {
        "game": game_key,
        "name": game_of(game_key).name,
        "count": len(rows),
        "new_rows": len(all_draws) - len(local),
        "latest": rows[0] if rows else None,
        "earliest": rows[-1] if rows else None,
        "mode": "full" if full else "incremental",
        "stop_reason": reason,
        "validation_errors": len(errors),
        "validation_warnings": len(warnings),
        "warning_sample": warnings[:3],
        "sha256": file_sha256(game_of(game_key).csv_path),
    }
    info.update(extra)
    if verbose:
        src = f"，交叉校验 {extra['cross_check']['checked']} 期/冲突 {extra['cross_check']['conflict_count']} 期" if "cross_check" in extra else ""
        print(f"  [{game_of(game_key).name}] {len(rows)} 期（新增 {info['new_rows']}），"
              f"{rows[-1]['issue']} ~ {rows[0]['issue']}{src}")
    return info


def fetch_all(keys, full: bool = True, verbose: bool = True):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "fetched_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": "full" if full else "incremental",
        "games": {},
        "sources": {k: GAMES[k].source_desc for k in keys},
    }
    for key in keys:
        report["games"][key] = fetch_game(key, full=full, verbose=verbose)
    path = DATA_DIR / "validation.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if verbose:
        print(f"  数据校验报告: {path}")
    return report
