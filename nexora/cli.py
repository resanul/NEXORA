from __future__ import annotations

import asyncio

from rich.console import Console
from rich.live import Live
from rich.table import Table

from .engine import Cartographer
from .models import Event

console = Console()


def dashboard(c: Cartographer, last: Event | None) -> Table:
    table = Table(title="NEXORA — Intelligent Network Cartography")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Subnets", str(len(c.subnets)))
    table.add_row("Hosts", str(len(c.hosts)))
    table.add_row("Links", str(len(c.links)))
    table.add_row("Open ports", str(sum(len(h.ports) for h in c.hosts.values())))
    if last:
        table.add_row("Last event", f"{last.type}: {last.data}")
    return table


async def run_cli(target: str, rate: float = 2.0):
    c = Cartographer(probes_per_second=rate)
    last: Event | None = None

    async def sink(event: Event):
        nonlocal last
        last = event

    with Live(dashboard(c, last), refresh_per_second=4, console=console) as live:
        async def refresh():
            while True:
                live.update(dashboard(c, last))
                await asyncio.sleep(0.25)

        task = asyncio.create_task(refresh())
        try:
            await c.scan_subnet(target, sink)
        finally:
            task.cancel()
    console.print(dashboard(c, last))
