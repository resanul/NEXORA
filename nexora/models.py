from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Host:
    ip: str
    subnet: str
    reachable: bool = False
    latency_ms: float | None = None
    hostname: str | None = None
    ports: dict[int, str] = field(default_factory=dict)
    services: dict[int, str] = field(default_factory=dict)
    os_candidates: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    last_seen: str = field(default_factory=utc_now)


@dataclass
class Subnet:
    cidr: str
    parent: str | None = None
    gateway: str | None = None
    status: str = "queued"
    confidence: float = 0.0
    hosts: set[str] = field(default_factory=set)
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class Link:
    source: str
    destination: str
    kind: str
    confidence: float = 0.0
    evidence: str = ""


@dataclass
class Event:
    type: str
    data: dict[str, Any]
    timestamp: str = field(default_factory=utc_now)
