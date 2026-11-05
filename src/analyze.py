# -*- coding: utf-8 -*-
"""
分析引擎：
- 份额变化：1日/5日/20日 变化率与变化量（国家队动作的核心代理指标）
- 净流入估算：Δ份额 × 当日单位净值（方向性指标，非精确国家队份额）
- 成交放量：当日成交额 / 20日均成交额
- 折溢价：收盘价 / 单位净值 - 1
- 异动评分：综合份额异动+放量，输出预警
输出：data/daily_snapshot.json + output/pages/metrics.json（供看板使用）
"""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nt_common import (DATA_DIR, OUTPUT_DIR, SHARE_HIST, QUOTE_HIST, NAV_HIST,
                       load_pool, log, ensure_dirs, DAILY_SNAPSHOT)


def _norm_date(s):
    return str(s)[:10]


def build_metrics():
    ensure_dirs()
    etfs, _ = load_pool()
    codes = [e["code"] for e in etfs]

    if not os.path.exists(SHARE_HIST):
        log("[metrics] share history missing, run data_fetch first")
        return None

    sh = pd.read_csv(SHARE_HIST, dtype={"code": str})
    sh["date"] = sh["date"].astype(str).str[:10]
    # 防御：清洗可能存在的千分位逗号后再转数值
    sh["shares"] = sh["shares"].astype(str).str.replace(",", "", regex=False)
    sh["shares"] = pd.to_numeric(sh["shares"], errors="coerce")

    q = None
    if os.path.exists(QUOTE_HIST):
        q = pd.read_csv(QUOTE_HIST, dtype={"code": str})
        q["date"] = q["date"].astype(str).str[:10]
        q["close"] = pd.to_numeric(q["close"], errors="coerce")
        q["amount"] = pd.to_numeric(q["amount"], errors="coerce")

    nv = None
    if os.path.exists(NAV_HIST):
        nv = pd.read_csv(NAV_HIST, dtype={"code": str})
        nv["date"] = nv["date"].astype(str).str[:10]
        nv["nav"] = pd.to_numeric(nv["nav"], errors="coerce")

    # 全池统一交易日（按份额数据的日期）
    all_dates = sorted(sh["date"].unique())
    if len(all_dates) < 2:
        log("[metrics] not enough share history")
        return None
    last_date = all_dates[-1]

    rows = []
    for e in etfs:
        code = e["code"]
        s = sh[sh["code"] == code].set_index("date")["shares"].sort_index()
        r = {"code": code, "name": e["name"], "category": e["category"],
             "index": e["index"], "market": e["market"], "note": e.get("note", ""),
             "date": last_date, "share": None}

        if last_date in s.index:
            r["share"] = float(s.loc[last_date])

        def share_n_days_ago(n):
            dts = [d for d in all_dates if d < last_date]
            if len(dts) < n:
                return None
            target = dts[-n]
            return float(s.loc[target]) if target in s.index else None

        prev = share_n_days_ago(1)
        d5 = share_n_days_ago(5)
        d20 = share_n_days_ago(20)

        # 1日份额变化
        if r["share"] is not None and prev:
            r["share_chg_1d"] = r["share"] - prev
            r["share_chg_1d_pct"] = (r["share"] / prev - 1) * 100
        else:
            r["share_chg_1d"] = None
            r["share_chg_1d_pct"] = None
        if r["share"] is not None and d5:
            r["share_chg_5d"] = r["share"] - d5
            r["share_chg_5d_pct"] = (r["share"] / d5 - 1) * 100
        else:
            r["share_chg_5d"] = None
            r["share_chg_5d_pct"] = None
        if r["share"] is not None and d20:
            r["share_chg_20d"] = r["share"] - d20
            r["share_chg_20d_pct"] = (r["share"] / d20 - 1) * 100
        else:
            r["share_chg_20d"] = None
            r["share_chg_20d_pct"] = None

        # 净值（当日）
        nav = None
        if nv is not None:
            ns = nv[nv["code"] == code].set_index("date")["nav"].sort_index()
            if last_date in ns.index:
                nav = float(ns.loc[last_date])
        r["nav"] = nav

        # 净流入估算（1日/5日）
        if r["share_chg_1d"] is not None and nav:
            r["net_inflow_1d"] = r["share_chg_1d"] * nav
        else:
            r["net_inflow_1d"] = None
        if r["share_chg_5d"] is not None and nav:
            r["net_inflow_5d"] = r["share_chg_5d"] * nav
        else:
            r["net_inflow_5d"] = None

        # 行情：收盘价 / 成交额 / 放量
        close = None
        if q is not None:
            qs = q[q["code"] == code].set_index("date")
            if last_date in qs.index:
                close = float(qs.loc[last_date, "close"])
                r["amount"] = float(qs.loc[last_date, "amount"]) if pd.notna(qs.loc[last_date, "amount"]) else None
            else:
                r["amount"] = None
            # 20日均成交额
            hist_amount = qs["amount"].dropna().astype(float)
            if len(hist_amount) >= 21:
                ma20 = hist_amount.iloc[-21:-1].mean()
                r["amount_ma20"] = float(ma20)
                r["volume_ratio"] = float(r["amount"] / ma20) if r["amount"] else None
            else:
                r["amount_ma20"] = None
                r["volume_ratio"] = None
        else:
            r["amount"] = None
            r["amount_ma20"] = None
            r["volume_ratio"] = None
        r["close"] = close

        # 折溢价
        r["premium_pct"] = ((close / nav - 1) * 100) if (close and nav) else None

        # 异动评分（0-100）：份额1日/5日变化 + 放量
        score = 0
        if r["share_chg_1d_pct"] is not None:
            score += min(abs(r["share_chg_1d_pct"]) * 15, 40)
        if r["share_chg_5d_pct"] is not None:
            score += min(abs(r["share_chg_5d_pct"]) * 8, 30)
        if r["volume_ratio"] is not None:
            score += min(max(r["volume_ratio"] - 1, 0) * 20, 30)
        r["anomaly_score"] = round(score, 1)
        r["anomaly_flag"] = score >= 40

        # 统一 NaN -> None（保证 JSON 合法）
        for k, v in r.items():
            if isinstance(v, float) and pd.isna(v):
                r[k] = None

        rows.append(r)

    df = pd.DataFrame(rows)

    # 全池汇总
    total_inflow_1d = df["net_inflow_1d"].sum()
    total_inflow_5d = df["net_inflow_5d"].sum()
    top = df.nlargest(3, "anomaly_score")[["name", "anomaly_score", "share_chg_1d_pct",
                                           "share_chg_5d_pct", "volume_ratio", "net_inflow_1d"]].to_dict("records")

    snapshot = {
        "date": last_date,
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "pool_size": len(etfs),
        "total_net_inflow_1d": float(total_inflow_1d) if pd.notna(total_inflow_1d) else None,
        "total_net_inflow_5d": float(total_inflow_5d) if pd.notna(total_inflow_5d) else None,
        "top_anomalies": top,
        "etfs": rows,
    }
    with open(DAILY_SNAPSHOT, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=1)
    os.makedirs(os.path.join(OUTPUT_DIR, "pages"), exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "pages", "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=1, allow_nan=False)
    log(f"[metrics] snapshot {last_date} saved, {len(rows)} etfs")
    return snapshot


if __name__ == "__main__":
    s = build_metrics()
    if s:
        print(json.dumps(s, ensure_ascii=False, indent=1)[:2000])
