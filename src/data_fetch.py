# -*- coding: utf-8 -*-
"""
数据采集模块：
1. 上交所 ETF 份额（fund_etf_scale_sse，按日回补历史）
2. 深交所 ETF 份额（fund_etf_scale_szse 修复版，仅当前值，历史从部署日起累积）
3. 新浪 ETF 历史行情（价格/成交额/成交量，回补历史）
4. 天天基金单位净值（历史净值）
5. 东财 push2 实时行情（单只，供折溢价/最新价校验）
"""
import json
import os
import sys
import time
import warnings

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nt_common import (DATA_DIR, SHARE_HIST, QUOTE_HIST, NAV_HIST, load_pool,
                       log, ensure_dirs, get_sh_symbol, get_em_secid)


def fetch_sse_share(date_str):
    """上交所某日全部 ETF 份额。date_str: YYYYMMDD"""
    import akshare as ak
    df = ak.fund_etf_scale_sse(date=date_str)
    df = df.rename(columns={"基金代码": "code", "基金简称": "name", "基金份额": "shares", "统计日期": "date"})
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df[["code", "name", "shares", "date"]]


def fetch_szse_share():
    """深交所当前 ETF 份额（修复 akshare 在 pandas3 下的 bytes bug）"""
    import requests
    url = "https://fund.szse.cn/api/report/ShowReport"
    params = {"SHOWTYPE": "xlsx", "CATALOGID": "1000_lf", "TABKEY": "tab1",
              "random": str(round(time.time(), 3))}
    headers = {"Referer": "https://fund.szse.cn/marketdata/fundslist/index.html",
               "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"}
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        df = pd.read_excel(__import__("io").BytesIO(r.content), engine="openpyxl", dtype={"基金代码": str})
    df["基金代码"] = df["基金代码"].astype(str).str.zfill(6)
    df = df.rename(columns={"基金代码": "code", "基金简称": "name", "当前规模(份)": "shares", "净值": "nav"})
    # 深交所份额带千分位逗号，需清洗为数值
    df["shares"] = df["shares"].astype(str).str.replace(",", "", regex=False)
    df["shares"] = pd.to_numeric(df["shares"], errors="coerce")
    return df[["code", "name", "shares", "nav"]]


def fetch_sina_hist(code):
    """新浪 ETF 全历史行情"""
    import akshare as ak
    sym = get_sh_symbol(code)
    df = ak.fund_etf_hist_sina(symbol=sym)
    df["code"] = code
    df = df.rename(columns={"date": "date", "close": "close", "volume": "volume", "amount": "amount"})
    return df[["date", "code", "close", "volume", "amount"]]


def fetch_nav_hist(code, start="20240101", end="20261231"):
    """天天基金单位净值历史"""
    import akshare as ak
    df = ak.fund_etf_fund_info_em(fund=code, start_date=start, end_date=end)
    df = df.rename(columns={"净值日期": "date", "单位净值": "nav"})
    df["code"] = code
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df[["date", "code", "nav"]]


def fetch_em_realtime(code):
    """东财 push2 实时行情（单只），失败返回 None"""
    import requests
    secid = get_em_secid(code)
    url = (f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&invt=2&fltt=2"
           f"&fields=f43,f44,f45,f46,f47,f48,f49,f50,f51,f52,f57,f58,f60,f116,f168,f169,f170,f171")
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    d = r.json().get("data") or {}
    if not d:
        return None
    return {"code": code, "name": d.get("f58"), "price": d.get("f43"), "prev_close": d.get("f60"),
            "high": d.get("f44"), "low": d.get("f45"), "open": d.get("f46"),
            "volume": d.get("f47"), "amount": d.get("f48"), "turnover": d.get("f50"),
            "mktcap": d.get("f116"), "change_pct": d.get("f170")}


def seed_share_history(days=120):
    """回补沪市标的份额历史：拉取最近 days 个交易日（按交易日历过滤），
    深市标的从本次起每日累积。返回更新后的 share_history DataFrame。"""
    import akshare as ak
    if os.path.exists(SHARE_HIST):
        hist = pd.read_csv(SHARE_HIST, dtype={"code": str})
    else:
        hist = pd.DataFrame(columns=["date", "code", "name", "shares", "source"])

    cal = ak.tool_trade_date_hist_sina()
    all_dates = sorted(str(d) for d in cal["trade_date"].astype(str).tolist())
    hist_dates = set(hist["date"].astype(str).unique()) if len(hist) else set()
    # 取最近 days 个尚未入库的交易日
    missing = [d for d in all_dates if d.replace("-", "") not in {h.replace("-", "") for h in hist_dates}]
    targets = missing[-days:] if len(missing) > days else missing

    etfs, _ = load_pool()
    sh_codes = {e["code"] for e in etfs if e["market"] == "SH"}
    added = 0
    for d in targets:
        yyyymmdd = d.replace("-", "")
        try:
            df = fetch_sse_share(yyyymmdd)
            sub = df[df["code"].isin(sh_codes)].copy()
            if len(sub) == 0:
                continue
            sub["source"] = "sse"
            hist = pd.concat([hist, sub], ignore_index=True)
            added += len(sub)
            log(f"  seed {d}: +{len(sub)} rows")
        except Exception as e:
            log(f"  seed {d} FAIL: {str(e)[:100]}")
        time.sleep(0.3)
    if added:
        hist = hist.drop_duplicates(subset=["date", "code"], keep="last")
        hist.to_csv(SHARE_HIST, index=False, encoding="utf-8-sig")
        log(f"[seed] share history updated, +{added} rows, total {len(hist)}")
    return hist


def append_today_share():
    """写入今日份额（沪市按今日、深市取当前值）"""
    import akshare as ak
    etfs, _ = load_pool()
    sh_codes = {e["code"] for e in etfs if e["market"] == "SH"}
    sz_codes = {e["code"] for e in etfs if e["market"] == "SZ"}

    if os.path.exists(SHARE_HIST):
        hist = pd.read_csv(SHARE_HIST, dtype={"code": str})
    else:
        hist = pd.DataFrame(columns=["date", "code", "name", "shares", "source"])

    # 今日日期（用最新交易日历最后一天，避免节假日写入空值）
    cal = ak.tool_trade_date_hist_sina()
    today = str(cal["trade_date"].astype(str).iloc[-1])

    rows = []
    # 沪市
    try:
        df = fetch_sse_share(today.replace("-", ""))
        sub = df[df["code"].isin(sh_codes)].copy()
        sub["source"] = "sse"
        rows.append(sub)
    except Exception as e:
        log(f"[warn] SSE today fetch fail: {e}")
    # 深市
    try:
        df_sz = fetch_szse_share()
        sub_sz = df_sz[df_sz["code"].isin(sz_codes)].copy()
        sub_sz["date"] = today
        sub_sz["source"] = "szse"
        rows.append(sub_sz[["date", "code", "name", "shares", "source"]])
    except Exception as e:
        log(f"[warn] SZSE today fetch fail: {e}")

    if rows:
        new = pd.concat(rows, ignore_index=True)
        hist = pd.concat([hist, new], ignore_index=True)
        hist = hist.drop_duplicates(subset=["date", "code"], keep="last")
        hist.to_csv(SHARE_HIST, index=False, encoding="utf-8-sig")
        log(f"[today] share snapshot {today}: +{len(new)} rows, total {len(hist)}")
    return hist


def refresh_quote_history():
    """刷新行情历史（新浪）与净值历史（天天基金），各标的合并"""
    etfs, _ = load_pool()
    codes = [e["code"] for e in etfs]

    if os.path.exists(QUOTE_HIST):
        q = pd.read_csv(QUOTE_HIST, dtype={"code": str})
    else:
        q = pd.DataFrame(columns=["date", "code", "close", "volume", "amount"])
    if os.path.exists(NAV_HIST):
        n = pd.read_csv(NAV_HIST, dtype={"code": str})
    else:
        n = pd.DataFrame(columns=["date", "code", "nav"])

    for code in codes:
        try:
            df = fetch_sina_hist(code)
            df["code"] = code
            q = pd.concat([q, df], ignore_index=True)
            log(f"  quote {code}: {len(df)} rows")
        except Exception as e:
            log(f"  quote {code} FAIL: {str(e)[:100]}")
        try:
            dfn = fetch_nav_hist(code)
            n = pd.concat([n, dfn], ignore_index=True)
        except Exception as e:
            log(f"  nav {code} FAIL: {str(e)[:100]}")
        time.sleep(0.2)

    q = q.drop_duplicates(subset=["date", "code"], keep="last")
    n = n.drop_duplicates(subset=["date", "code"], keep="last")
    q.to_csv(QUOTE_HIST, index=False, encoding="utf-8-sig")
    n.to_csv(NAV_HIST, index=False, encoding="utf-8-sig")
    log(f"[quote] total {len(q)} rows, nav total {len(n)} rows")
    return q, n


if __name__ == "__main__":
    ensure_dirs()
    log("== manual data refresh ==")
    seed_share_history(days=120)
    append_today_share()
    refresh_quote_history()
