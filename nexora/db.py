from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class Database:
    """SQLite persistence for current topology, scan sessions, events, and history."""

    SCHEMA_VERSION = "2"

    def __init__(self, path: str = "nexora.db"):
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                type TEXT NOT NULL,
                data TEXT NOT NULL
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
            CREATE TABLE IF NOT EXISTS hosts (
                ip TEXT PRIMARY KEY,
                subnet TEXT NOT NULL,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS host_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id INTEGER,
                ip TEXT NOT NULL,
                subnet TEXT NOT NULL,
                data TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                FOREIGN KEY(scan_id) REFERENCES scans(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS subnets (
                cidr TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS subnet_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id INTEGER,
                cidr TEXT NOT NULL,
                data TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                FOREIGN KEY(scan_id) REFERENCES scans(id) ON DELETE SET NULL
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
            CREATE TABLE IF NOT EXISTS link_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id INTEGER,
                source TEXT NOT NULL,
                destination TEXT NOT NULL,
                kind TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                FOREIGN KEY(scan_id) REFERENCES scans(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
            CREATE INDEX IF NOT EXISTS idx_host_history_scan ON host_history(scan_id);
            CREATE INDEX IF NOT EXISTS idx_subnet_history_scan ON subnet_history(scan_id);
            CREATE INDEX IF NOT EXISTS idx_link_history_scan ON link_history(scan_id);
            """
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO schema_meta(key,value) VALUES('version',?)",
            (self.SCHEMA_VERSION,),
        )
        self.conn.commit()

    @staticmethod
    def _json(data: Any) -> str:
        return json.dumps(data, sort_keys=True)

    def event(self, ts: str, event_type: str, data: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO events(ts,type,data) VALUES(?,?,?)",
            (ts, event_type, self._json(data)),
        )
        self.conn.commit()

    def recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(1000, int(limit)))
        rows = self.conn.execute(
            "SELECT id,ts,type,data FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {"id": row[0], "timestamp": row[1], "type": row[2], "data": json.loads(row[3])}
            for row in reversed(rows)
        ]

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

    def recent_scans(self, limit: int = 25) -> list[dict[str, Any]]:
        limit = max(1, min(250, int(limit)))
        rows = self.conn.execute(
            "SELECT id,started_at,finished_at,target,status,hosts,subnets,links "
            "FROM scans ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {"id": r[0], "started_at": r[1], "finished_at": r[2], "target": r[3],
             "status": r[4], "hosts": r[5], "subnets": r[6], "links": r[7]}
            for r in rows
        ]

    def snapshot(self, cartographer, scan_id: int | None = None) -> None:
        recorded_at = self.conn.execute("SELECT datetime('now')").fetchone()[0]
        for ip, host in cartographer.hosts.items():
            data = {
                "ip": host.ip, "subnet": host.subnet, "reachable": host.reachable,
                "latency_ms": host.latency_ms, "hostname": host.hostname,
                "ports": host.ports, "services": host.services,
                "os_candidates": host.os_candidates, "confidence": host.confidence,
                "last_seen": host.last_seen,
            }
            payload = self._json(data)
            self.conn.execute(
                "INSERT OR REPLACE INTO hosts VALUES(?,?,?,?)",
                (ip, host.subnet, payload, recorded_at),
            )
            self.conn.execute(
                "INSERT INTO host_history(scan_id,ip,subnet,data,recorded_at) VALUES(?,?,?,?,?)",
                (scan_id, ip, host.subnet, payload, recorded_at),
            )
        for cidr, subnet in cartographer.subnets.items():
            data = {
                "cidr": subnet.cidr, "parent": subnet.parent, "gateway": subnet.gateway,
                "status": subnet.status, "confidence": subnet.confidence,
                "hosts": sorted(subnet.hosts), "evidence": subnet.evidence,
            }
            payload = self._json(data)
            self.conn.execute(
                "INSERT OR REPLACE INTO subnets VALUES(?,?,?)",
                (cidr, payload, recorded_at),
            )
            self.conn.execute(
                "INSERT INTO subnet_history(scan_id,cidr,data,recorded_at) VALUES(?,?,?,?)",
                (scan_id, cidr, payload, recorded_at),
            )
        for link in cartographer.links:
            self.conn.execute(
                "INSERT OR REPLACE INTO links VALUES(?,?,?,?,?,?)",
                (link.source, link.destination, link.kind, link.confidence, link.evidence, recorded_at),
            )
            self.conn.execute(
                "INSERT INTO link_history(scan_id,source,destination,kind,confidence,evidence,recorded_at) VALUES(?,?,?,?,?,?,?)",
                (scan_id, link.source, link.destination, link.kind, link.confidence, link.evidence, recorded_at),
            )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
