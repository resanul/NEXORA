from __future__ import annotations

import asyncio
import ipaddress
import platform
import re
import time
from collections.abc import Awaitable, Callable

from .models import Event, Host, Link, Subnet, utc_now

DEFAULT_PORTS = [22, 53, 80, 443, 445, 3389, 8080]
EventSink = Callable[[Event], Awaitable[None]]


class RateLimiter:
    """Simple global token-spacing limiter; deliberately conservative."""
    def __init__(self, probes_per_second: float = 2.0):
        self.interval = 1.0 / max(0.1, probes_per_second)
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = self.interval - (now - self._last)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = time.monotonic()


async def emit(sink: EventSink, event_type: str, **data) -> None:
    await sink(Event(event_type, data))


async def tcp_check(ip: str, port: int, limiter: RateLimiter, timeout: float = 1.5) -> tuple[bool, float | None]:
    await limiter.wait()
    started = time.perf_counter()
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout)
        writer.close()
        await writer.wait_closed()
        return True, (time.perf_counter() - started) * 1000
    except (OSError, asyncio.TimeoutError):
        return False, None


def ping_command(ip: str) -> list[str]:
    if platform.system().lower() == "windows":
        return ["ping", "-n", "1", "-w", "1200", ip]
    return ["ping", "-c", "1", "-W", "1", ip]


async def icmp_check(ip: str) -> tuple[bool, float | None]:
    started = time.perf_counter()
    try:
        proc = await asyncio.create_subprocess_exec(
            *ping_command(ip), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        await asyncio.wait_for(proc.communicate(), timeout=2.5)
        if proc.returncode == 0:
            return True, (time.perf_counter() - started) * 1000
    except (OSError, asyncio.TimeoutError):
        pass
    return False, None


def traceroute_command(target: str, max_hops: int = 12) -> list[str]:
    if platform.system().lower() == "windows":
        return ["tracert", "-d", "-h", str(max_hops), "-w", "1000", target]
    return ["traceroute", "-n", "-m", str(max_hops), "-w", "1", target]


async def traceroute(target: str, max_hops: int = 12) -> list[str]:
    """Collect path evidence using the host OS traceroute utility."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *traceroute_command(target), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=max_hops * 2.5)
    except (OSError, asyncio.TimeoutError):
        return []

    hops: list[str] = []
    for line in stdout.decode(errors="replace").splitlines():
        for candidate in re.findall(r"(?:\d{1,3}\.){3}\d{1,3}", line):
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if candidate not in hops:
                hops.append(candidate)
                break
    return hops


class Cartographer:
    def __init__(self, probes_per_second: float = 2.0, ports: list[int] | None = None):
        self.limiter = RateLimiter(probes_per_second)
        self.ports = ports or DEFAULT_PORTS
        self.subnets: dict[str, Subnet] = {}
        self.hosts: dict[str, Host] = {}
        self.links: list[Link] = []

    async def scan_subnet(self, cidr: str, sink: EventSink, parent: str | None = None) -> None:
        network = ipaddress.ip_network(cidr, strict=False)
        subnet = self.subnets.setdefault(cidr, Subnet(cidr=cidr, parent=parent, status="discovering"))
        await emit(sink, "SUBNET_STARTED", cidr=cidr, parent=parent)

        for address in network.hosts():
            ip = str(address)
            alive, latency = await icmp_check(ip)
            if not alive:
                for port in (443, 80, 22):
                    ok, port_latency = await tcp_check(ip, port, self.limiter)
                    if ok:
                        alive, latency = True, port_latency
                        break
            if not alive:
                continue

            host = self.hosts.setdefault(ip, Host(ip=ip, subnet=cidr))
            host.reachable = True
            host.latency_ms = latency
            host.last_seen = utc_now()
            subnet.hosts.add(ip)
            await emit(sink, "HOST_DISCOVERED", ip=ip, subnet=cidr, latency_ms=latency)
            await self.enumerate_host(host, sink)

        subnet.status = "mapped"
        await emit(sink, "SUBNET_COMPLETED", cidr=cidr, hosts=len(subnet.hosts))

    async def enumerate_host(self, host: Host, sink: EventSink) -> None:
        for port in self.ports:
            ok, latency = await tcp_check(host.ip, port, self.limiter)
            if ok:
                host.ports[port] = "open"
                service = service_name(port)
                host.services[port] = service
                await emit(sink, "PORT_FOUND", ip=host.ip, port=port, service=service, latency_ms=latency)

        candidates = fingerprint(host)
        host.os_candidates = candidates
        host.confidence = candidates[0]["confidence"] if candidates else 0.0
        if candidates:
            await emit(sink, "OS_ESTIMATE", ip=host.ip, candidates=candidates)

        path = await traceroute(host.ip)
        previous = None
        for hop in path:
            if previous:
                self.links.append(Link(previous, hop, "traceroute", 0.75, "traceroute observation"))
                await emit(sink, "LINK_FOUND", source=previous, destination=hop, kind="traceroute", confidence=0.75)
            previous = hop
        if path:
            await emit(sink, "PATH_FOUND", target=host.ip, hops=path)


def service_name(port: int) -> str:
    return {22: "ssh", 53: "dns", 80: "http", 443: "https", 445: "smb", 3389: "rdp", 8080: "http-alt"}.get(port, "unknown")


def fingerprint(host: Host) -> list[dict]:
    p = set(host.ports)
    scores = {"Linux/Unix": 0.0, "Windows": 0.0, "Network appliance": 0.0}
    if 22 in p:
        scores["Linux/Unix"] += 0.55
    if 445 in p or 3389 in p:
        scores["Windows"] += 0.65
    if 53 in p and len(p) <= 3:
        scores["Network appliance"] += 0.25
    if 80 in p or 443 in p:
        scores["Linux/Unix"] += 0.08
        scores["Windows"] += 0.08
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top = ranked[0][1]
    if top <= 0:
        return []
    return [{"os": name, "confidence": round(min(0.99, score / max(0.75, top)), 2)} for name, score in ranked if score > 0]
