from __future__ import annotations

import argparse
import asyncio

import uvicorn

from .cli import run_cli
from .web import app, run_scan


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="NEXORA — Intelligent Network Cartography")
    p.add_argument("--target", required=True, help="Authorized CIDR to map, e.g. 192.168.1.0/24")
    p.add_argument("--rate", type=float, default=2.0, help="Maximum average probes/sec (default: 2)")
    p.add_argument("--web", action="store_true", help="Run the local web dashboard")
    p.add_argument("--cli", action="store_true", help="Show the terminal dashboard")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--expand", action="store_true", help="Follow private RFC1918 traceroute evidence into additional /24s")
    p.add_argument("--max-subnets", type=int, default=16, help="Maximum subnets per run (default: 16)")
    p.add_argument("--max-hosts-per-subnet", type=int, default=256, help="Maximum hosts examined per subnet (default: 256)")
    return p


async def main() -> None:
    args = parser().parse_args()
    if not args.web and not args.cli:
        args.web = True

    scan_kwargs = {
        "target": args.target,
        "probes_per_second": args.rate,
        "expand": args.expand,
        "max_subnets": args.max_subnets,
        "max_hosts_per_subnet": args.max_hosts_per_subnet,
    }

    if args.web:
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning"))
        web_task = asyncio.create_task(server.serve())
        try:
            await asyncio.sleep(0.2)
            scan_task = asyncio.create_task(run_scan(**scan_kwargs))
            if args.cli:
                await run_cli(args.target, args.rate)
            else:
                await scan_task
        finally:
            server.should_exit = True
            if not scan_task.done():
                await scan_task
            await web_task
    else:
        await run_cli(args.target, args.rate)


if __name__ == "__main__":
    asyncio.run(main())
