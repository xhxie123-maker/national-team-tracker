# -*- coding: utf-8 -*-
"""
历史数据清洗（幂等）：
云端每日增量会重复合并全量行情/净值，若 date dtype 不一致，去重会失效，
导致 CSV 行数翻倍、同一天出现多条记录，进而使分析端 .loc 取回 Series 而报错。
本模块在分析前统一 date 为 YYYY-MM-DD、code 补零，并按 (date, code) 去重后回写。
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nt_common import DATA_DIR, SHARE_HIST, QUOTE_HIST, NAV_HIST, log

TARGETS = (
    ("share", SHARE_HIST, ["date", "code"]),
    ("quote", QUOTE_HIST, ["date", "code"]),
    ("nav", NAV_HIST, ["date", "code"]),
)


def _clean(path, keys):
    if not os.path.exists(path):
        return 0, 0
    df = pd.read_csv(path, dtype={"code": str})
    n0 = len(df)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        df = df[df["date"].notna()].copy()
    if "code" in df.columns:
        df["code"] = df["code"].astype(str).str.zfill(6)
    if "shares" in df.columns:
        df["shares"] = df["shares"].astype(str).str.replace(",", "", regex=False)
        df["shares"] = pd.to_numeric(df["shares"], errors="coerce")
    df = df.drop_duplicates(subset=keys, keep="last").sort_values(keys)
    n1 = len(df)
    if n1 != n0:
        df.to_csv(path, index=False, encoding="utf-8-sig")
    return n0, n1


def clean_history():
    total_removed = 0
    for name, path, keys in TARGETS:
        n0, n1 = _clean(path, keys)
        if n0:
            total_removed += (n0 - n1)
            log(f"[clean] {name}: {n0} -> {n1} rows (-{n0 - n1})")
    if total_removed:
        log(f"[clean] history normalized, removed {total_removed} duplicated rows")
    return total_removed


if __name__ == "__main__":
    clean_history()
