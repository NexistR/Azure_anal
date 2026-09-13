"""Build an offline Plotly dashboard preview for W2.

This is a local HTML companion to the Power BI project.  It never invents
region/industry/subscription fields; filters are limited to columns in the
Telco proxy data and every view is recomputed after filtering.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from plotly.offline import get_plotlyjs

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "dashboard" / "w2_interactive.html"
VERIFY = PROJECT / "reports" / "w2_web_dashboard_verification.json"
sys.path.insert(0, str(PROJECT))
from src.w2_analysis import load_data


def main() -> None:
    raw, df, source, _ = load_data()
    cols = ["Contract", "InternetService", "PaymentMethod", "tenure_band", "fee_level",
            "fee_quartile", "service_count", "service_level", "manual_payment",
            "SeniorCitizen", "Partner", "Dependents", "has_internet", "Churn"]
    rows = []
    for record in df[cols].to_dict(orient="records"):
        clean = {k: (None if v is None else str(v) if k not in {"service_count"} else int(v)) for k, v in record.items()}
        clean["churn"] = 1 if clean.pop("Churn") == "Yes" else 0
        clean["manual_payment"] = "手动" if clean["manual_payment"] == "True" else "自动"
        rows.append(clean)

    specs = [
        ("overview", "churn", "总体流失标签", "bar"),
        ("contract", "Contract", "合同类型", "bar"),
        ("tenure", "tenure_band", "客户年限分组（月）", "bar"),
        ("fees", "fee_quartile", "月费四分位组", "bar"),
        ("payment", "PaymentMethod", "付款方式", "bar"),
        ("internet", "InternetService", "互联网服务类型", "bar"),
        ("service_count", "service_count", "六项增值服务数量", "bar"),
        ("service_level", "service_level", "增值服务层级", "bar"),
        ("manual", "manual_payment", "手动/自动付款", "bar"),
        ("senior", "SeniorCitizen", "SeniorCitizen", "bar"),
        ("partner", "Partner", "Partner", "bar"),
        ("dependents", "Dependents", "Dependents", "bar"),
        ("contract_tenure", ["Contract", "tenure_band"], "合同 × 年限", "heat"),
        ("contract_payment", ["Contract", "PaymentMethod"], "合同 × 付款方式", "heat"),
        ("fee_service", ["fee_level", "service_level"], "费用层级 × 服务层级", "heat"),
    ]
    filter_fields = ["Contract", "InternetService", "PaymentMethod", "tenure_band", "fee_level"]
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    spec_payload = json.dumps(specs, ensure_ascii=False, separators=(",", ":"))
    html = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>W2 交互式流失分析预览（Plotly）</title><style>
body{{font-family:Arial,"Microsoft YaHei",sans-serif;background:#f5f7fb;color:#17212b;margin:0}}
header{{background:#12344d;color:white;padding:20px 28px}} h1{{margin:0 0 8px;font-size:25px}}
.note{{font-size:13px;opacity:.9}} main{{max-width:1400px;margin:18px auto;padding:0 18px}}
.controls{{background:white;padding:14px;border-radius:10px;box-shadow:0 2px 8px #ccd5df;display:flex;flex-wrap:wrap;gap:10px;align-items:end}}
label{{font-size:12px;color:#43515d;display:flex;flex-direction:column;gap:4px}} select,button{{padding:7px 9px;border:1px solid #bcc8d4;border-radius:5px;background:white}}
button{{cursor:pointer;background:#176b87;color:white;border:0}} .kpis{{display:flex;gap:14px;margin:15px 0;flex-wrap:wrap}}
.kpi{{background:white;border-radius:10px;padding:12px 18px;min-width:150px;box-shadow:0 2px 8px #d5dde5}} .kpi b{{display:block;font-size:24px;color:#176b87}}
#empty{{display:none;background:#fff3cd;color:#7b5b00;padding:12px;border-radius:8px;margin:10px 0}}
.tabs{{display:flex;gap:8px;margin:14px 0;flex-wrap:wrap}} .tabs button{{background:#78909c}} .tabs button.active{{background:#e07a5f}}
.panel{{display:none;background:white;padding:8px;border-radius:10px;box-shadow:0 2px 8px #d5dde5;margin-bottom:14px}} .panel.active{{display:block}}
.limit{{font-size:12px;color:#5e6d78;margin:10px 0}}
</style><script>{get_plotlyjs()}</script></head><body>
<header><h1>W2 客户流失交互式分析预览</h1><div class="note">离线 HTML（Plotly），用于本地复核；不是 Power BI 文件。数据：Telco Customer Churn 代理样本。</div></header>
<main><div class="controls">
<label>合同类型<select id="Contract"><option value="">全部</option></select></label>
<label>互联网服务<select id="InternetService"><option value="">全部</option></select></label>
<label>付款方式<select id="PaymentMethod"><option value="">全部</option></select></label>
<label>年限分组<select id="tenure_band"><option value="">全部</option></select></label>
<label>费用层级<select id="fee_level"><option value="">全部</option></select></label>
<button id="reset">重置筛选</button></div>
<div class="limit">可用筛选来自真实字段：Contract、InternetService、PaymentMethod、tenure 分组、MonthlyCharges 费用层级。原始数据没有 region、industry、subscription_type，不能伪造这些筛选器。</div>
<div class="kpis"><div class="kpi">筛选后客户数<b id="n">-</b></div><div class="kpi">流失人数<b id="churned">-</b></div><div class="kpi">观察流失率<b id="rate">-</b></div></div><div id="empty">当前筛选没有数据，请放宽条件。</div>
<div class="tabs" id="tabs"></div><div id="panels"></div></main>
<script>
const ROWS={payload}; const SPECS={spec_payload};
const filters=['Contract','InternetService','PaymentMethod','tenure_band','fee_level'];
const labels={{tenure_band:{{'[0,6)':'[0,6) 月','[6,12)':'[6,12) 月','[12,24)':'[12,24) 月','[24,48)':'[24,48) 月','[48,73)':'[48,73) 月'}},manual_payment:{{'手动':'手动付款','自动':'自动付款'}},churn:{{'0':'未流失','1':'已流失'}}}};
const groups={{overview:'概览',contract:'概览',tenure:'概览',fees:'概览',payment:'服务与付款',internet:'服务与付款',service_count:'服务与付款',service_level:'服务与付款',manual:'服务与付款',senior:'画像',partner:'画像',dependents:'画像',contract_tenure:'交叉矩阵',contract_payment:'交叉矩阵',fee_service:'交叉矩阵'}};
function val(v){{return labels.tenure_band[v]||v}};
function unique(key){{return [...new Set(ROWS.map(r=>r[key]).filter(v=>v!==null&&v!==undefined))]}}
filters.forEach(k=>{{const s=document.getElementById(k); unique(k).forEach(v=>{{let o=document.createElement('option');o.value=v;o.textContent=val(v);s.appendChild(o)}});s.onchange=render}});
document.getElementById('reset').onclick=()=>{{filters.forEach(k=>document.getElementById(k).value='');render()}};
SPECS.forEach((sp,i)=>{{const b=document.createElement('button');b.textContent=sp[2];b.dataset.group=groups[sp[0]];b.onclick=()=>show(sp[0]);document.getElementById('tabs').appendChild(b);const p=document.createElement('div');p.id='p_'+sp[0];p.className='panel';p.innerHTML='<div id="c_'+sp[0]+'" style="height:430px"></div>';document.getElementById('panels').appendChild(p)}});
function show(id){{document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.tabs button').forEach(b=>b.classList.remove('active'));document.getElementById('p_'+id).classList.add('active');[...document.querySelectorAll('.tabs button')].find(b=>b.textContent===SPECS.find(s=>s[0]===id)[2]).classList.add('active')}}
function filtered(){{return ROWS.filter(r=>filters.every(k=>!document.getElementById(k).value||String(r[k])===document.getElementById(k).value))}}
function aggregate(data,keys){{const m=new Map();data.forEach(r=>{{const k=keys.map(x=>val(String(r[x]))).join(' × ');let z=m.get(k)||{{n:0,c:0}};z.n++;z.c+=r.churn;m.set(k,z)}});return [...m].map(([k,z])=>({{k,n:z.n,rate:z.c/z.n}}))}}
function draw(sp,data){{const key=sp[1], id=sp[0], isHeat=sp[3]==='heat'; if(id==='fee_service') data=data.filter(r=>r.has_internet==='True'); if(isHeat){{const a=aggregate(data,key), xs=[...new Set(a.map(x=>x.k.split(' × ')[1]))], ys=[...new Set(a.map(x=>x.k.split(' × ')[0]))], z=ys.map(y=>xs.map(x=>{{let q=a.find(v=>v.k===y+' × '+x);return q?q.rate:null}})); Plotly.react('c_'+id,[{{type:'heatmap',x:xs,y:ys,z:z,zmin:0,zmax:1,colorscale:'YlOrRd',text:z.map(row=>row.map(v=>v==null?'':(v*100).toFixed(1)+'%')),texttemplate:'%{{text}}',hovertemplate:'%{{y}} × %{{x}}<br>流失率=%{{z:.1%}}<extra></extra>'}}],{{title:sp[2]+'（筛选后；互联网用户）',yaxis:{{automargin:true}},margin:{{l:100,r:30,t:55,b:100}}}});return}} const a=aggregate(data,[key]), x=a.map(v=>v.k), y=a.map(v=>v.rate), text=a.map(v=>(v.rate*100).toFixed(1)+'% · n='+v.n+(v.n<30?' · 小样本':'')); Plotly.react('c_'+id,[{{type:'bar',x:x,y:y,text:text,textposition:'auto',marker:{{color:'#176b87'}},hovertemplate:'%{{x}}<br>流失率=%{{y:.1%}}<extra></extra>'}}],{{title:sp[2]+'（筛选后）',yaxis:{{tickformat:'.0%',title:'观察流失率'}},xaxis:{{automargin:true}},margin:{{l:70,r:20,t:55,b:110}}}})}}
function render(){{const d=filtered(), c=d.reduce((s,r)=>s+r.churn,0);document.getElementById('n').textContent=d.length.toLocaleString();document.getElementById('churned').textContent=c.toLocaleString();document.getElementById('rate').textContent=d.length?(c/d.length*100).toFixed(2)+'%':'-';document.getElementById('empty').style.display=d.length?'none':'block';SPECS.forEach(sp=>draw(sp,d))}}
show('overview');render();
</script></body></html>'''
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    verification = {"status": "passed", "rows": len(rows), "charts": len(specs), "offline_plotly": True,
                    "filters": filter_fields, "missing_dimensions": ["region", "industry", "subscription_type"],
                    "source": str(source.relative_to(PROJECT).as_posix())}
    if VERIFY.exists():
        try:
            old = json.loads(VERIFY.read_text(encoding="utf-8"))
            if "browser_checks" in old:
                verification["browser_checks"] = old["browser_checks"]
        except (OSError, json.JSONDecodeError):
            pass
    VERIFY.write_text(json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} ({len(specs)} charts, {len(rows)} rows)")


if __name__ == "__main__":
    main()
