from __future__ import annotations

import ipaddress
from collections import deque
from collections.abc import Awaitable, Callable

from .engine import Cartographer
from .models import Event

EventSink = Callable[[Event], Awaitable[None]]


class Frontier:
    """Bounded autonomous frontier for private-network discovery.

    Expansion is deliberately opt-in. Only RFC1918 IPv4 traceroute hops are
    promoted to subnet candidates, and every candidate is still scanned using
    the normal low-impact Cartographer probes.
    """

    def __init__(
        self,
        seed: str,
        max_subnets: int = 16,
        max_hosts_per_subnet: int = 256,
        prefix: int = 24,
        expand: bool = False,
    ) -> None:
        self.seed = str(ipaddress.ip_network(seed, strict=False))
        self.max_subnets = max(1, max_subnets)
        self.max_hosts_per_subnet = max(1, max_hosts_per_subnet)
        self.prefix = min(32, max(8, prefix))
        self.expand = expand
        self.queue: deque[tuple[str, str | None]] = deque([(self.seed, None)])
        self.seen: set[str] = {self.seed}

    def _candidate(self, address: str) -> str | None:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return None
        if ip.version != 4 or not ip.is_private:
            return None
        network = ipaddress.ip_network(f"{ip}/{self.prefix}", strict=False)
        # Avoid turning documentation/test-only space or loopback into scope.
        if network.is_loopback or network.is_link_local:
            return None
        return str(network)

    def _promote_paths(self, cartographer: Cartographer, parent: str) -> None:
        if not self.expand:
            return
        for link in cartographer.links:
            candidate = self._candidate(link.destination)
            if candidate and candidate not in self.seen and len(self.seen) < self.max_subnets:
                self.seen.add(candidate)
                self.queue.append((candidate, parent))

    async def run(self, cartographer: Cartographer, sink: EventSink) -> None:
        while self.queue and len(cartographer.subnets) < self.max_subnets:
            cidr, parent = self.queue.popleft()
            await sink(Event("SUBNET_QUEUED", {"cidr": cidr, "parent": parent}))
            await cartographer.scan_subnet(
                cidr,
                sink,
                parent=parent,
                max_hosts=self.max_hosts_per_subnet,
            )
            self._promote_paths(cartographer, cidr)
            await sink(Event("SUBNET_FRONTIER_UPDATED", {
                "completed": len(cartographer.subnets),
                "queued": len(self.queue),
                "limit": self.max_subnets,
            }))
