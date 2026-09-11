from __future__ import annotations

from collections import deque
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse

from .db import Database
from .engine import Cartographer
from .frontier import Frontier
from .models import Event

app = FastAPI(title="NEXORA", version="0.3.0")
cartographer = Cartographer()
db = Database()
event_history: deque[dict] = deque(maxlen=500)
clients: set[WebSocket] = set()
scan_state = {"status": "idle", "target": None, "scan_id": None}


async def sink(event: Event) -> None:
    payload = {"type": event.type, "timestamp": event.timestamp, "data": event.data}
    event_history.append(payload)
    db.event(event.timestamp, event.type, event.data)
    dead = []
    for ws in clients:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


@app.get("/api/state")
async def state():
    return {
        "scan": scan_state,
        "subnets": [s.__dict__ | {"hosts": sorted(s.hosts)} for s in cartographer.subnets.values()],
        "hosts": [h.__dict__ for h in cartographer.hosts.values()],
        "links": [l.__dict__ for l in cartographer.links],
        "events": list(event_history),
    }


@app.get("/api/scans")
async def scans(limit: int = 25):
    return {"scans": db.recent_scans(limit)}


@app.get("/api/events")
async def events(limit: int = 100):
    return {"events": db.recent_events(limit)}


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        await ws.send_json({"type": "SNAPSHOT", "data": await state()})
        while True:
            await ws.receive_text()
    except Exception:
        clients.discard(ws)


@app.get("/")
async def index():
    return HTMLResponse(INDEX)


async def run_scan(target: str, probes_per_second: float = 2.0, expand: bool = False, max_subnets: int = 16, max_hosts_per_subnet: int = 256):
    global cartographer, scan_state
    cartographer = Cartographer(probes_per_second=probes_per_second)
    frontier = Frontier(target, max_subnets=max_subnets, max_hosts_per_subnet=max_hosts_per_subnet, expand=expand)
    started = datetime.now(timezone.utc).isoformat()
    scan_id = db.start_scan(started, target)
    scan_state = {"status": "running", "target": target, "scan_id": scan_id}
    await sink(Event("SCAN_STARTED", {"scan_id": scan_id, "target": target}))
    try:
        await frontier.run(cartographer, sink)
        db.snapshot(cartographer, scan_id=scan_id)
        db.finish_scan(scan_id, datetime.now(timezone.utc).isoformat(), cartographer)
        scan_state = {"status": "completed", "target": target, "scan_id": scan_id}
        await sink(Event("SCAN_COMPLETED", {"scan_id": scan_id, "hosts": len(cartographer.hosts), "subnets": len(cartographer.subnets), "links": len(cartographer.links)}))
    except Exception as exc:
        db.finish_scan(scan_id, datetime.now(timezone.utc).isoformat(), cartographer, status="failed")
        scan_state = {"status": "failed", "target": target, "scan_id": scan_id}
        await sink(Event("SCAN_FAILED", {"scan_id": scan_id, "error": str(exc)}))
        raise


INDEX = r'''<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NEXORA</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#07111f;color:#dbeafe;font:14px system-ui,-apple-system,sans-serif}header{height:58px;padding:0 18px;border-bottom:1px solid #20304a;display:flex;align-items:center;gap:14px}header b{font-size:17px;letter-spacing:.08em}.pill{padding:5px 9px;border:1px solid #334155;border-radius:999px;color:#93c5fd;font-size:12px}main{display:grid;grid-template-columns:minmax(0,1fr) 340px;height:calc(100vh - 58px)}#map{position:relative;overflow:hidden;background:radial-gradient(circle at 50% 45%,#10233b 0,#07111f 60%)}#canvas{width:100%;height:100%;cursor:grab}.drag{cursor:grabbing}.toolbar{position:absolute;top:14px;left:14px;display:flex;gap:6px}.toolbar button,.filter{background:#0d1a2c;color:#dbeafe;border:1px solid #30445f;border-radius:8px;padding:7px 10px}.toolbar button:hover{border-color:#60a5fa}.legend{position:absolute;bottom:14px;left:14px;background:#0b1728dd;border:1px solid #26364d;border-radius:10px;padding:9px 12px;font-size:12px}.legend span{margin-right:12px}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}.subnet{background:#60a5fa}.host{background:#34d399}.link{background:#94a3b8}aside{border-left:1px solid #20304a;overflow:auto;padding:10px}.card{background:#0b1728;border:1px solid #26364d;border-radius:11px;padding:12px;margin-bottom:10px}.card h3{margin:0 0 9px;font-size:13px;color:#bfdbfe}.stats{display:grid;grid-template-columns:1fr 1fr;gap:7px}.metric{background:#0f1d31;border-radius:8px;padding:8px}.metric strong{display:block;font-size:18px}.metric small{color:#94a3b8}.event{font-size:12px;padding:7px 0;border-top:1px solid #1e293b;word-break:break-word}.event:first-child{border-top:0}.detail{line-height:1.6;color:#cbd5e1}.muted{color:#94a3b8}.empty{color:#64748b;padding:20px;text-align:center}.node-label{font-size:11px;fill:#dbeafe;pointer-events:none}.edge{stroke:#64748b;stroke-width:1.5;opacity:.65}.edge:hover{stroke:#93c5fd;opacity:1}
</style></head>
<body><header><b>NEXORA</b><span>Intelligent Network Cartography</span><span id="status" class="pill">connecting…</span><span class="pill">Interactive topology</span></header>
<main><section id="map"><svg id="canvas" viewBox="0 0 1200 800" aria-label="Interactive network topology"></svg><div class="toolbar"><button id="zoomIn">+</button><button id="zoomOut">−</button><button id="reset">Reset</button><button id="fit">Fit</button><select id="filter" class="filter"><option value="all">All nodes</option><option value="subnets">Subnets</option><option value="hosts">Hosts</option></select></div><div class="legend"><span><i class="dot subnet"></i>Subnet</span><span><i class="dot host"></i>Host</span><span><i class="dot link"></i>Path</span><span>Scroll to zoom · drag to pan · click node for details</span></div></section><aside><div class="card"><h3>SCAN TELEMETRY</h3><div class="stats"><div class="metric"><strong id="mSubnets">0</strong><small>Subnets</small></div><div class="metric"><strong id="mHosts">0</strong><small>Hosts</small></div><div class="metric"><strong id="mLinks">0</strong><small>Links</small></div><div class="metric"><strong id="mPorts">0</strong><small>Open ports</small></div></div></div><div class="card"><h3>SELECTED NODE</h3><div id="detail" class="detail empty">Click a subnet or host.</div></div><div class="card"><h3>LIVE EVENTS</h3><div id="events"><div class="empty">Waiting for discovery…</div></div></div></aside></main>
<script>
const svg=document.querySelector('#canvas'),events=document.querySelector('#events'),detail=document.querySelector('#detail');let state={subnets:[],hosts:[],links:[]},filter='all',scale=1,tx=0,ty=0,drag=false,last={x:0,y:0};
const NS='http://www.w3.org/2000/svg';const el=(tag,attrs={})=>{const n=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));return n};
function positions(){const items=[];state.subnets.forEach((s,i)=>items.push({id:'s:'+s.cidr,type:'subnet',label:s.cidr,x:180+(i%4)*250,y:150+Math.floor(i/4)*220,obj:s}));state.hosts.forEach((h,i)=>items.push({id:'h:'+h.ip,type:'host',label:h.hostname||h.ip,x:170+(i%6)*170,y:520+Math.floor(i/6)*150,obj:h}));return items}
function visible(n){return filter==='all'||filter===n.type+'s'}
function render(){svg.innerHTML='';const g=el('g',{transform:`translate(${tx} ${ty}) scale(${scale})`}),nodes=positions(),byId=Object.fromEntries(nodes.map(n=>[n.id,n]));state.links.forEach(l=>{const a=byId['h:'+l.source]||byId['s:'+l.source],b=byId['h:'+l.destination]||byId['s:'+l.destination];if(!a||!b||(!visible(a)&&!visible(b)))return;g.appendChild(el('line',{x1:a.x,y1:a.y,x2:b.x,y2:b.y,class:'edge'}))});nodes.filter(visible).forEach(n=>{const group=el('g',{transform:`translate(${n.x} ${n.y})`,style:'cursor:pointer'});group.appendChild(el('circle',{r:n.type==='subnet'?30:18,fill:n.type==='subnet'?'#60a5fa':'#34d399',opacity:.18,stroke:n.type==='subnet'?'#60a5fa':'#34d399','stroke-width':2}));group.appendChild(el('circle',{r:n.type==='subnet'?5:4,fill:n.type==='subnet'?'#60a5fa':'#34d399'}));const text=el('text',{y:n.type==='subnet'?48:35,'text-anchor':'middle',class:'node-label'});text.textContent=n.label;group.appendChild(text);group.addEventListener('click',e=>{e.stopPropagation();select(n)});g.appendChild(group)});svg.appendChild(g)}
function select(n){const o=n.obj;if(n.type==='subnet')detail.innerHTML=`<b>${o.cidr}</b><br>Status: ${o.status}<br>Confidence: ${(o.confidence||0).toFixed(2)}<br>Hosts: ${o.hosts.length}<br>Parent: ${o.parent||'—'}`;else detail.innerHTML=`<b>${o.hostname||o.ip}</b><br>IP: ${o.ip}<br>Reachable: ${o.reachable?'yes':'no'}<br>Latency: ${o.latency_ms==null?'—':o.latency_ms.toFixed(1)+' ms'}<br>Ports: ${Object.keys(o.ports||{}).join(', ')||'none'}<br>Services: ${Object.values(o.services||{}).join(', ')||'none'}<br>Confidence: ${(o.confidence||0).toFixed(2)}`;detail.classList.remove('empty')}
function renderStats(){document.querySelector('#mSubnets').textContent=state.subnets.length;document.querySelector('#mHosts').textContent=state.hosts.length;document.querySelector('#mLinks').textContent=state.links.length;document.querySelector('#mPorts').textContent=state.hosts.reduce((n,h)=>n+Object.keys(h.ports||{}).length,0)}
function addEvent(e){if(events.querySelector('.empty'))events.innerHTML='';const d=e.data||{};events.innerHTML=`<div class="event"><b>${e.type}</b><br><span class="muted">${new Date(e.timestamp).toLocaleTimeString()}</span> ${JSON.stringify(d)}</div>`+events.innerHTML;events.innerHTML=events.innerHTML.slice(0,18000)}
function apply(){render();renderStats()}function zoom(f){scale=Math.max(.35,Math.min(3,scale*f));render()}function reset(){scale=1;tx=0;ty=0;render()}function fit(){scale=.8;tx=0;ty=0;render()}
document.querySelector('#zoomIn').onclick=()=>zoom(1.2);document.querySelector('#zoomOut').onclick=()=>zoom(.83);document.querySelector('#reset').onclick=reset;document.querySelector('#fit').onclick=fit;document.querySelector('#filter').onchange=e=>{filter=e.target.value;render()};svg.addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY<0?1.1:.9)},{passive:false});svg.addEventListener('pointerdown',e=>{drag=true;last={x:e.clientX,y:e.clientY};svg.classList.add('drag')});svg.addEventListener('pointermove',e=>{if(!drag)return;tx+=(e.clientX-last.x)/scale;ty+=(e.clientY-last.y)/scale;last={x:e.clientX,y:e.clientY};render()});svg.addEventListener('pointerup',()=>{drag=false;svg.classList.remove('drag')});svg.addEventListener('pointerleave',()=>{drag=false;svg.classList.remove('drag')});
const ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws`);ws.onopen=()=>document.querySelector('#status').textContent='● live';ws.onmessage=e=>{const x=JSON.parse(e.data);if(x.type==='SNAPSHOT'){state=x.data;(state.events||[]).slice(-40).forEach(addEvent);apply()}else{addEvent(x);fetch('/api/state').then(r=>r.json()).then(x=>{state=x;apply()})}};ws.onclose=()=>document.querySelector('#status').textContent='disconnected';apply();
</script></body></html>'''
