"""彩种规则、号域与数据源配置。"""

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"


@dataclass(frozen=True)
class Zone:
    """一个选号区。

    combination=True  -> 组合型：号码不重复、升序排列（红球 / 前区 / 后区）
    combination=False -> 排列型：按位独立、数字可重复（七星彩各数位）
    """

    key: str
    name: str
    size: int
    low: int
    high: int
    combination: bool

    @property
    def numbers(self):
        return list(range(self.low, self.high + 1))

    @property
    def slots(self):
        """该区的取值个数（理论概率分母用）。"""
        return self.high - self.low + 1


@dataclass(frozen=True)
class Game:
    key: str
    name: str
    short: str
    org: str
    front: Zone
    back: Zone
    price: int
    draw_days: str
    source_desc: str
    mode: str = "dual"          # dual=前区+后区；pool=单一号池（快乐8）
    pick_size: int = 0          # pool 模式下玩家选号个数（选十玩法=10）
    prize_levels: tuple = ()    # ((命中个数, 单注奖金, 奖级名称), ...)
    prize_note: str = ""

    @property
    def csv_path(self):
        return DATA_DIR / f"{self.key}.csv"

    @property
    def is_pool(self):
        return self.mode == "pool"

    @property
    def prize_map(self):
        return {hits: money for hits, money, _ in self.prize_levels}


GAMES = {
    "ssq": Game(
        key="ssq",
        name="双色球",
        short="SSQ",
        org="中国福利彩票",
        front=Zone("front", "红球", 6, 1, 33, True),
        back=Zone("back", "蓝球", 1, 1, 16, True),
        price=2,
        draw_days="每周二、四、日",
        source_desc="中国福彩网开奖公告（2013 年至今，含开奖日期）+ 500 彩票网历史数据（2003 年首期起，补齐早期，二者重叠期号逐期交叉校验）",
    ),
    "dlt": Game(
        key="dlt",
        name="超级大乐透",
        short="DLT",
        org="中国体育彩票",
        front=Zone("front", "前区", 5, 1, 35, True),
        back=Zone("back", "后区", 2, 1, 12, True),
        price=2,
        draw_days="每周一、三、六",
        source_desc="中国体育彩票 webapi 历史开奖列表（全量，含开奖日期）+ 500 彩票网历史数据（全量，逐期交叉校验）",
    ),
    "qxc": Game(
        key="qxc",
        name="七星彩",
        short="QXC",
        org="中国体育彩票",
        front=Zone("front", "前六位", 6, 0, 9, False),
        back=Zone("back", "特别位", 1, 0, 14, False),
        price=2,
        draw_days="每周二、五、日",
        source_desc="中国体育彩票 webapi 历史开奖列表（全量，含开奖日期）",
    ),
    "kl8": Game(
        key="kl8",
        name="快乐8（选十）",
        short="KL8",
        org="中国福利彩票",
        front=Zone("front", "开奖号", 20, 1, 80, True),
        back=Zone("back", "", 0, 0, 0, True),  # 单一号池，无独立后区
        price=2,
        draw_days="每天（休市日除外）",
        source_desc="中国福彩网快乐 8 开奖公告（全量，含开奖日期）",
        mode="pool",
        pick_size=10,
        prize_levels=(
            (10, 5_000_000, "选十中十（浮动奖，单注封顶 500 万）"),
            (9, 8_000, "选十中九"),
            (8, 720, "选十中八"),
            (7, 80, "选十中七"),
            (6, 5, "选十中六"),
            (5, 3, "选十中五"),
            (0, 2, "选十中零"),
        ),
        prize_note="官方规则：从 1~80 中选 1~10 个号码投注，每注 2 元，每期开出 20 个号码；"
                   "彩票奖金按销售额 58% 计提（57% 当期奖金 + 1% 调节基金）。",
    ),
}

GAME_ORDER = ("ssq", "dlt", "qxc", "kl8")

# ---------------------------------------------------------------- 数据源
CWL_API = (
    "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"
    "?name=ssq&issueCount=3000&pageNo={page}&pageSize=100&systemType=PC"
)
CWL_KL8_API = (
    "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"
    "?name=kl8&issueCount=5000&pageNo={page}&pageSize=100&systemType=PC"
)
CWL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.cwl.gov.cn/ygkj/wqkjgg/",
}
CWL500_API = (
    # end=99999 表示取到数据源最新一期，无需随年份手工修改
    "https://datachart.500.com/ssq/history/newinc/history.php"
    "?start=03001&end=99999"
)
CWL500_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://datachart.500.com/ssq/history/",
}
DLT500_API = (
    "https://datachart.500.com/dlt/history/newinc/history.php"
    "?start=00001&end=99999"
)
DLT500_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://datachart.500.com/dlt/history/",
}
SPORTTERY_API = (
    "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry"
    "?gameNo={game_no}&provinceId=0&pageSize=100&isVerify=1&pageNo={page}"
)
SPORTTERY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.lottery.gov.cn/kj/kjlb.html",
}
SPORTTERY_GAME_NO = {"dlt": "85", "qxc": "04"}

REQUEST_TIMEOUT = 30
REQUEST_RETRIES = 3
REQUEST_INTERVAL = 0.25  # 礼貌限速，避免给官方接口造成压力


def game_of(key: str) -> Game:
    if key not in GAMES:
        raise ValueError(f"未知彩种: {key}，可选 {', '.join(GAME_ORDER)}")
    return GAMES[key]


def parse_game_keys(text: str):
    if text in ("all", "全部", "*"):
        return list(GAME_ORDER)
    keys = [x.strip().lower() for x in text.split(",") if x.strip()]
    for k in keys:
        game_of(k)
    return keys
