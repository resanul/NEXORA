from __future__ import annotations

from collections import deque
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse

from .db import Database
from .engine import Cartographer
from .frontier import Frontier
from .models import Event

app = FastAPI(title="NEXORA", version="0.2.0")
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


async def run_scan(
    target: str,
    probes_per_second: float = 2.0,
    expand: bool = False,
    max_subnets: int = 16,
    max_hosts_per_subnet: int = 256,
):
    global cartographer, scan_state
    cartographer = Cartographer(probes_per_second=probes_per_second)
    frontier = Frontier(
        target,
        max_subnets=max_subnets,
        max_hosts_per_subnet=max_hosts_per_subnet,
        expand=expand,
    )
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
<html><head><meta charset="utf-8"><title>NEXORA</title>
<style>body{margin:0;background:#07111f;color:#dbeafe;font:14px system-ui}header{padding:16px 22px;border-bottom:1px solid #1e293b}main{display:grid;grid-template-columns:1fr 330px;height:calc(100vh - 65px)}#map{position:relative;overflow:auto;padding:30px}.card{background:#0f1b2d;border:1px solid #26364d;border-radius:12px;padding:14px;margin:10px}.node{display:inline-block;margin:10px;padding:12px 16px;border:1px solid #3b82f6;border-radius:10px;background:#0b1728}.muted{color:#94a3b8}.event{font-size:12px;margin:7px 0;word-break:break-word}</style></head>
<body><header><b>NEXORA</b> — Intelligent Network Cartography <span id="status" class="muted">connecting…</span></header>
<main><section id="map"><div class="card"><b>Live topology</b><div id="nodes"></div></div></section><aside><div class="card"><b>Statistics</b><div id="stats"></div></div><div class="card"><b>Live events</b><div id="events"></div></div></aside></main>
<script>
const nodes=document.querySelector('#nodes'),events=document.querySelector('#events'),stats=document.querySelector('#stats');
let state={subnets:[],hosts:[],links:[]};
function render(){nodes.innerHTML=state.subnets.map(s=>`<div class="node"><b>${s.cidr}</b><br><span class="muted">${s.hosts.length} hosts · ${s.status}</span></div>`).join('')||'<span class="muted">Waiting for discovery…</span>';stats.innerHTML=`Subnets: ${state.subnets.length}<br>Hosts: ${state.hosts.length}<br>Links: ${state.links.length}<br>Open ports: ${state.hosts.reduce((n,h)=>n+Object.keys(h.ports||{}).length,0)}`}
function addEvent(e){const d=e.data||{};events.innerHTML=`<div class="event"><b>${e.type}</b> ${JSON.stringify(d)}</div>`+events.innerHTML;events.innerHTML=events.innerHTML.slice(0,12000)}
const ws=new WebSocket(`ws://${location.host}/ws`);ws.onopen=()=>document.querySelector('#status').textContent='● live';ws.onmessage=e=>{const x=JSON.parse(e.data);if(x.type==='SNAPSHOT'){state=x.data;render();(state.events||[]).slice(-30).forEach(addEvent)}else{addEvent(x);fetch('/api/state').then(r=>r.json()).then(x=>{state=x;render()})}};ws.onclose=()=>document.querySelector('#status').textContent='disconnected';render();
</script></body></html>'''
