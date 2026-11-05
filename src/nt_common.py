# -*- coding: utf-8 -*-
"""
national-team-tracker 公共模块
数据源口径说明：
- 份额：上交所官方接口（按日可查、历史可回补）+ 深交所官方接口（当前值）
- 行情：新浪 ETF 历史（成交额/成交量/收盘价）
- 净值：天天基金单位净值（净流入估算基准）
注意：公开份额变化 = 市场资金+稳市资金合计，不能精确拆分国家队份额，
仅作为“国家队动作方向”的代理指标，最终以基金季报/年报十大持有人披露为准。
"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "etf_pool.json")
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

SHARE_HIST = os.path.join(DATA_DIR, "share_history.csv")   # 每日份额（全部池内标的）
QUOTE_HIST = os.path.join(DATA_DIR, "quote_history.csv")   # 每日行情快照（价格/成交额）
NAV_HIST = os.path.join(DATA_DIR, "nav_history.csv")       # 每日单位净值
DAILY_SNAPSHOT = os.path.join(DATA_DIR, "daily_snapshot.json")  # 当日指标快照
HOLDERS_FILE = os.path.join(DATA_DIR, "holders.json")      # 季报十大持有人披露（半自动维护）
RUN_LOG = os.path.join(OUTPUT_DIR, "run_log.txt")
DASHBOARD = os.path.join(OUTPUT_DIR, "dashboard.html")
PAGES_DIR = os.path.join(OUTPUT_DIR, "pages")


def ensure_dirs():
    for d in [DATA_DIR, OUTPUT_DIR, PAGES_DIR]:
        os.makedirs(d, exist_ok=True)


def load_pool():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg["etfs"], cfg


def get_sh_symbol(code):
    """新浪 symbol：sh510300 / sz159919"""
    return ("sh" + code) if code.startswith(("5", "6")) else ("sz" + code)


def get_em_secid(code):
    """东财 secid：1=沪 0=深"""
    return ("1." + code) if code.startswith(("5", "6")) else ("0." + code)


def log(msg, also_stdout=True):
    line = f"{msg}"
    if also_stdout:
        print(line, flush=True)
    try:
        with open(RUN_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def ensure_trade_dates():
    """获取交易日历（含未来），失败时返回 None"""
    try:
        import akshare as ak
        df = ak.tool_trade_date_hist_sina()
        return sorted(str(d) for d in df["trade_date"].astype(str).tolist())
    except Exception as e:
        log(f"[warn] trade calendar fetch failed: {e}")
        return None
