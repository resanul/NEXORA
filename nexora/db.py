from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: str = "nexora.db"):
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                type TEXT NOT NULL,
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS hosts (
                ip TEXT PRIMARY KEY,
                subnet TEXT NOT NULL,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS subnets (
                cidr TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def event(self, ts: str, event_type: str, data: dict[str, Any]) -> None:
        self.conn.execute("INSERT INTO events(ts,type,data) VALUES(?,?,?)", (ts, event_type, json.dumps(data)))
        self.conn.commit()

    def snapshot(self, cartographer) -> None:
        for ip, host in cartographer.hosts.items():
            data = {"ip": host.ip, "subnet": host.subnet, "reachable": host.reachable,
                    "latency_ms": host.latency_ms, "ports": host.ports, "services": host.services,
                    "os_candidates": host.os_candidates, "confidence": host.confidence}
            self.conn.execute("INSERT OR REPLACE INTO hosts VALUES(?,?,?,datetime('now'))", (ip, host.subnet, json.dumps(data)))
        for cidr, subnet in cartographer.subnets.items():
            data = {"cidr": subnet.cidr, "parent": subnet.parent, "gateway": subnet.gateway,
                    "status": subnet.status, "confidence": subnet.confidence, "hosts": sorted(subnet.hosts),
                    "evidence": subnet.evidence}
            self.conn.execute("INSERT OR REPLACE INTO subnets VALUES(?,?,datetime('now'))", (cidr, json.dumps(data)))
        self.conn.commit()
