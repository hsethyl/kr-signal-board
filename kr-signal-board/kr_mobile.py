#!/usr/bin/env python3
"""IF-Convex KR 휴대폰 알림판 생성기 (표준 라이브러리만 사용)

실행: python3 kr_mobile.py [출력폴더]
 - 네이버 증권 일봉으로 코스피 상위 100 + 코스닥 상위 50 계산 (IF-Convex KR 규칙: 50일 신고가 돌파 매수,
   1ATR 손절, +2R 본전, 4ATR 추적, 매수 전용)
 - 출력폴더/index.html 생성 (Artifact 페이지 본문, doctype 없음)
 - 마지막 줄에 SUMMARY {json} 출력 → 알림 문구에 사용
"""
import json
import math
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
P = dict(N=50, stopM=1.0, trailM=4.0, beR=2.0, atrLen=20)
UA = {"User-Agent": "Mozilla/5.0"}


def get(url, enc="utf-8", tries=4):
    for k in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read().decode(enc, "ignore")
        except Exception:  # noqa: BLE001
            if k == tries - 1:
                raise
            time.sleep(1.5 * (k + 1))


def universe(kospi=100, kosdaq=50):
    out = []
    for mkt, n in (("KOSPI", kospi), ("KOSDAQ", kosdaq)):
        page, got = 1, 0
        while got < n:
            st = json.loads(get(f"https://m.stock.naver.com/api/stocks/marketValue/{mkt}?page={page}&pageSize=100")).get("stocks", [])
            if not st:
                break
            for s in st:
                if s.get("stockEndType") != "stock":
                    continue
                out.append({"code": s["itemCode"], "name": s["stockName"], "mkt": mkt})
                got += 1
                if got >= n:
                    break
            page += 1
    return out


def bars(code):
    t = get(f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count=600&requestType=0", "euc-kr")
    b = [(r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]))
         for r in (x.split("|") for x in re.findall(r'data="([^"]+)"', t)) if float(r[1]) > 0]
    now = datetime.now(KST)
    if b and b[-1][0] == now.strftime("%Y%m%d") and (now.hour, now.minute) < (15, 40):
        b.pop()
    return b


def atr_rma(h, l, c, n):
    out, prev, buf = [math.nan] * len(c), math.nan, []
    for i in range(len(c)):
        tr = h[i] - l[i] if i == 0 else max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        if math.isnan(prev):
            buf.append(tr)
            if len(buf) == n:
                prev = sum(buf) / n
                out[i] = prev
        else:
            prev = (tr + (n - 1) * prev) / n
            out[i] = prev
    return out


def convex(b):
    d = [x[0] for x in b]
    o, h, l, c = ([x[k] for x in b] for k in (1, 2, 3, 4))
    atr = atr_rma(h, l, c, P["atrLen"])
    pos, ep, risk, stop, best, be, pend, prisk = 0, math.nan, math.nan, math.nan, math.nan, False, 0, math.nan
    entry_d = sig_d = None
    trades = []
    for i in range(len(c)):
        if pend and not pos:
            pos, ep, risk = 1, o[i], prisk
            stop, best, be, entry_d = ep - risk, ep, False, d[i]
        pend = 0
        if pos and l[i] <= stop:
            trades.append({"entry": entry_d, "exit": d[i], "ep": ep, "px": min(o[i], stop), "r": (min(o[i], stop) - ep) / risk})
            pos = 0
        if i < P["N"] or math.isnan(atr[i]):
            continue
        hi = max(h[i - P["N"]:i])
        if pos:
            best = max(best, c[i])
            if not be and c[i] - ep >= P["beR"] * risk:
                be = True
            if be:
                stop = max(stop, ep, best - P["trailM"] * atr[i])
        elif c[i] > hi:
            pend, prisk, sig_d = 1, P["stopM"] * atr[i], d[i]
    return dict(pos=pos, ep=ep, risk=risk, stop=stop, be=be, pend=pend, prisk=prisk, entry_d=entry_d, sig_d=sig_d,
                trades=trades, hi_next=max(h[-P["N"]:]), close=c[-1], date=d[-1])


def one(u):
    try:
        b = bars(u["code"])
        if len(b) < P["N"] + P["atrLen"] + 5:
            return None
        r, y = convex(b), convex(b[:-1])
        last = r["date"]
        sold = [t for t in r["trades"] if t["exit"] == last]
        row = dict(u, date=last, close=r["close"], dist=(r["hi_next"] / r["close"] - 1) * 100)
        if r["pend"]:
            row.update(kind="buy", risk=r["prisk"], sig=r["sig_d"])
        elif sold:
            t = sold[-1]
            row.update(kind="sell", ep=t["ep"], px=t["px"], r=t["r"], entry=t["entry"])
        elif r["pos"]:
            raised = y["pos"] and r["stop"] > y["stop"] + 1e-9
            row.update(kind="hold", ep=r["ep"], risk=r["risk"], stop=r["stop"], be=r["be"], entry=r["entry_d"],
                       rnow=(r["close"] - r["ep"]) / r["risk"], raised=bool(raised), prev_stop=y["stop"] if y["pos"] else None)
        else:
            row.update(kind="wait")
        return row
    except Exception as e:  # noqa: BLE001
        print("  실패:", u["name"], e, file=sys.stderr)
        return None


PAGE = r"""<title>한국주식 신호 알림판</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet">
<style>
/* 레이아웃: 한 줄 세로 스택 — 오늘 할 일(매수·매도) → 보유 관리 → 감시 목록 */
:root{--bg:#f5f6f8;--card:#ffffff;--fg:#191f28;--dim:#6b7684;--line:#e5e8eb;--up:#e22c3c;--down:#1b64da;--warn:#b7791f;--warnbg:#fff7e6;--chip:#eef1f5;
--sans:"IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif;--mono:"IBM Plex Mono",ui-monospace,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#101318;--card:#1a1f27;--fg:#e8ebef;--dim:#98a2b0;--line:#2a313c;--up:#ff5a67;--down:#5b9bff;--warn:#e0b25a;--warnbg:#2a2214;--chip:#242b35;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#101318;--card:#1a1f27;--fg:#e8ebef;--dim:#98a2b0;--line:#2a313c;--up:#ff5a67;--down:#5b9bff;--warn:#e0b25a;--warnbg:#2a2214;--chip:#242b35;color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font:15px/1.55 var(--sans);padding-inline:16px;padding-block:18px 40px;max-width:640px;margin:0 auto}
h1{font-size:20px;margin:0;text-wrap:balance}
.meta{color:var(--dim);font-size:13px;margin-top:2px}
.warn{background:var(--warnbg);color:var(--warn);border-radius:10px;padding:10px 12px;font-size:13px;margin:14px 0}
.sum{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0}
.sum div{background:var(--card);border-radius:12px;padding:10px 12px}
.sum span{display:block;color:var(--dim);font-size:12px}
.sum b{font:500 22px var(--mono);font-variant-numeric:tabular-nums}
h2{font-size:15px;margin:22px 0 8px;display:flex;justify-content:space-between;align-items:baseline;gap:8px}
h2 small{color:var(--dim);font-weight:400;font-size:12px}
.list{display:flex;flex-direction:column;gap:8px}
.item{background:var(--card);border-radius:12px;padding:12px 14px;border-left:4px solid var(--line)}
.item.buy{border-left-color:var(--up)}.item.sell{border-left-color:var(--down)}.item.hold{border-left-color:var(--chip)}
.top{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap}
.name{font-weight:700;font-size:16px}.code{color:var(--dim);font-size:12px;margin-left:4px;font-family:var(--mono)}
.tag{font-size:12px;font-weight:700;padding:2px 8px;border-radius:99px;background:var(--chip);white-space:nowrap}
.tag.buy{background:var(--up);color:#fff}.tag.sell{background:var(--down);color:#fff}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:4px 12px;margin-top:8px;font-size:13px}
.kv div{display:flex;justify-content:space-between;gap:6px;min-width:0}
.kv span{color:var(--dim)}.kv b{font-family:var(--mono);font-weight:500;font-variant-numeric:tabular-nums}
.up{color:var(--up)}.down{color:var(--down)}
.note{font-size:12px;color:var(--dim);margin-top:6px}
a{color:var(--down);font-size:13px;text-decoration:none}
.empty{background:var(--card);border-radius:12px;padding:14px;color:var(--dim);font-size:14px}
.set{background:var(--card);border-radius:12px;padding:12px 14px;display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin-top:22px}
.set label{display:flex;flex-direction:column;font-size:12px;color:var(--dim);gap:4px;flex:1;min-width:130px}
input{font:15px var(--mono);padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);width:100%}
input:focus-visible,a:focus-visible,summary:focus-visible{outline:2px solid var(--down);outline-offset:2px}
details{margin-top:22px}summary{font-weight:700;cursor:pointer;font-size:15px}
.rules{font-size:13px;color:var(--dim);background:var(--card);border-radius:12px;padding:12px 14px;margin-top:22px}
.rules b{color:var(--fg)}
</style>
<header>
  <h1>한국주식 신호 알림판</h1>
  <div class="meta" id="meta"></div>
</header>
<div class="warn"><b>관찰용.</b> 대형주 33종목 2014~2026 검증에서 거래당 평균 +0.02R, 6개 기준 중 2개만 통과했습니다. 모의 기록용이며 투자 조언이 아닙니다.</div>
<div class="sum">
  <div><span>오늘 매수 신호</span><b class="up" id="nBuy">0</b></div>
  <div><span>오늘 매도</span><b class="down" id="nSell">0</b></div>
  <div><span>보유 중</span><b id="nHold">0</b></div>
</div>
<h2>매수 신호 <small>다음 거래일 시가에 매수</small></h2><div class="list" id="buy"></div>
<h2>매도 <small>오늘 손절가 도달</small></h2><div class="list" id="sell"></div>
<h2>보유 중 <small>손절가만 관리</small></h2><div class="list" id="hold"></div>
<details><summary>신고가 3% 이내 감시 목록</summary><div class="list" id="near" style="margin-top:8px"></div></details>
<div class="set">
  <label for="acct">계좌 금액 (원)<input id="acct" type="number" inputmode="numeric" value="10000000" step="100000" min="100000"></label>
  <label for="risk">1R = 계좌의 %<input id="risk" type="number" inputmode="decimal" value="0.5" step="0.1" min="0.1" max="3"></label>
</div>
<div class="rules"><b>규칙</b> 50일 신고가 종가 돌파 → 다음 거래일 시가 매수 · 손절 1ATR(=1R) · +2R 도달 시 손절을 매수가로 · 이후 최고 종가 − 4ATR로 손절 상향 · 목표가 없음 · 동시 보유 3종목까지.<br><b>보유 중</b>은 규칙상 상태이며 실제 계좌와 다를 수 있습니다. 매 평일 15:47에 자동으로 갱신됩니다.</div>
<script>
const D = /*__DATA__*/null;
const tick = p => p < 2000 ? 1 : p < 5000 ? 5 : p < 20000 ? 10 : p < 50000 ? 50 : p < 200000 ? 100 : p < 500000 ? 500 : 1000;
const fl = p => Math.floor(p / tick(p)) * tick(p);
const n0 = x => Math.round(x).toLocaleString("ko-KR");
const dd = s => s ? `${+s.slice(4,6)}/${+s.slice(6,8)}` : "-";
const $ = id => document.getElementById(id);
function load(){try{const a=localStorage.getItem("krAcct"),r=localStorage.getItem("krRisk");if(a)$("acct").value=a;if(r)$("risk").value=r;}catch(e){}}
function save(){try{localStorage.setItem("krAcct",$("acct").value);localStorage.setItem("krRisk",$("risk").value);}catch(e){}}
function qty(buy, per){const a=+$("acct").value,rp=+$("risk").value;if(!(per>0))return 0;return Math.max(0,Math.min(Math.floor(a*rp/100/per),Math.floor(a/buy)));}
const link = r => `<a href="https://m.stock.naver.com/domestic/stock/${r.code}/total" target="_blank" rel="noopener">차트</a>`;
const head = (r, tag, cls) => `<div class="top"><div><span class="name">${r.name}</span><span class="code">${r.code}</span></div><span class="tag ${cls}">${tag}</span></div>`;
function render(){
  if(!D){$("meta").textContent="아직 데이터가 없습니다. 첫 자동 갱신(평일 15:47) 후 채워집니다.";return;}
  $("meta").textContent = `${D.at} 기준 · ${D.holiday ? "오늘 휴장, 직전 거래일("+dd(D.last)+") 기준" : dd(D.last)+" 종가 반영"} · ${D.n}종목`;
  const B=D.rows.filter(r=>r.kind==="buy"),S=D.rows.filter(r=>r.kind==="sell"),H=D.rows.filter(r=>r.kind==="hold"),N=D.rows.filter(r=>r.kind==="wait"&&r.dist<=3).sort((a,b)=>a.dist-b.dist);
  $("nBuy").textContent=B.length;$("nSell").textContent=S.length;$("nHold").textContent=H.length;
  $("buy").innerHTML = B.map(r=>{const stop=fl(r.close-r.risk),per=r.close-stop,q=qty(r.close,per);
    return `<div class="item buy">${head(r,"▲ 매수","buy")}<div class="kv"><div><span>기준가(종가)</span><b>${n0(r.close)}</b></div><div><span>손절가</span><b class="down">${n0(stop)}</b></div><div><span>1R</span><b>${(per/r.close*100).toFixed(1)}%</b></div><div><span>매수 수량</span><b>${n0(q)}주</b></div><div><span>투자금액</span><b>${n0(q*r.close)}원</b></div><div><span>손절 시</span><b class="down">-${n0(q*per)}원</b></div></div><div class="note">다음 거래일 시가에 매수하고, 손절가는 실제 매수가 − ${n0(r.risk)}원으로 다시 맞추세요. ${link(r)}</div></div>`}).join("") || `<div class="empty">오늘은 매수 신호가 없습니다.</div>`;
  $("sell").innerHTML = S.map(r=>`<div class="item sell">${head(r,"▼ 매도","sell")}<div class="kv"><div><span>매수가</span><b>${n0(r.ep)}</b></div><div><span>손절가(체결)</span><b>${n0(fl(r.px))}</b></div><div><span>결과</span><b class="${r.r>=0?"up":"down"}">${r.r>=0?"+":""}${r.r.toFixed(2)}R</b></div><div><span>보유 시작</span><b>${dd(r.entry)}</b></div></div><div class="note">오늘 저가가 손절가에 닿았습니다. 아직 보유 중이라면 매도하세요. ${link(r)}</div></div>`).join("") || `<div class="empty">오늘은 매도 신호가 없습니다.</div>`;
  $("hold").innerHTML = H.sort((a,b)=>b.rnow-a.rnow).map(r=>{const stop=fl(r.stop),q=qty(r.ep,r.risk);
    return `<div class="item hold">${head(r,r.raised?"손절가 상향":(r.be?"본전 확보":"보유"),"")}<div class="kv"><div><span>매수가</span><b>${n0(r.ep)}</b></div><div><span>현재가</span><b>${n0(r.close)}</b></div><div><span>손절가</span><b class="down">${n0(stop)}</b></div><div><span>현재 R</span><b class="${r.rnow>=0?"up":"down"}">${r.rnow>=0?"+":""}${r.rnow.toFixed(2)}R</b></div><div><span>규칙 수량</span><b>${n0(q)}주</b></div><div><span>보유 시작</span><b>${dd(r.entry)}</b></div></div>${r.raised?`<div class="note">손절가를 ${n0(fl(r.prev_stop))} → <b>${n0(stop)}</b>원으로 올리세요.</div>`:""}</div>`}).join("") || `<div class="empty">규칙상 보유 중인 종목이 없습니다.</div>`;
  $("near").innerHTML = N.map(r=>`<div class="item">${head(r,"신고가까지 "+r.dist.toFixed(1)+"%","")}<div class="note">종가 ${n0(r.close)}원 · ${r.mkt==="KOSPI"?"코스피":"코스닥"} ${link(r)}</div></div>`).join("") || `<div class="empty">3% 이내 종목이 없습니다.</div>`;
}
load(); render();
["acct","risk"].forEach(id=>$(id).addEventListener("input",()=>{save();render();}));
</script>
"""


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out_dir, exist_ok=True)
    uni = universe()
    with ThreadPoolExecutor(5) as ex:
        rows = [r for r in ex.map(one, uni) if r]
    now = datetime.now(KST)
    last = max(r["date"] for r in rows)
    holiday = last != now.strftime("%Y%m%d") or now.weekday() >= 5
    data = {"at": now.strftime("%Y-%m-%d %H:%M"), "last": last, "holiday": holiday, "n": len(rows),
            "rows": [r for r in rows if r["kind"] != "wait" or r["dist"] <= 3]}
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(PAGE.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False)))
    buy = [r["name"] for r in rows if r["kind"] == "buy"]
    sell = [r["name"] for r in rows if r["kind"] == "sell"]
    raised = [r["name"] for r in rows if r["kind"] == "hold" and r.get("raised")]
    print("SUMMARY " + json.dumps({"holiday": holiday, "last": last, "n": len(rows), "buy": buy, "sell": sell,
                                   "raised": raised}, ensure_ascii=False))


if __name__ == "__main__":
    main()
