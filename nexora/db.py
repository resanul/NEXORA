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
            CREATE TABLE IF NOT EXISTS links (
                source TEXT NOT NULL,
                destination TEXT NOT NULL,
                kind TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(source, destination, kind)
            );
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                target TEXT NOT NULL,
                status TEXT NOT NULL,
                hosts INTEGER NOT NULL DEFAULT 0,
                subnets INTEGER NOT NULL DEFAULT 0,
                links INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        self.conn.commit()

    def event(self, ts: str, event_type: str, data: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO events(ts,type,data) VALUES(?,?,?)",
            (ts, event_type, json.dumps(data)),
        )
        self.conn.commit()

    def start_scan(self, started_at: str, target: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO scans(started_at,target,status) VALUES(?,?,?)",
            (started_at, target, "running"),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_scan(self, scan_id: int, finished_at: str, cartographer, status: str = "completed") -> None:
        self.conn.execute(
            "UPDATE scans SET finished_at=?, status=?, hosts=?, subnets=?, links=? WHERE id=?",
            (finished_at, status, len(cartographer.hosts), len(cartographer.subnets), len(cartographer.links), scan_id),
        )
        self.conn.commit()

    def snapshot(self, cartographer) -> None:
        for ip, host in cartographer.hosts.items():
            data = {
                "ip": host.ip,
                "subnet": host.subnet,
                "reachable": host.reachable,
                "latency_ms": host.latency_ms,
                "hostname": host.hostname,
                "ports": host.ports,
                "services": host.services,
                "os_candidates": host.os_candidates,
                "confidence": host.confidence,
                "last_seen": host.last_seen,
            }
            self.conn.execute(
                "INSERT OR REPLACE INTO hosts VALUES(?,?,?,datetime('now'))",
                (ip, host.subnet, json.dumps(data)),
            )
        for cidr, subnet in cartographer.subnets.items():
            data = {
                "cidr": subnet.cidr,
                "parent": subnet.parent,
                "gateway": subnet.gateway,
                "status": subnet.status,
                "confidence": subnet.confidence,
                "hosts": sorted(subnet.hosts),
                "evidence": subnet.evidence,
            }
            self.conn.execute(
                "INSERT OR REPLACE INTO subnets VALUES(?,?,datetime('now'))",
                (cidr, json.dumps(data)),
            )
        for link in cartographer.links:
            self.conn.execute(
                "INSERT OR REPLACE INTO links VALUES(?,?,?,?,?,datetime('now'))",
                (link.source, link.destination, link.kind, link.confidence, link.evidence),
            )
        self.conn.commit()
