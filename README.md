# NEXORA — Intelligent Network Cartography

NEXORA is a conservative, evidence-driven network cartography platform for authorized networks. It progressively discovers reachable hosts and subnets, collects topology evidence, fingerprints services/OS candidates, and renders the evolving map in CLI and web interfaces.

## Current MVP

- Async, bounded TCP connectivity/port checks
- Conservative rate limiting
- ICMP reachability via the platform ping utility
- Traceroute evidence collection
- Bounded autonomous discovery frontier
- RFC1918-only subnet expansion when explicitly enabled
- Per-run subnet and host safety limits
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

The web UI is available at `http://127.0.0.1:8080` and stays live while the scan runs.

### Autonomous expansion

Expansion is opt-in because traceroute observations can reveal networks outside the intended assessment scope. When enabled, NEXORA only promotes private RFC1918 IPv4 hops to `/24` candidates and applies hard bounds:

```bash
python -m nexora --target 192.168.1.0/24 --web --expand --max-subnets 16 --max-hosts-per-subnet 256
```

`--max-subnets` limits the number of subnet scopes visited in one run. `--max-hosts-per-subnet` limits addresses examined in each subnet. For a conservative test, use a small subnet that you own/control.

CLI mode:

```bash
python -m nexora --target 192.168.1.0/24 --cli
```

## Windows

The application can run from source on Windows. EXE packaging is provided by the PyInstaller build configuration:

```powershell
python -m pip install -r requirements.txt
pyinstaller nexora.spec
```

## Safety

Use NEXORA only on networks you own or are explicitly authorized to assess. Autonomous expansion is deliberately disabled unless `--expand` is supplied. NEXORA does not attempt authentication, exploitation, credential attacks, or stealth/evasion.
