# -*- coding: utf-8 -*-
"""
国家队 ETF 跟踪系统 主入口
用法：
  python main.py            # 完整流程：回补历史(幂等) -> 写当日 -> 刷新行情净值 -> 清洗 -> 计算指标 -> 生成看板
  python main.py --no-seed  # 跳过历史回补（不推荐，seed 幂等，每次只补缺失交易日）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from nt_common import ensure_dirs, log
import data_fetch
import clean
import analyze
import render


def _history_days():
    """已入库的份额交易日数量，用于判断是否需要回补历史（日常运行无需重复回补）"""
    import pandas as pd
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "share_history.csv")
    if not os.path.exists(path):
        return 0
    try:
        df = pd.read_csv(path, usecols=["date"])
        return int(df["date"].astype(str).str[:10].nunique())
    except Exception:
        return 0


def main():
    ensure_dirs()
    args = sys.argv[1:]
    no_seed = "--no-seed" in args

    log("===== national-team-tracker run =====")

    if not no_seed:
        if _history_days() >= 60:
            log(f"[seed] 份额历史已足够（{_history_days()} 个交易日），跳过回补")
        else:
            data_fetch.seed_share_history(days=240)  # 幂等：只补缺失交易日（首日回补近一年）
    data_fetch.append_today_share()              # 写当日份额
    data_fetch.refresh_quote_history()           # 行情+净值
    clean.clean_history()                        # 去重/类型归一（防云端重复累积）

    snapshot = analyze.build_metrics()           # 指标计算
    render.build_dashboard(snapshot)             # 看板生成
    log("===== run done =====")


if __name__ == "__main__":
    main()
