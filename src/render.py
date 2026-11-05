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
const NETFLOW = {NETFLOW_JSON};
const THEME = {color:['#3d7eff','#ffb84d','#2ecc71','#f4504e','#a78bfa','#38bdf8','#fb923c','#4ade80','#f472b6','#eab308']};

// 份额趋势
(function(){
  const chart = echarts.init(document.getElementById('trend'));
  const series = TREND_CODES.map((c, i) => ({
    name: c, type:'line', data: TREND[c], smooth:true, showSymbol:false,
    lineStyle:{width:2}, itemStyle:{color:THEME.color[i%10]}
  }));
  chart.setOption({
    backgroundColor:'transparent',
    tooltip:{trigger:'axis'},
    legend:{textStyle:{color:'#8a97b5'}, top:0},
    grid:{left:55,right:20,top:34,bottom:30},
    xAxis:{type:'category',data:[],axisLabel:{color:'#8a97b5'},axisLine:{lineStyle:{color:'#24304a'}}},
    yAxis:{type:'value',axisLabel:{color:'#8a97b5'},splitLine:{lineStyle:{color:'rgba(36,48,74,.5)'}}},
    series: series
  });
  // 日期轴用份额行数对齐
  chart.setOption({xAxis:{data:TREND.dates || []}});
})();

// 5日份额变化率
(function(){
  const chart = echarts.init(document.getElementById('chg5d'));
  chart.setOption({
    backgroundColor:'transparent',
    tooltip:{trigger:'axis'},
    grid:{left:90,right:30,top:10,bottom:30},
    xAxis:{type:'value',axisLabel:{color:'#8a97b5'},splitLine:{lineStyle:{color:'rgba(36,48,74,.5)'}}},
    yAxis:{type:'category',data:CHG5D.names,axisLabel:{color:'#8a97b5'}},
    series:[{type:'bar',data:CHG5D.vals,itemStyle:{color:function(p){return p.value>=0?'#f4504e':'#2ecc71'}},label:{show:true,position:'right',color:'#dbe4f5',formatter:'{c}%'}}]
  });
})();

// 5日净流入
(function(){
  const chart = echarts.init(document.getElementById('netflow'));
  chart.setOption({
    backgroundColor:'transparent',
    tooltip:{trigger:'axis'},
    grid:{left:90,right:40,top:10,bottom:30},
    xAxis:{type:'value',axisLabel:{color:'#8a97b5'},splitLine:{lineStyle:{color:'rgba(36,48,74,.5)'}}},
    yAxis:{type:'category',data:NETFLOW.names,axisLabel:{color:'#8a97b5'}},
    series:[{type:'bar',data:NETFLOW.vals,itemStyle:{color:function(p){return p.value>=0?'#f4504e':'#2ecc71'}},label:{show:true,position:'right',color:'#dbe4f5',formatter:'{c}'}}]
  });
})();
</script>
</body>
</html>"""

    # ---------- 数据填充 ----------
    def fmt(v, digits=2, unit=""):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "-"
        return f"{v:.{digits}f}{unit}"

    inflow5d = snapshot.get("total_net_inflow_5d")
    inflow1d = snapshot.get("total_net_inflow_1d")
    inflow5d_yi = inflow5d / 1e8 if inflow5d is not None else None
    inflow1d_yi = inflow1d / 1e8 if inflow1d is not None else None

    # 异动表
    alert_rows = ""
    for r in table_rows:
        if r["flag"]:
            alert_rows += (f"<tr><td>{r['name']}</td><td>{r['category']}</td>"
                           f"<td class='flag'>{fmt(r['score'],1)}</td>"
                           f"<td class='num {('up' if (r['chg1d_pct'] or 0)>=0 else 'down')}'>{fmt(r['chg1d_pct'])}%</td>"
                           f"<td class='num {('up' if (r['chg5d_pct'] or 0)>=0 else 'down')}'>{fmt(r['chg5d_pct'])}%</td>"
                           f"<td class='num'>{fmt(r['vol_ratio'])}x</td>"
                           f"<td class='num {('up' if (r['net5d'] or 0)>=0 else 'down')}'>{fmt(r['net5d']/1e8 if r['net5d'] else None)}</td></tr>")
    if not alert_rows:
        alert_rows = "<tr><td colspan='7' style='color:var(--sub)'>当前无显著异动（阈值：异动分≥40）</td></tr>"

    # 明细表
    table_rows_html = ""
    for r in table_rows:
        mkt_pill = "<span class='pill pill-sh'>沪</span>" if r["code"].startswith(("5", "6")) else "<span class='pill pill-sz'>深</span>"
        flag_html = "<span class='pill pill-anom'>异动</span>" if r["flag"] else ""
        table_rows_html += (f"<tr><td>{r['code']}</td><td>{r['name']}{flag_html}</td><td>{r['category']}</td><td>{mkt_pill}</td>"
                            f"<td class='num'>{fmt(r['share']/1e8 if r['share'] else None)}</td>"
                            f"<td class='num {('up' if (r['chg1d_pct'] or 0)>=0 else 'down')}'>{fmt(r['chg1d_pct'])}%</td>"
                            f"<td class='num {('up' if (r['chg5d_pct'] or 0)>=0 else 'down')}'>{fmt(r['chg5d_pct'])}%</td>"
                            f"<td class='num {('up' if (r['chg20d_pct'] or 0)>=0 else 'down')}'>{fmt(r['chg20d_pct'])}%</td>"
                            f"<td class='num {('up' if (r['net5d'] or 0)>=0 else 'down')}'>{fmt(r['net5d']/1e8 if r['net5d'] else None)}</td>"
                            f"<td class='num'>{fmt(r['vol_ratio'])}x</td>"
                            f"<td class='num {('up' if (r['premium'] or 0)>=0 else 'down')}'>{fmt(r['premium'])}%</td>"
                            f"<td class='num'>{fmt(r['nav'])}</td></tr>")

    # 持有人表
    holders_note = holders.get("note", "")
    holders_table = ""
    for p in holders.get("periods", []):
        items = p.get("items", [])
        if items:
            rows_html = "".join(
                f"<tr><td>{it.get('code','')}</td><td>{it.get('name','')}</td>"
                f"<td>{it.get('holder','')}</td><td>{it.get('ratio','')}</td><td>{it.get('change','')}</td></tr>"
                for it in items)
            holders_table += (f"<div style='margin-top:10px'><b>{p['period']}</b>"
                              f"<table style='margin-top:6px'><thead><tr><th>代码</th><th>ETF</th><th>持有人</th><th>持仓占比</th><th>变化</th></tr></thead>"
                              f"<tbody>{rows_html}</tbody></table></div>")
    if not holders_table:
        holders_table = "<div class='note' style='margin-top:8px'>尚未录入本季度披露数据，季报发布后可编辑 data/holders.json 更新。</div>"

    # 图表 JSON
    chg5d_names = [r["name"] for r in rows]
    chg5d_vals = [round(r.get("share_chg_5d_pct") or 0, 2) for r in rows]
    netflow_names = [r["name"] for r in rows]
    netflow_vals = [round((r.get("net_inflow_5d") or 0) / 1e8, 2) for r in rows]

    html = html.replace("{DATE}", date)
    html = html.replace("{ECHARTS_SCRIPT}", _echarts_script())
    html = html.replace("{GEN}", generated)
    html = html.replace("{INFLOW5D}", fmt(inflow5d_yi))
    html = html.replace("{INFLOW5D_CLASS}", ("up" if (inflow5d_yi or 0) >= 0 else "down"))
    html = html.replace("{INFLOW1D}", fmt(inflow1d_yi))
    html = html.replace("{INFLOW1D_CLASS}", ("up" if (inflow1d_yi or 0) >= 0 else "down"))
    html = html.replace("{POOL_SIZE}", str(snapshot.get("pool_size", len(etfs))))
    html = html.replace("{ANOM_COUNT}", str(sum(1 for r in table_rows if r["flag"])))
    html = html.replace("{ALERT_ROWS}", alert_rows)
    html = html.replace("{TABLE_ROWS}", table_rows_html)
    html = html.replace("{HOLDERS_NOTE}", holders_note.replace("<", "&lt;").replace(">", "&gt;"))
    html = html.replace("{HOLDERS_TABLE}", holders_table)
    html = html.replace("{TREND_JSON}", json.dumps({**trend_series, "dates": trend_dates}, ensure_ascii=False))
    html = html.replace("{TREND_CODES_JSON}", json.dumps(focus_codes))
    html = html.replace("{CHG5D_JSON}", json.dumps({"names": chg5d_names, "vals": chg5d_vals}, ensure_ascii=False))
    html = html.replace("{NETFLOW_JSON}", json.dumps({"names": netflow_names, "vals": netflow_vals}, ensure_ascii=False))

    with open(DASHBOARD, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"[dashboard] saved {DASHBOARD} ({os.path.getsize(DASHBOARD)} bytes)")
    return DASHBOARD


if __name__ == "__main__":
    build_dashboard(None)
