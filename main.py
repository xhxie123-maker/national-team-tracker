# -*- coding: utf-8 -*-
"""
国家队 ETF 跟踪系统 主入口
用法：
  python main.py            # 完整流程：回补历史(幂等) -> 写当日 -> 刷新行情净值 -> 计算指标 -> 生成看板
  python main.py --no-seed  # 跳过历史回补（不推荐，seed 幂等，每次只补缺失交易日）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from nt_common import ensure_dirs, log
import data_fetch
import analyze
import render


def main():
    ensure_dirs()
    args = sys.argv[1:]
    no_seed = "--no-seed" in args

    log("===== national-team-tracker run =====")

    if not no_seed:
        data_fetch.seed_share_history(days=240)  # 幂等：只补缺失交易日（首日回补近一年）
    data_fetch.append_today_share()              # 写当日份额
    data_fetch.refresh_quote_history()           # 行情+净值

    snapshot = analyze.build_metrics()           # 指标计算
    render.build_dashboard(snapshot)             # 看板生成
    log("===== run done =====")


if __name__ == "__main__":
    main()
