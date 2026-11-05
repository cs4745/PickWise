"""生成自包含的离线 HTML 分析报告（数据内联，无外部依赖）。"""

from __future__ import annotations

import datetime as dt
import json

from . import DISCLAIMER, __version__
from .backtest import DEFAULT_STRATEGIES, backtest_all
from .config import OUTPUT_DIR
from .recommend import STRATEGIES, recommend_all

TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>买什么 PickWise | 彩票历史数据分析报告</title>
<style>
:root{
  --bg:#f5f7fb; --card:#ffffff; --ink:#16233b; --ink2:#4a5b78; --ink3:#8493ad;
  --line:#e3e9f2; --primary:#2b5cd9; --primary-soft:#eaf0ff; --red:#e0484d;
  --blue:#2f7de1; --warm:#e8754b; --cool:#4b8bd8; --green:#1f9d6b;
  --shadow:0 1px 2px rgba(20,40,80,.04),0 8px 24px rgba(20,40,80,.06);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",system-ui,-apple-system,sans-serif;
  font-size:14px;line-height:1.65;-webkit-font-smoothing:antialiased}
a{color:var(--primary);text-decoration:none}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px 80px}
header.top{background:linear-gradient(120deg,#16294f 0%,#24448a 55%,#2b5cd9 100%);color:#fff;padding:34px 0 30px}
header.top .wrap{padding-bottom:0}
.brand{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.brand h1{margin:0;font-size:30px;letter-spacing:1px;font-weight:700}
.brand .en{font-size:17px;opacity:.75;letter-spacing:3px;font-weight:400}
.brand .ver{margin-left:auto;font-size:12px;opacity:.7}
.sub{margin-top:8px;opacity:.86;font-size:14px}
.disclaimer{background:#fff7ed;border:1px solid #f6c99a;border-left:4px solid #e8754b;
  border-radius:10px;padding:14px 18px;margin:22px 0 26px;color:#7a4318;font-size:13px;line-height:1.8}
.disclaimer b{color:#b4531a}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px;margin-bottom:26px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;box-shadow:var(--shadow)}
.card .k{color:var(--ink3);font-size:12px;letter-spacing:.5px}
.card .v{font-size:25px;font-weight:700;margin:6px 0 2px;letter-spacing:.5px}
.card .d{color:var(--ink2);font-size:12px}
.tabs{display:flex;gap:8px;margin:0 0 18px;flex-wrap:wrap}
.tab{border:1px solid var(--line);background:#fff;color:var(--ink2);padding:9px 22px;border-radius:999px;
  cursor:pointer;font-size:14px;font-weight:600;transition:.15s}
.tab:hover{border-color:var(--primary);color:var(--primary)}
.tab.on{background:var(--primary);border-color:var(--primary);color:#fff}
.panel{display:none}
.panel.on{display:block}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:900px){.grid2{grid-template-columns:1fr}}
section.box{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 22px;
  margin-bottom:16px;box-shadow:var(--shadow)}
section.box h2{margin:0 0 4px;font-size:17px;font-weight:700}
section.box .hint{color:var(--ink3);font-size:12px;margin:0 0 16px}
h3.sub-h{font-size:14px;margin:22px 0 10px;color:var(--ink2);font-weight:700;
  border-left:3px solid var(--primary);padding-left:9px}
.balls{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:10px 0 4px}
.ball{width:38px;height:38px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
  color:#fff;font-weight:700;font-size:15px;box-shadow:inset 0 -3px 6px rgba(0,0,0,.14)}
.ball.red{background:linear-gradient(145deg,#f0656a,#d5363c)}
.ball.blue{background:linear-gradient(145deg,#5a9bf0,#2466c9)}
.ball.purple{background:linear-gradient(145deg,#8b7bf0,#5c48cf)}
.ball.small{width:31px;height:31px;font-size:13px}
.ball .sep{color:#fff}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}
th{color:var(--ink3);font-weight:600;font-size:12px;background:#fafbfe}
tr:last-child td{border-bottom:none}
td.num{font-variant-numeric:tabular-nums}
.tag{display:inline-block;padding:1px 8px;border-radius:5px;font-size:11px;font-weight:600}
.tag.hot{background:#fdece6;color:#c25127}
.tag.cold{background:#e8f1fd;color:#2266b8}
.tag.ok{background:#e7f6ee;color:#177a52}
.tag.warn{background:#fff4e2;color:#a8620f}
.chart{width:100%;overflow-x:auto}
svg{display:block;max-width:100%;height:auto}
svg text{font-family:inherit}
.note{background:#f6f8fc;border:1px solid var(--line);border-radius:8px;padding:12px 14px;
  color:var(--ink2);font-size:12.5px;margin-top:14px;line-height:1.8}
.note.strong{background:#eef4ff;border-color:#c9dbff;color:#24427f}
.combo{background:#fafbff;border:1px solid var(--line);border-radius:9px;padding:11px 13px;margin-bottom:9px}
.combo .no{font-size:11px;color:var(--ink3);margin-bottom:5px}
.combo .nums{display:flex;gap:5px;flex-wrap:wrap;align-items:center}
.combo .why{font-size:11.5px;color:var(--ink3);margin-top:6px;line-height:1.6}
.strat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(255px,1fr));gap:14px}
.strat{background:#fbfcff;border:1px solid var(--line);border-radius:10px;padding:14px}
.strat h4{margin:0 0 3px;font-size:14px}
.strat .desc{font-size:11.5px;color:var(--ink3);min-height:34px;margin-bottom:9px}
.foot{color:var(--ink3);font-size:12px;text-align:center;margin-top:30px;line-height:2}
.kv{display:flex;flex-wrap:wrap;gap:8px 26px;font-size:13px;color:var(--ink2);margin-top:8px}
.kv b{color:var(--ink);font-weight:600}
.legend{display:flex;gap:16px;font-size:11.5px;color:var(--ink3);margin:6px 0 0}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
</style>
</head>
<body>
<header class="top"><div class="wrap">
  <div class="brand"><h1>买什么</h1><span class="en">PickWise</span>
    <span class="ver">v__VERSION__ · 生成于 __TIME__</span></div>
  <div class="sub">双色球 / 超级大乐透 / 七星彩 —— 历史开奖数据的统计分析与随机性研究工具</div>
</div></header>
<div class="wrap">
  <div class="disclaimer"><b>重要声明</b>　__DISCLAIMER__<br>
  本报告展示的「参考组合」只是历史统计加权的随机抽样结果，<b>不是预测，也不构成购买建议</b>；
  其单注中奖概率与任意一组手写号码完全相同。</div>
  <div class="cards" id="cards"></div>
  <div class="tabs" id="tabs"></div>
  <div id="panels"></div>
  <div class="foot">
    数据来源：中国福利彩票发行管理中心、国家体育总局体育彩票管理中心公开开奖公告及公开历史数据，采集口径详见各彩种说明。<br>
    理性购彩 · 量力而行 · 未满 18 周岁禁止购彩 · 本工具不提供代购、投注或任何资金服务。<br>
    买什么 PickWise v__VERSION__ · 仅用于统计学习与娱乐
  </div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const G=D.games;
const COL={red:'#e0484d',blue:'#2f7de1',purple:'#6f5bd6',warm:'#e8754b',cool:'#4b8bd8',
           primary:'#2b5cd9',grid:'#e8edf5',ink:'#4a5b78',green:'#1f9d6b'};
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmt=(n,d=2)=>Number(n).toFixed(d);

function svgBar(labels,values,opt={}){
  const W=720,H=opt.height||230,L=44,R=12,T=14,B=34;
  const iw=W-L-R,ih=H-T-B,max=Math.max(...values,opt.ref||0,1)*1.12;
  const n=values.length,bw=iw/n,gap=Math.min(4,bw*.18);
  let bars='',lbl='',ref='';
  values.forEach((v,i)=>{
    const h=Math.max(1,v/max*ih),x=L+i*bw+gap/2,y=T+ih-h;
    const c=opt.colors?opt.colors[i]:(opt.color||COL.primary);
    bars+=`<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${(bw-gap).toFixed(1)}" height="${h.toFixed(1)}" rx="2" fill="${c}" opacity=".88"><title>${esc(labels[i])}: ${fmt(v,opt.dec||0)}</title></rect>`;
    const step=n>24?Math.ceil(n/16):1;
    if(i%step===0)lbl+=`<text x="${(x+bw/2).toFixed(1)}" y="${H-12}" font-size="10" fill="${COL.ink}" text-anchor="middle">${esc(labels[i])}</text>`;
  });
  [0,.5,1].forEach(t=>{
    const y=T+ih-t*ih;
    ref+=`<line x1="${L}" y1="${y}" x2="${W-R}" y2="${y}" stroke="${COL.grid}" stroke-width="1"/>`+
         `<text x="${L-7}" y="${y+3}" font-size="10" fill="${COL.ink}" text-anchor="end">${fmt(t*max,0)}</text>`;
  });
  let refline='';
  if(opt.ref){const y=T+ih-opt.ref/max*ih;
    refline=`<line x1="${L}" y1="${y}" x2="${W-R}" y2="${y}" stroke="${COL.red}" stroke-width="1.4" stroke-dasharray="5 4"/>`+
            `<text x="${W-R-4}" y="${y-5}" font-size="10" fill="${COL.red}" text-anchor="end">理论期望 ${fmt(opt.ref,1)}</text>`;}
  return `<svg viewBox="0 0 ${W} ${H}" role="img">${ref}${bars}${refline}${lbl}</svg>`;
}
function svgLine(values,labels,opt={}){
  const W=720,H=opt.height||210,L=44,R=12,T=14,B=30;
  const iw=W-L-R,ih=H-T-B,mn=Math.min(...values),mx=Math.max(...values);
  const lo=mn-(mx-mn)*.12-1,hi=mx+(mx-mn)*.12+1,avg=values.reduce((a,b)=>a+b,0)/values.length;
  const X=i=>L+i*iw/Math.max(1,values.length-1),Y=v=>T+ih-(v-lo)/(hi-lo)*ih;
  let path='',grid='';
  values.forEach((v,i)=>{path+=(i?' L':'M')+X(i).toFixed(1)+' '+Y(v).toFixed(1)});
  [0,.5,1].forEach(t=>{const y=T+ih-t*ih,v=lo+t*(hi-lo);
    grid+=`<line x1="${L}" y1="${y}" x2="${W-R}" y2="${y}" stroke="${COL.grid}"/>`+
          `<text x="${L-7}" y="${y+3}" font-size="10" fill="${COL.ink}" text-anchor="end">${fmt(v,0)}</text>`;});
  const ay=Y(avg);
  grid+=`<line x1="${L}" y1="${ay}" x2="${W-R}" y2="${ay}" stroke="${COL.green}" stroke-dasharray="5 4" stroke-width="1.2"/>`+
        `<text x="${W-R-3}" y="${ay-5}" font-size="10" fill="${COL.green}" text-anchor="end">均值 ${fmt(avg,1)}</text>`;
  const step=Math.ceil(labels.length/8);
  let xl='';labels.forEach((l,i)=>{if(i%step===0)xl+=`<text x="${X(i).toFixed(1)}" y="${H-9}" font-size="10" fill="${COL.ink}" text-anchor="middle">${esc(l)}</text>`;});
  return `<svg viewBox="0 0 ${W} ${H}" role="img">${grid}<path d="${path}" fill="none" stroke="${opt.color||COL.primary}" stroke-width="1.7" stroke-linejoin="round"/>${xl}</svg>`;
}
function balls(front,back,key,small=false){
  const fc=key==='qxc'?COL.purple:COL.red;
  const f=front.map(x=>`<span class="ball ${key==='qxc'?'purple':'red'} ${small?'small':''}">${String(x).padStart(2,'0')}</span>`).join('');
  const b=back.map(x=>`<span class="ball blue ${small?'small':''}">${String(x).padStart(2,'0')}</span>`).join('');
  return `<div class="balls">${f}<span style="color:#a7b4c9;font-weight:700">+</span>${b}</div>`;
}
function hotColdTable(z,unit){
  const rows=(items,tag)=>items.map(x=>`<tr><td><span class="tag ${tag}">${String(x.number).padStart(2,'0')}</span></td>
    <td class="num">${x.count}</td><td class="num">${fmt(x.rate*100,2)}%</td>
    <td class="num">${x.recent} / ${fmt(x.recent_expected,1)}</td>
    <td class="num">${fmt(x.deviation,1)}</td><td class="num">${x.omission.current}</td>
    <td class="num">${x.omission.max}</td></tr>`).join('');
  const head=`<tr><th>${unit}</th><th>历史次数</th><th>出现率</th><th>近${z.recent_window}期 / 期望</th><th>与期望差</th><th>当前遗漏</th><th>最大遗漏</th></tr>`;
  return `<div class="grid2"><div><h3 class="sub-h">热号 Top ${z.hot.length}（近 ${z.recent_window} 期）</h3>
    <table>${head}${rows(z.hot,'hot')}</table></div>
    <div><h3 class="sub-h">冷号 Bottom ${z.cold.length}（近 ${z.recent_window} 期）</h3>
    <table>${head}${rows(z.cold,'cold')}</table></div></div>`;
}
function freqChart(z,title){
  return `<h3 class="sub-h">${title} · 全历史出现次数</h3>
  <div class="chart">${svgBar(z.numbers.map(n=>String(n).padStart(2,'0')),z.counts,
     {ref:z.expected,color:COL.blue,dec:0})}</div>
  <div class="legend"><span><i style="background:${COL.blue}"></i>实际出现次数</span>
  <span><i style="background:${COL.red}"></i>等概率假设下的理论期望</span></div>`;
}
function omissionChart(z,title){
  const vals=z.numbers.map(n=>z.omission[String(n)].current);
  const mx=Math.max(...vals);
  const colors=vals.map(v=>v>=mx*.75?COL.warm:(v===0?COL.green:COL.cool));
  return `<h3 class="sub-h">${title} · 当前遗漏（距上次出现的期数）</h3>
  <div class="chart">${svgBar(z.numbers.map(n=>String(n).padStart(2,'0')),vals,{color:COL.cool,colors:colors,dec:0,height:190})}</div>
  <div class="note">遗漏值只描述「已经多久没出现」。每期开奖独立，遗漏再长也不会提高下一期出现概率。</div>`;
}
function distTable(o,title){
  const tot=o.counts.reduce((a,b)=>a+b,0)||1;
  return `<h3 class="sub-h">${title}</h3><table><tr><th>取值</th><th>期数</th><th>占比</th></tr>`+
    o.labels.map((l,i)=>`<tr><td>${esc(l)}</td><td class="num">${o.counts[i]}</td>
    <td class="num">${fmt(o.counts[i]/tot*100,2)}%</td></tr>`).join('')+`</table>`;
}
function stratCard(r,key){
  return `<div class="strat"><h4>${esc(r.strategy_label)}型 <span class="tag ${r.strategy==='random'?'ok':'warn'}">${r.strategy==='random'?'对照基线':'统计加权'}</span></h4>
   <div class="desc">${esc(r.strategy_desc)}</div>
   ${r.combos.map(c=>`<div class="combo"><div class="no">第 ${c.index} 组</div>
     <div class="nums">${balls(c.front,c.back,key,true)}</div>
     <div class="why">${esc(c.reason)}</div></div>`).join('')}</div>`;
}
function backtestSection(b){
  const ss=Object.values(b.strategies);
  const labels=ss.map(s=>s.label),vals=ss.map(s=>s.mean_hits);
  const colors=ss.map(s=>s.strategy==='random'?COL.green:COL.primary);
  const rows=ss.map(s=>`<tr><td>${esc(s.label)}${s.strategy==='random'?' <span class="tag ok">基线</span>':''}</td>
    <td class="num">${fmt(s.mean_hits,3)}</td><td class="num">${fmt(s.mean_front_hits,3)}</td>
    <td class="num">${s.max_hits}</td><td class="num">${s.high_hit_rounds}</td>
    <td class="num">${s.diff_vs_random===undefined?'-':fmt(s.diff_vs_random,3)}</td>
    <td class="num">${s.z_vs_random===undefined?'-':fmt(s.z_vs_random,2)}</td>
    <td>${s.strategy==='random'?'-':(s.significant?'<span class="tag hot">显著</span>':'<span class="tag ok">不显著</span>')}</td></tr>`).join('');
  return `<section class="box"><h2>样本外回测：统计选号真的更准吗？</h2>
   <p class="hint">对最近 ${b.rounds} 期逐期回测，每期只用该期之前 ${b.window} 期历史生成 1 组号码，再与真实开奖号比对；无未来函数。</p>
   <div class="chart">${svgBar(labels,vals,{color:COL.primary,colors:colors,ref:b.theoretical_mean_hits,dec:3,height:200})}</div>
   <div class="legend"><span><i style="background:${COL.green}"></i>纯随机基线</span><span><i style="background:${COL.red}"></i>独立随机下的理论期望命中数 ${fmt(b.theoretical_mean_hits,3)}</span></div>
   <table style="margin-top:16px"><tr><th>策略</th><th>平均命中数</th><th>前区/前六位命中</th><th>单期最高</th>
     <th>命中≥4 的期数</th><th>与随机差</th><th>z 值</th><th>显著性</th></tr>${rows}</table>
   <div class="note strong">${esc(b.conclusion)}</div>
   </section>`;
}
function eraTable(a){
  const e=a.era_check;
  const rows=(list)=>list.map(x=>`<tr><td>${esc(x.label)}</td><td class="num">${x.count}</td>
    <td class="num">${x.chi2}</td><td class="num">${x.pvalue}</td>
    <td>${x.deviates?'<span class="tag hot">偏离</span>':'<span class="tag ok">一致</span>'}</td></tr>`).join('');
  const head='<tr><th>年份</th><th>期数</th><th>χ²</th><th>p 值</th><th>结论</th></tr>';
  return `<h3 class="sub-h">分段均匀性检验（每 3 年一段）</h3>
   <p class="hint">按时间段分别检验，用于区分随机波动与历史规则调整 / 数据口径变化。</p>
   <div class="grid2"><div><b>${esc(a.zones.front.name)}</b><table>${head}${rows(e.front)}</table></div>
   <div><b>${esc(a.zones.back.name)}</b><table>${head}${rows(e.back)}</table></div></div>`;
}
function gamePanel(key){
  const g=G[key],a=g.analysis,zf=a.zones.front,zb=a.zones.back,s=a.structure;
  const recs=Object.values(g.recommendations);
  const recHtml=recs.map(r=>stratCard(r,key)).join('');
  const statCards=`
   <div class="kv"><span>覆盖期数 <b>${a.count.toLocaleString()}</b></span>
   <span>期号范围 <b>${esc(a.earliest.issue)} ~ ${esc(a.latest.issue)}</b></span>
   <span>开奖频率 <b>${esc(a.draw_days)}</b></span>
   <span>单注金额 <b>¥${a.price}</b></span>
   <span>一等奖理论概率 <b>${esc(g.recommendations.balanced.jackpot_odds)}</b></span></div>`;
  const positionTable=(!zf.combination&&zf.by_position)?
    `<h3 class="sub-h">七星彩 · 各数位 0~9 出现次数（按位统计）</h3><table><tr><th>位置</th>${zf.numbers.map(n=>`<th>${n}</th>`).join('')}</tr>`+
    zf.by_position.map((row,i)=>`<tr><td>第 ${i+1} 位</td>${row.map(v=>`<td class="num">${v}</td>`).join('')}</tr>`).join('')+`</table>`:'';
  return `<div class="panel ${key==='ssq'?'on':''}" id="p-${key}">
   <section class="box"><h2>${esc(a.name)} <span style="font-size:12px;color:var(--ink3);font-weight:400">${esc(a.org)}</span></h2>
    <p class="hint">选号规则：${esc(a.rules)}</p>
    ${statCards}
    <h3 class="sub-h">最新开奖 · 第 ${esc(a.latest.issue)} 期 ${a.latest.date?'（'+esc(a.latest.date)+'）':''}</h3>
    ${balls(a.latest.front,a.latest.back,key)}
    <div class="note"><b>数据源</b>　${esc(a.source_desc)}
      ${a.data_notes?'<br><b>数据口径提示</b>　'+esc(a.data_notes):''}</div>
   </section>
   <section class="box"><h2>热号 / 冷号</h2>
    <p class="hint">热冷按近 ${zf.recent_window} 期出现次数排序；「与期望差」为全历史出现次数减去等概率理论期望。</p>
    ${hotColdTable(zf,zf.name)}
    <h3 class="sub-h">${esc(zb.name)}（独立选号区）</h3>
    ${hotColdTable(zb,zb.name)}
   </section>
   <section class="box"><h2>频率与遗漏</h2>
    <p class="hint">若开奖完全随机，各号码出现次数应围绕理论期望小幅波动。</p>
    ${freqChart(zf,zf.name)}
    ${freqChart(zb,zb.name)}
    ${positionTable}
    ${omissionChart(zf,zf.name)}
    <div class="note"><b>均匀性检验（卡方拟合优度）</b><br>
      ${esc(zf.name)}：χ²=${zf.chi2.stat}，df=${zf.chi2.df}，p=${zf.chi2.pvalue} —— ${esc(zf.chi2.conclusion)}<br>
      ${esc(zb.name)}：χ²=${zb.chi2.stat}，df=${zb.chi2.df}，p=${zb.chi2.pvalue} —— ${esc(zb.chi2.conclusion)}</div>
    ${eraTable(a)}
   </section>
   <section class="box"><h2>号码结构分布</h2>
    <p class="hint">和值、奇偶、大小等结构只能描述历史形态，对下一期没有预测作用。</p>
    <h3 class="sub-h">和值分布（${s.type==='digits'?'数字和':zf.name+'之和'}）</h3>
    <div class="chart">${svgBar(s.sum.hist.labels,s.sum.hist.counts,{color:COL.primary,dec:0,height:200})}</div>
    <div class="kv"><span>均值 <b>${s.sum.mean}</b></span><span>范围 <b>${s.sum.min} ~ ${s.sum.max}</b></span>
      <span>10%~90% 分位 <b>${s.sum.p10} ~ ${s.sum.p90}</b></span>
      <span>相邻期和值自相关 <b>${s.sum_lag1_corr}</b>（应接近 0）</span></div>
    <h3 class="sub-h">近 ${a.trend.length} 期和值走势</h3>
    <div class="chart">${svgLine(s.sum.values,a.trend.map(t=>t.issue),{color:COL.blue})}</div>
    <div class="grid2" style="margin-top:10px">
      ${s.type==='combination'?distTable(s.odd_count,'前区奇数个数分布')+distTable(s.big_count,'前区大号个数分布'):
        `<div class="note">七星彩为按位独立数字，不适用组合型的奇偶比 / 大小比 / AC 值分析。<br>
        历史上与前一期同位数字相同的平均个数：<b>${s.position_hit_mean}</b>，独立随机下的理论值 <b>${s.position_hit_theoretical}</b>。</div>`}
      <div><h3 class="sub-h">其他结构指标</h3><table>
        <tr><th>指标</th><th>历史值</th><th>说明</th></tr>
        <tr><td>平均跨度</td><td class="num">${s.span?s.span.mean:s.distinct_mean}</td><td>${s.span?'最大号减最小号':'平均不同数字个数'}</td></tr>
        ${s.consecutive_rate!==undefined?`<tr><td>含连号比例</td><td class="num">${fmt(s.consecutive_rate*100,2)}%</td><td>出现相邻号码的期数占比</td></tr>`:''}
        ${s.repeat_mean!==undefined?`<tr><td>与上期重号均值</td><td class="num">${s.repeat_mean}</td><td>随机理论值 ${s.repeat_theoretical}</td></tr>`:''}
        <tr><td>和值 lag-1 自相关</td><td class="num">${s.sum_lag1_corr}</td><td>接近 0 表示无短期记忆</td></tr>
      </table></div>
    </div>
    ${s.third_ratio_top?`<h3 class="sub-h">最常见的三区比</h3><table><tr><th>一区:二区:三区</th><th>出现期数</th></tr>`+
      s.third_ratio_top.map(x=>`<tr><td>${esc(x.ratio)}</td><td class="num">${x.count}</td></tr>`).join('')+`</table>`:''}
   </section>
   ${backtestSection(g.backtest)}
   <section class="box"><h2>参考组合（娱乐演示，非购买建议）</h2>
    <p class="hint">四组策略使用同一随机种子，便于对比；所有组合的单注中奖概率均为 ${esc(g.recommendations.balanced.jackpot_odds)}，完全相同。</p>
    <div class="strat-grid">${recHtml}</div>
    <div class="note strong"><b>请理性看待</b>　${esc(g.recommendations.balanced.notice)}
      报告中的「参考组合」是统计分析结果的可视化演示，<b>不是、也不应被当作购买建议</b>。
      如需购彩，请自行决定并自行承担风险；不购彩当然也完全可以。</div>
   </section>
   <section class="box"><h2>关于「买什么」的认真回答</h2>
    <p class="hint">这是本工具唯一会给出的购买建议，它不基于任何号码预测。</p>
    <table><tr><th style="width:150px">问题</th><th>基于数据的回答</th></tr>
      <tr><td>有没有必中 / 提高中奖率的选号法？</td><td>没有。每期开奖独立，任意一组号码的单注中奖概率完全相同（本彩种一等奖 ${esc(g.recommendations.balanced.jackpot_odds)}）。上面的回测也显示统计选号与纯随机无显著差异。</td></tr>
      <tr><td>长期买彩票能赚钱吗？</td><td>不能。按彩票资金分配规则，返奖奖金只占销售额的一部分，另含公益金与发行费用，单注期望回报低于投入；投入越多，长期损失越接近确定。</td></tr>
      <tr><td>如果仍想偶尔买呢？</td><td>把它当娱乐消费：先设定每月固定上限并严格执行，只用闲钱，不追号、不加倍、不借贷、不把「差一个号」当作继续投入的理由。</td></tr>
      <tr><td>什么情况下应当停止？</td><td>超出预算、试图靠购彩弥补亏损、影响工作生活或人际关系时请立即停止并主动寻求帮助。未满 18 周岁禁止购彩。</td></tr>
    </table>
    <div class="note strong">最优的「买什么」是量力而行，或者不买。本工具不会告诉您该押哪一组号能赢，因为那样说是假的。</div>
   </section>
  </div>`;
}
// 渲染
const order=['ssq','dlt','qxc'];
document.getElementById('cards').innerHTML=order.map(k=>{const a=G[k].analysis,b=G[k].backtest;
  return `<div class="card"><div class="k">${esc(a.name)} · 已采集</div><div class="v">${a.count.toLocaleString()} <span style="font-size:14px;font-weight:400">期</span></div>
   <div class="d">最新第 ${esc(a.latest.issue)} 期 · 回测 ${b.rounds} 期</div></div>`}).join('')+
  `<div class="card"><div class="k">回测结论</div><div class="v" style="font-size:18px;color:var(--green)">统计选号 ≈ 纯随机</div>
   <div class="d">历史冷热号未带来显著命中优势</div></div>`;
document.getElementById('tabs').innerHTML=order.map((k,i)=>
  `<button class="tab ${i===0?'on':''}" data-k="${k}">${esc(G[k].analysis.name)}</button>`).join('');
document.getElementById('panels').innerHTML=order.map(k=>gamePanel(k)).join('');
document.querySelectorAll('.tab').forEach(btn=>btn.addEventListener('click',()=>{
  document.querySelectorAll('.tab').forEach(b=>b.classList.remove('on'));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('on'));
  btn.classList.add('on');
  document.getElementById('p-'+btn.dataset.k).classList.add('on');
  window.scrollTo({top:document.querySelector('.tabs').offsetTop-16,behavior:'smooth'});
}));
</script>
</body></html>
"""


def build_data(keys=None, rec_count=3, rounds=200, window=250, seed=20261105):
    from .analyze import analyze_all
    from .backtest import backtest_all as _bt
    from .config import GAME_ORDER
    keys = keys or list(GAME_ORDER)
    analyses = analyze_all(keys)
    backtests = _bt(keys, rounds=rounds, window=window, seed=seed)
    recs = {}
    for st in DEFAULT_STRATEGIES:
        part = recommend_all(keys, strategy=st, count=rec_count, seed=seed)
        for k in keys:
            recs.setdefault(k, {})[st] = part[k]
    return {
        "meta": {
            "version": __version__,
            "generated_at": dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            "disclaimer": DISCLAIMER,
        },
        "games": {
            k: {"analysis": analyses[k], "recommendations": recs[k], "backtest": backtests[k]}
            for k in keys
        },
    }


def generate(data=None, filename="report.html"):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = data or build_data()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    html = (TEMPLATE.replace("__DATA__", payload)
            .replace("__DISCLAIMER__", DISCLAIMER)
            .replace("__VERSION__", __version__)
            .replace("__TIME__", data["meta"]["generated_at"]))
    path = OUTPUT_DIR / filename
    path.write_text(html, encoding="utf-8")
    (OUTPUT_DIR / "analysis.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, data
