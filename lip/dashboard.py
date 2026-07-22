"""작업제어 대시보드 — 무의존 stdlib 웹서버 (LinkNode 통합 대시보드 이식).

LinkNode `src/app/dashboard` (KPI 그리드 · 상태 배지 · 라이브 이벤트 피드 · 제어)를
LIP 이미지 공장에 맞게 이식. 의존성 0 — http.server 로 HTML + JSON API 제공.

라우트:
  GET  /                → 대시보드 HTML (2초 폴링)
  GET  /api/summary     → KPI 집계
  GET  /api/jobs        → 작업 큐
  GET  /api/events      → 라이브 이벤트 피드
  GET  /api/nodes       → Compute Node 목록 (lasset)
  POST /api/control     → {action: pause|resume|stop|cancel, id?}
  GET  /img/<id>/<file> → 생성물 썸네일(webp)
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .jobs import JobStore
from .nodes import NodeRegistry

PAGE = """<!doctype html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>LIP · 이미지 공장 제어 대시보드</title>
<style>
:root{--bg:#0b0f17;--card:#141b2b;--line:#243049;--fg:#e6ecf5;--mut:#8291ad;--ok:#34d399;--warn:#fbbf24;--err:#f87171;--info:#60a5fa;--accent:#7c8cff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,'Segoe UI',sans-serif}
header{padding:16px 24px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:14px;flex-wrap:wrap}
h1{font-size:17px;margin:0;font-weight:700}.sub{color:var(--mut);font-size:12px}
.wrap{padding:20px 24px;max-width:1280px;margin:0 auto}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.kpi .l{color:var(--mut);font-size:12px}.kpi .v{font-size:26px;font-weight:700;margin-top:4px}
.grid{display:grid;grid-template-columns:1.6fr 1fr;gap:16px}@media(max-width:900px){.grid{grid-template-columns:1fr}}
.panel{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:16px}
.panel h2{font-size:13px;margin:0 0 12px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line)}
th{color:var(--mut);font-weight:600}td.mono{font-family:ui-monospace,monospace;font-size:12px;color:var(--mut)}
.badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:600}
.b-pending{background:#2a3346;color:var(--mut)}.b-generating,.b-optimizing{background:#1e3a5f;color:var(--info)}
.b-done{background:#123524;color:var(--ok)}.b-failed{background:#3a1620;color:var(--err)}.b-cancelled{background:#2a3346;color:var(--mut)}
.b-online{background:#123524;color:var(--ok)}.b-offline{background:#3a1620;color:var(--err)}.b-unknown{background:#2a3346;color:var(--mut)}
.feed{max-height:320px;overflow:auto}.ev{padding:6px 0;border-bottom:1px solid var(--line);font-size:12px;display:flex;gap:8px}
.ev .dot{width:8px;height:8px;border-radius:50%;margin-top:5px;flex:none}
.dot.info{background:var(--info)}.dot.success{background:var(--ok)}.dot.warning{background:var(--warn)}.dot.error{background:var(--err)}
.controls{display:flex;gap:8px;flex-wrap:wrap;margin-left:auto}
button{background:var(--accent);color:#fff;border:0;border-radius:9px;padding:8px 14px;font-size:13px;font-weight:600;cursor:pointer}
button.ghost{background:transparent;border:1px solid var(--line);color:var(--fg)}button:active{transform:translateY(1px)}
.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px}
.gallery img{width:100%;border-radius:8px;border:1px solid var(--line);aspect-ratio:16/9;object-fit:cover;background:#000}
.dist{display:flex;flex-direction:column;gap:6px}.bar{height:8px;border-radius:4px;background:var(--accent)}
.pill{padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid var(--line)}
.pill.run{background:#123524;color:var(--ok)}.pill.pause{background:#3a2a10;color:var(--warn)}
</style></head><body>
<header>
  <h1>🏭 LIP 이미지 공장</h1><span class=sub id=sub>연결 중…</span>
  <span class=pill id=state>—</span>
  <div class=controls>
    <button class=ghost onclick=ctl('pause')>일시정지</button>
    <button class=ghost onclick=ctl('resume')>재개</button>
    <button onclick=ctl('stop')>중지</button>
  </div>
</header>
<div class=wrap>
  <div class=kpis id=kpis></div>
  <div class=grid>
    <div>
      <div class=panel><h2>작업 큐</h2><table><thead><tr><th>상태</th><th>태그</th><th>ID</th><th>노드</th><th>용량</th></tr></thead><tbody id=jobs></tbody></table></div>
      <div class=panel><h2>최근 생성물</h2><div class=gallery id=gallery></div></div>
    </div>
    <div>
      <div class=panel><h2>Compute Nodes</h2><table><thead><tr><th>상태</th><th>이름</th><th>URL</th></tr></thead><tbody id=nodes></tbody></table></div>
      <div class=panel><h2>태그 분포</h2><div class=dist id=dist></div></div>
      <div class=panel><h2>라이브 이벤트</h2><div class="feed" id=feed></div></div>
    </div>
  </div>
</div>
<script>
async function j(u,o){const r=await fetch(u,o);return r.json()}
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
async function ctl(a,id){await j('/api/control',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({action:a,id:id})});tick()}
function kpi(l,v){return `<div class=kpi><div class=l>${l}</div><div class=v>${v}</div></div>`}
async function tick(){
 try{
  const s=await j('/api/summary'),t=s.totals;
  document.getElementById('sub').textContent=`가동 ${Math.round(t.elapsed_sec)}s · ${t.throughput_per_min}/분`;
  const st=document.getElementById('state');st.textContent=s.stopped?'중지됨':s.paused?'일시정지':'가동 중';
  st.className='pill '+(s.paused||s.stopped?'pause':'run');
  document.getElementById('kpis').innerHTML=[
   kpi('총 작업',t.total),kpi('완료',t.done),kpi('진행',t.running),kpi('대기',t.pending),
   kpi('실패',t.failed),kpi('분당 처리',t.throughput_per_min),
   kpi('총 용량',(t.bytes_total/1048576).toFixed(1)+'MB')].join('');
  const jobs=await j('/api/jobs');
  document.getElementById('jobs').innerHTML=jobs.map(x=>`<tr><td><span class="badge b-${x.status}">${x.status_label}</span></td><td>${esc(x.tag)}</td><td class=mono>${esc(x.prompt_id)}</td><td class=mono>${esc(x.node||'-')}</td><td class=mono>${x.bytes_total?(x.bytes_total/1024).toFixed(0)+'KB':'-'}</td></tr>`).join('')||'<tr><td colspan=5 style=color:#8291ad>작업 없음</td></tr>';
  const gal=jobs.filter(x=>x.status==='done').slice(0,12);
  document.getElementById('gallery').innerHTML=gal.map(x=>`<img loading=lazy src="/img/${encodeURIComponent(x.prompt_id)}/image.webp" title="${esc(x.positive)}">`).join('')||'<span class=sub>아직 없음</span>';
  const nodes=await j('/api/nodes');
  document.getElementById('nodes').innerHTML=nodes.map(n=>`<tr><td><span class="badge b-${n.status}">${n.status}</span></td><td>${esc(n.name)}${n.active?' ●':''}</td><td class=mono>${esc(n.base_url)}</td></tr>`).join('')||'<tr><td colspan=3 style=color:#8291ad>노드 없음</td></tr>';
  const mx=Math.max(1,...s.distribution.map(d=>d.value));
  document.getElementById('dist').innerHTML=s.distribution.map(d=>`<div><span class=sub>${esc(d.tag)} · ${d.value}</span><div class=bar style=width:${d.value/mx*100}%></div></div>`).join('')||'<span class=sub>—</span>';
  const evs=await j('/api/events');
  document.getElementById('feed').innerHTML=evs.map(e=>`<div class=ev><span class="dot ${e.level}"></span><span>${esc(e.message)}</span></div>`).join('');
 }catch(e){document.getElementById('sub').textContent='연결 끊김'}
}
tick();setInterval(tick,2000);
</script></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    store: JobStore = None      # 인스턴스 주입 (set on class)
    registry: NodeRegistry = None
    out_dir: Path = Path("out")

    def log_message(self, *a):  # 조용히
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif p == "/api/summary":
            self._json(self.store.summary())
        elif p == "/api/jobs":
            self._json([j.as_dict() for j in self.store.jobs(60)])
        elif p == "/api/events":
            self._json([{"ts": e.ts, "level": e.level, "message": e.message}
                        for e in self.store.events(60)])
        elif p == "/api/nodes":
            self._json([n.as_dict() for n in self.registry.list()] if self.registry else [])
        elif p.startswith("/img/"):
            self._serve_image(p[len("/img/"):])
        else:
            self._json({"error": "not found"}, 404)

    def _serve_image(self, rel: str):
        # rel = "<prompt_id>/image.webp" — out_dir 밖으로 못 나가게 검증
        target = (self.out_dir / rel).resolve()
        if self.out_dir.resolve() not in target.parents or not target.is_file():
            self._json({"error": "not found"}, 404)
            return
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("content-type", "image/webp")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path.split("?")[0] != "/api/control":
            self._json({"error": "not found"}, 404)
            return
        length = int(self.headers.get("content-length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        action = payload.get("action")
        if action == "pause":
            self.store.pause()
        elif action == "resume":
            self.store.resume()
        elif action == "stop":
            self.store.stop()
        elif action == "cancel" and payload.get("id"):
            self.store.cancel(payload["id"])
        else:
            self._json({"error": "unknown action"}, 400)
            return
        self._json({"ok": True})


def serve_dashboard(store: JobStore, registry: NodeRegistry, out_dir: Path,
                    port: int = 8787, block: bool = True):
    """대시보드 서버 시작. block=False 면 백그라운드 스레드로 실행하고 서버 반환."""
    handler = type("_H", (_Handler,), {"store": store, "registry": registry,
                                       "out_dir": Path(out_dir)})
    httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)
    if block:
        httpd.serve_forever()
        return httpd
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd
