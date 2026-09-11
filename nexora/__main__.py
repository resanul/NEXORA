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
    return p


async def main() -> None:
    args = parser().parse_args()
    if not args.web and not args.cli:
        args.web = True

    if args.web and args.cli:
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning"))
        web_task = asyncio.create_task(server.serve())
        try:
            await asyncio.sleep(0.2)
            # The same scan events feed both the CLI and browser in a single process.
            await run_scan(args.target, args.rate)
        finally:
            server.should_exit = True
            await web_task
    elif args.web:
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning"))
        web_task = asyncio.create_task(server.serve())
        try:
            await asyncio.sleep(0.2)
            await run_scan(args.target, args.rate)
        finally:
            server.should_exit = True
            await web_task
    else:
        await run_cli(args.target, args.rate)


if __name__ == "__main__":
    asyncio.run(main())
