# -*- coding: utf-8 -*-
"""
看板生成：生成单文件 ECharts HTML 看板（含内联数据，无外部依赖除 echarts.min.js）。
图表：
1. 份额趋势（沪深300四只 + 上证50/180 分组折线）
2. 份额变化率排行（1日/5日）
3. 净流入估算排行（5日）
4. 放量倍数条形
5. 异动预警列表
6. 季报披露持仓表（holders.json，半自动维护）
"""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nt_common import (BASE_DIR, DATA_DIR, OUTPUT_DIR, SHARE_HIST, QUOTE_HIST,
                       NAV_HIST, load_pool, log, ensure_dirs, HOLDERS_FILE, DASHBOARD)

ECHARTS_LIB = os.path.join(BASE_DIR, "libs", "echarts.min.js")


def _echarts_script():
    """内联 echarts（自包含看板，无外部依赖）。libs 缺失时回退 CDN 引用。"""
    if os.path.exists(ECHARTS_LIB):
        try:
            with open(ECHARTS_LIB, "r", encoding="utf-8") as f:
                js = f.read()
            return f"<script>{js}</script>"
        except Exception:
            pass
    return '<script src="libs/echarts.min.js"></script>'

DEFAULT_HOLDERS = {
    "note": "基金季报/年报十大持有人披露（手动维护，季度更新）。汇金系持仓占比数据来自公开报道口径，非实时。",
    "periods": [
        {"period": "2025年报", "updated": "2026-03-31", "items": []},
        {"period": "2026一季报", "updated": "2026-04-22", "items": []},
        {"period": "2026中报", "updated": "2026-08-31", "items": []},
        {"period": "2026三季报", "updated": "2026-10-31", "items": []},
    ]
}


def load_holders():
    if os.path.exists(HOLDERS_FILE):
        try:
            with open(HOLDERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    with open(HOLDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_HOLDERS, f, ensure_ascii=False, indent=1)
    return DEFAULT_HOLDERS


def build_dashboard(snapshot):
    ensure_dirs()
    if snapshot is None:
        if os.path.exists(os.path.join(OUTPUT_DIR, "pages", "metrics.json")):
            with open(os.path.join(OUTPUT_DIR, "pages", "metrics.json"), "r", encoding="utf-8") as f:
                snapshot = json.load(f)
        else:
            log("[dashboard] no snapshot data")
            return

    etfs, cfg = load_pool()
    holders = load_holders()
    date = snapshot.get("date", "")
    generated = snapshot.get("generated_at", "")

    # ---------- 份额趋势数据 ----------
    if os.path.exists(SHARE_HIST):
        sh = pd.read_csv(SHARE_HIST, dtype={"code": str})
        sh["date"] = sh["date"].astype(str).str[:10]
        sh["shares"] = sh["shares"].astype(str).str.replace(",", "", regex=False)
        sh["shares"] = pd.to_numeric(sh["shares"], errors="coerce")
    else:
        sh = pd.DataFrame(columns=["date", "code", "shares"])

    focus_codes = ["510300", "510310", "510330", "159919", "510050", "510180"]
    trend_dates = sorted(sh["date"].unique())[-90:] if len(sh) else []
    trend_series = {}
    for c in focus_codes:
        sub = sh[sh["code"] == c]
        m = sub.set_index("date")["shares"].reindex(trend_dates)
        trend_series[c] = [None if pd.isna(v) else v / 1e8 for v in m]  # 亿份

    # ---------- 表数据 ----------
    rows = snapshot.get("etfs", [])
    table_rows = []
    for r in sorted(rows, key=lambda x: (x.get("anomaly_score") or 0), reverse=True):
        table_rows.append({
            "code": r["code"], "name": r["name"], "category": r["category"],
            "share": r.get("share"),
            "chg1d_pct": r.get("share_chg_1d_pct"),
            "chg5d_pct": r.get("share_chg_5d_pct"),
            "chg20d_pct": r.get("share_chg_20d_pct"),
            "net5d": r.get("net_inflow_5d"),
            "vol_ratio": r.get("volume_ratio"),
            "premium": r.get("premium_pct"),
            "score": r.get("anomaly_score"),
            "flag": r.get("anomaly_flag"),
            "nav": r.get("nav"),
            "close": r.get("close"),
        })

    top_anomalies = snapshot.get("top_anomalies", [])

    # ---------- HTML ----------
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>国家队ETF跟踪看板</title>
{ECHARTS_SCRIPT}
<style>
:root{--bg:#0f1420;--card:#161d2e;--border:#24304a;--text:#dbe4f5;--sub:#8a97b5;--accent:#3d7eff;--up:#f4504e;--down:#2ecc71;}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:"Microsoft YaHei",-apple-system,sans-serif;padding:16px}
.header{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:8px;margin-bottom:14px}
.header h1{font-size:22px;letter-spacing:1px}
.header .sub{color:var(--sub);font-size:12px;margin-top:4px}
.badges{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.badge{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:10px 14px;min-width:150px}
.badge .k{color:var(--sub);font-size:12px}
.badge .v{font-size:20px;font-weight:700;margin-top:2px}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:12px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px;grid-column:span 12}
.card h2{font-size:15px;margin-bottom:10px;color:#c8d4ee;display:flex;align-items:center;gap:6px}
.card h2::before{content:"";width:4px;height:14px;background:var(--accent);border-radius:2px}
.col-6{grid-column:span 6}
.col-4{grid-column:span 4}
@media(max-width:1100px){.col-6,.col-4{grid-column:span 12}}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{color:var(--sub);text-align:left;font-weight:600;padding:7px 6px;border-bottom:1px solid var(--border);white-space:nowrap}
td{padding:7px 6px;border-bottom:1px solid rgba(36,48,74,.5);white-space:nowrap}
tr:hover td{background:rgba(61,126,255,.06)}
.up{color:var(--up)}.down{color:var(--down)}
.flag{color:#ffb84d;font-weight:700}
.num{font-variant-numeric:tabular-nums}
.chart{width:100%;height:320px}
.chart-sm{width:100%;height:260px}
.alert{border-left:3px solid #ffb84d}
.note{color:var(--sub);font-size:11.5px;margin-top:10px;line-height:1.7}
.footer{margin-top:14px;color:var(--sub);font-size:11px;text-align:center}
.pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;margin-right:4px}
.pill-sh{background:rgba(61,126,255,.15);color:#7fa8ff}
.pill-sz{background:rgba(46,204,113,.15);color:#6fe3a8}
.pill-anom{background:rgba(255,184,77,.18);color:#ffb84d}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>国家队 ETF 跟踪看板</h1>
    <div class="sub">中央汇金系 · 国新/诚通等稳市资金青睐的大盘宽基 · 数据日期 {DATE}</div>
  </div>
  <div class="sub">生成时间 {GEN}<br>份额：上交所/深交所官方 · 净值：天天基金 · 行情：新浪</div>
</div>

<div class="badges">
  <div class="badge"><div class="k">全池5日净流入估算</div><div class="v {INFLOW_CLASS}">{INFLOW5D} 亿元</div></div>
  <div class="badge"><div class="k">全池1日净流入估算</div><div class="v {INFLOW1D_CLASS}">{INFLOW1D} 亿元</div></div>
  <div class="badge"><div class="k">跟踪标的数</div><div class="v">{POOL_SIZE} 只</div></div>
  <div class="badge"><div class="k">异动预警</div><div class="v" style="color:#ffb84d">{ANOM_COUNT} 条</div></div>
</div>

<div class="grid">
  <div class="card">
    <h2>核心标的份额趋势（近90个交易日，亿份）</h2>
    <div id="trend" class="chart"></div>
  </div>

  <div class="card col-6">
    <h2>5日份额变化率排行（%）</h2>
    <div id="chg5d" class="chart-sm"></div>
  </div>
  <div class="card col-6">
    <h2>5日净流入估算排行（亿元）</h2>
    <div id="netflow" class="chart-sm"></div>
  </div>

  <div class="card">
    <h2>异动预警（份额异动 + 成交放量）</h2>
    <table><thead><tr><th>标的</th><th>类别</th><th>异动分</th><th>1日份额变化</th><th>5日份额变化</th><th>放量倍数</th><th>5日净流入(亿)</th></tr></thead>
    <tbody>{ALERT_ROWS}</tbody></table>
  </div>

  <div class="card">
    <h2>全标的明细（按异动分排序）</h2>
    <table><thead><tr><th>代码</th><th>名称</th><th>类别</th><th>市场</th><th>份额(亿份)</th><th>1日Δ%</th><th>5日Δ%</th><th>20日Δ%</th><th>5日净流入(亿)</th><th>放量</th><th>折溢价%</th><th>净值</th></tr></thead>
    <tbody>{TABLE_ROWS}</tbody></table>
  </div>

  <div class="card">
    <h2>季报十大持有人披露（手动维护，季度更新）</h2>
    <div class="note">{HOLDERS_NOTE}</div>
    {HOLDERS_TABLE}
  </div>

  <div class="card">
    <div class="note">
      <b>重要口径说明：</b><br>
      ① 公开份额变化 = 市场资金 + 稳市资金合计，<b>不能精确拆分国家队份额</b>，本看板仅作“国家队动作方向”的代理指标；<br>
      ② 汇金持仓为动态逆周期操作（2024-2025大幅增持 → 2026上半年减持兑现 → 7月后分批回补），历史持仓名单不等于当前仍在加仓，请结合份额异动与季报披露判断；<br>
      ③ 净流入估算 = Δ份额 × 当日单位净值，为方向性估算；<br>
      ④ 本系统仅作数据整理与研究参考，不构成投资建议。
    </div>
  </div>
</div>
<div class="footer">national-team-tracker · GitHub Actions 每日收盘后自动更新 · 数据源：上交所/深交所/天天基金/新浪</div>

<script>
const TREND = {TREND_JSON};
const TREND_CODES = {TREND_CODES_JSON};
const CHG5D = {CHG5D_JSON};
const CHG1D = {CHG1D_JSON};
const NETFLOW = {NETFLOW_JSON};
const VOLRATIO = {VOLRATIO_JSON};
const PREMIUM = {PREMIUM_JSON};
const ALERTS = {ALERTS_JSON};
const HOLDERS = {HOLDERS_JSON};

const fmt = (v, d=2) => v==null||isNaN(v) ? "-" : Number(v).toLocaleString("zh-CN",{minimumFractionDigits:d,maximumFractionDigits:d});
const pct = (v) => v==null ? "-" : (v>0?"+":"") + v.toFixed(2) + "%";
const cls = (v) => v==null ? "" : (v>0?"up":"down");
const nvb = (v) => v==null ? "-" : (v>=1e8? (v/1e8).toFixed(2)+"亿" : v.toLocaleString("zh-CN"));

function setChart(id, option){ const el = document.getElementById(id); if(!el) return; const c = echarts.init(el); c.setOption(option); window.addEventListener("resize", ()=>c.resize()); }

// 1 份额趋势
setChart("trend", {
  backgroundColor:"transparent",
  tooltip:{trigger:"axis"},
  legend:{data:TREND_CODES.map(c=>c[1]), textStyle:{color:"#8a97b5"}, top:0},
  grid:{left:50,right:20,top:32,bottom:30},
  xAxis:{type:"category",data:TREND[0],axisLabel:{color:"#8a97b5"}},
  yAxis:{type:"value",axisLabel:{color:"#8a97b5"},splitLine:{lineStyle:{color:"rgba(36,48,74,.5)"}}},
  series: TREND_CODES.map((c,i)=>({name:c[1],type:"line",smooth:true,showSymbol:false,data:TREND[i+1],lineStyle:{width:2},itemStyle:{color:["#3d7eff","#f4504e","#2ecc71","#ffb84d","#a78bfa","#22d3ee"][i%6]}}))
});

// 2 5日份额变化率排行
setChart("chg5d", {
  backgroundColor:"transparent",
  tooltip:{trigger:"axis",axisPointer:{type:"shadow"}},
  grid:{left:110,right:40,top:8,bottom:24},
  xAxis:{type:"value",axisLabel:{color:"#8a97b5"},splitLine:{lineStyle:{color:"rgba(36,48,74,.5)"}}},
  yAxis:{type:"category",data:CHG5D.map(d=>d[0]),axisLabel:{color:"#8a97b5"}},
  series:[{type:"bar",data:CHG5D.map(d=>d[1]),barWidth:10,itemStyle:{color:(p)=>p.value>=0?"#f4504e":"#2ecc71",borderRadius:[0,4,4,0]}}]
});

// 3 5日净流入估算排行
setChart("netflow", {
  backgroundColor:"transparent",
  tooltip:{trigger:"axis",axisPointer:{type:"shadow"},valueFormatter:v=>v.toFixed(1)+" 亿"},
  grid:{left:110,right:40,top:8,bottom:24},
  xAxis:{type:"value",axisLabel:{color:"#8a97b5"},splitLine:{lineStyle:{color:"rgba(36,48,74,.5)"}}},
  yAxis:{type:"category",data:NETFLOW.map(d=>d[0]),axisLabel:{color:"#8a97b5"}},
  series:[{type:"bar",data:NETFLOW.map(d=>d[1]),barWidth:10,itemStyle:{color:(p)=>p.value>=0?"#f4504e":"#2ecc71",borderRadius:[0,4,4,0]}}]
});

// 4 放量倍数
setChart("volratio", {
  backgroundColor:"transparent",
  tooltip:{trigger:"axis",axisPointer:{type:"shadow"},valueFormatter:v=>v.toFixed(2)+"x"},
  grid:{left:110,right:40,top:8,bottom:24},
  xAxis:{type:"value",axisLabel:{color:"#8a97b5"},splitLine:{lineStyle:{color:"rgba(36,48,74,.5)"}}},
  yAxis:{type:"category",data:VOLRATIO.map(d=>d[0]),axisLabel:{color:"#8a97b5"}},
  series:[{type:"bar",data:VOLRATIO.map(d=>d[1]),barWidth:10,itemStyle:{color:"#3d7eff",borderRadius:[0,4,4,0]}}]
});

// 5 折溢价
setChart("premium", {
  backgroundColor:"transparent",
  tooltip:{trigger:"axis",axisPointer:{type:"shadow"},valueFormatter:v=>v.toFixed(2)+"%"},
  grid:{left:110,right:40,top:8,bottom:24},
  xAxis:{type:"value",axisLabel:{color:"#8a97b5"},splitLine:{lineStyle:{color:"rgba(36,48,74,.5)"}}},
  yAxis:{type:"category",data:PREMIUM.map(d=>d[0]),axisLabel:{color:"#8a97b5"}},
  series:[{type:"bar",data:PREMIUM.map(d=>d[1]),barWidth:10,itemStyle:{color:(p)=>p.value>=0?"#f4504e":"#2ecc71",borderRadius:[0,4,4,0]}}]
});

document.addEventListener("DOMContentLoaded", ()=>{
  const tbody = document.getElementById("alert-body");
  if(tbody) tbody.innerHTML = ALERTS.map(a=>`<tr class="alert"><td>${a.name}</td><td>${a.category}</td><td class="flag">${a.score}</td><td class="${cls(a.c1)}">${pct(a.c1)}</td><td class="${cls(a.c5)}">${pct(a.c5)}</td><td>${a.vr==null?"-":a.vr.toFixed(2)+"x"}</td><td class="${cls(a.n5)}">${fmt(a.n5/1e8)}</td></tr>`).join("");
});
document.addEventListener("DOMContentLoaded", ()=>{
  const tb2 = document.getElementById("detail-body");
  if(tb2) tb2.innerHTML = TABLE_ROWS.map(t=>`<tr><td>${t.code}</td><td>${t.name}${t.flag?"<span class='flag'> 异动</span>":""}</td><td>${t.category}</td><td><span class="pill ${t.code.startsWith("5")?"pill-sh":"pill-sz"}">${t.code.startsWith("5")?"沪":"深"}</span></td><td class="num">${t.share==null?"-":(t.share/1e8).toFixed(2)}</td><td class="${cls(t.chg1d_pct)}">${pct(t.chg1d_pct)}</td><td class="${cls(t.chg5d_pct)}">${pct(t.chg5d_pct)}</td><td class="${cls(t.chg20d_pct)}">${pct(t.chg20d_pct)}</td><td class="${cls(t.net5d)}">${t.net5d==null?"-":(t.net5d/1e8).toFixed(2)}</td><td>${t.vol_ratio==null?"-":t.vol_ratio.toFixed(2)+"x"}</td><td class="${cls(t.premium)}">${pct(t.premium)}</td><td>${t.nav==null?"-":t.nav.toFixed(3)}</td></tr>`).join("");
});
document.addEventListener("DOMContentLoaded", ()=>{
  const hb = document.getElementById("holders-body");
  if(!hb) return;
  const periods = HOLDERS.periods || [];
  if(!periods.length || periods.every(p=>!p.items || !p.items.length)){
    hb.innerHTML = `<tr><td style="color:#8a97b5">尚未录入本季度披露数据，季报发布后可编辑 data/holders.json 更新。</td></tr>`;
    return;
  }
  hb.innerHTML = periods.flatMap(p=>p.items.map(i=>`<tr><td>${p.period}</td><td>${i.code}</td><td>${i.name}</td><td>${i.holder}</td><td>${i.ratio}</td><td>${i.change||""}</td></tr>`)).join("");
});
</script>
</body>
</html>"""

    # ---------- 组装数据 ----------
    trend_json = json.dumps([trend_dates] + [trend_series.get(c, []) for c in focus_codes], ensure_ascii=False)
    trend_codes_json = json.dumps([[c, next((e["name"] for e in etfs if e["code"] == c), c)] for c in focus_codes], ensure_ascii=False)

    def pick(key, conv=lambda v: v, desc=False):
        data = []
        for r in rows:
            v = r.get(key)
            if v is None:
                continue
            data.append([r["name"], conv(v)])
        data.sort(key=lambda x: x[1], reverse=desc)
        return data[:10]

    chg5d_json = json.dumps(pick("chg5d_pct", desc=True), ensure_ascii=False)
    chg1d_json = json.dumps(pick("chg1d_pct", desc=True), ensure_ascii=False)
    netflow_json = json.dumps(pick("net5d", lambda v: round(v / 1e8, 1), desc=True), ensure_ascii=False)
    volratio_json = json.dumps(pick("vol_ratio", desc=True), ensure_ascii=False)
    premium_json = json.dumps(pick("premium", desc=True), ensure_ascii=False)

    alerts = [r for r in rows if r.get("flag")]
    alerts_json = json.dumps([{"name": r["name"], "category": r["category"], "score": r["score"],
                               "c1": r.get("chg1d_pct"), "c5": r.get("chg5d_pct"),
                               "vr": r.get("vol_ratio"), "n5": r.get("net5d")} for r in alerts], ensure_ascii=False)

    # 预警表行
    alert_rows = "".join(
        f"<tr class='alert'><td>{r['name']}</td><td>{r['category']}</td><td class='flag'>{r['score']}</td>"
        f"<td class='{cls(r.get('chg1d_pct'))}'>{pct(r.get('chg1d_pct'))}</td>"
        f"<td class='{cls(r.get('chg5d_pct'))}'>{pct(r.get('chg5d_pct'))}</td>"
        f"<td>{'-' if r.get('vol_ratio') is None else str(round(r['vol_ratio'],2))+'x'}</td>"
        f"<td class='{cls(r.get('net5d'))}'>{'-' if r.get('net5d') is None else round(r['net5d']/1e8,2)}</td></tr>"
        for r in alerts)

    # 明细表行
    table_html = "".join(
        f"<tr><td>{r['code']}</td><td>{r['name']}{'<span class=\"flag\"> 异动</span>' if r.get('flag') else ''}</td>"
        f"<td>{r['category']}</td><td><span class='pill {'pill-sh' if r['code'].startswith('5') else 'pill-sz'}'>{'沪' if r['code'].startswith('5') else '深'}</span></td>"
        f"<td class='num'>{'-' if r.get('share') is None else round(r['share']/1e8,2)}</td>"
        f"<td class='{cls(r.get('chg1d_pct'))}'>{pct(r.get('chg1d_pct'))}</td>"
        f"<td class='{cls(r.get('chg5d_pct'))}'>{pct(r.get('chg5d_pct'))}</td>"
        f"<td class='{cls(r.get('chg20d_pct'))}'>{pct(r.get('chg20d_pct'))}</td>"
        f"<td class='{cls(r.get('net5d'))}'>{'-' if r.get('net5d') is None else round(r['net5d']/1e8,2)}</td>"
        f"<td>{'-' if r.get('vol_ratio') is None else str(round(r['vol_ratio'],2))+'x'}</td>"
        f"<td class='{cls(r.get('premium'))}'>{pct(r.get('premium'))}</td>"
        f"<td>{'-' if r.get('nav') is None else round(r['nav'],3)}</td></tr>"
        for r in table_rows)

    holders_note = holders.get("note", "")
    holders_periods = holders.get("periods", [])
    if any(p.get("items") for p in holders_periods):
        holders_table = (
            "<table><thead><tr><th>报告期</th><th>代码</th><th>名称</th><th>持有人</th><th>占比</th><th>变动</th></tr></thead>"
            "<tbody>" + "".join(
                f"<tr><td>{p['period']}</td><td>{i['code']}</td><td>{i['name']}</td><td>{i['holder']}</td><td>{i['ratio']}</td><td>{i.get('change','')}</td></tr>"
                for p in holders_periods for i in p.get("items", [])) + "</tbody></table>")
    else:
        holders_table = "<div class='note'>尚未录入本季度披露数据，季报发布后可编辑 data/holders.json 更新。</div>"

    # ---------- 汇总值 ----------
    inflow5d = snapshot.get("total_net_inflow_5d")
    inflow1d = snapshot.get("total_net_inflow_1d")
    anom_count = sum(1 for r in rows if r.get("flag"))

    def fmt_hy(v):
        return "-" if v is None else f"{v/1e8:,.2f}"

    html = (html
        .replace("{ECHARTS_SCRIPT}", _echarts_script())
        .replace("{DATE}", str(date))
        .replace("{GEN}", str(generated))
        .replace("{INFLOW5D}", fmt_hy(inflow5d))
        .replace("{INFLOW1D}", fmt_hy(inflow1d))
        .replace("{POOL_SIZE}", str(snapshot.get("pool_size", len(rows))))
        .replace("{ANOM_COUNT}", str(anom_count))
        .replace("{INFLOW_CLASS}", cls(inflow5d))
        .replace("{INFLOW1D_CLASS}", cls(inflow1d))
        .replace("{TREND_JSON}", trend_json)
        .replace("{TREND_CODES_JSON}", trend_codes_json)
        .replace("{CHG5D_JSON}", chg5d_json)
        .replace("{CHG1D_JSON}", chg1d_json)
        .replace("{NETFLOW_JSON}", netflow_json)
        .replace("{VOLRATIO_JSON}", volratio_json)
        .replace("{PREMIUM_JSON}", premium_json)
        .replace("{ALERTS_JSON}", alerts_json)
        .replace("{ALERT_ROWS}", alert_rows)
        .replace("{TABLE_ROWS}", table_html)
        .replace("{HOLDERS_NOTE}", holders_note)
        .replace("{HOLDERS_TABLE}", holders_table)
        .replace("{HOLDERS_JSON}", json.dumps(holders, ensure_ascii=False))
        .replace("{TABLE_ROWS_JS}", json.dumps(table_rows, ensure_ascii=False)))

    with open(DASHBOARD, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"[dashboard] {DASHBOARD} written ({os.path.getsize(DASHBOARD)} bytes)")
    return html


if __name__ == "__main__":
    s = None
    try:
        with open(os.path.join(DATA_DIR, "daily_snapshot.json"), "r", encoding="utf-8") as f:
            s = json.load(f)
    except Exception:
        pass
    build_dashboard(s)
