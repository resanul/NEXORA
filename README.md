# NEXORA — Intelligent Network Cartography

NEXORA is a conservative, evidence-driven network cartography platform for authorized networks. It progressively discovers reachable hosts and subnets, collects topology evidence, fingerprints services/OS candidates, and renders the evolving map in CLI and web interfaces.

## Current MVP

- Async, bounded TCP connectivity/port checks
- Conservative rate limiting and exponential backoff
- ICMP reachability via the platform ping utility
- Traceroute evidence collection
- CIDR/subnet modeling and discovery queue
- Evidence-based service/OS candidate scoring
- SQLite persistence
- Live event bus
- Rich CLI dashboard
- FastAPI JSON/WebSocket API
- Minimal browser map/dashboard

## Run

```bash
python -m pip install -r requirements.txt
python -m nexora --target 192.168.1.0/24 --web
```

The web UI is available at `http://127.0.0.1:8080`.

For a conservative test, use a small subnet that you own/control. NEXORA intentionally bounds concurrency and probe rate.

## Windows

The application can run from source on Windows. EXE packaging is provided by the PyInstaller build configuration:

```powershell
python -m pip install -r requirements.txt
pyinstaller nexora.spec
```

## Safety

Use NEXORA only on networks you own or are explicitly authorized to assess. The default policy is conservative and bounded. NEXORA does not attempt authentication, exploitation, credential attacks, or stealth/evasion.
