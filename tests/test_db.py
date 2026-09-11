import json

from nexora.db import Database
from nexora.models import Host, Link, Subnet


class Snapshot:
    def __init__(self):
        self.hosts = {
            "192.168.1.10": Host(
                "192.168.1.10",
                "192.168.1.0/24",
                reachable=True,
                ports={443: "open"},
                services={443: "https"},
                confidence=0.8,
            )
        }
        self.subnets = {
            "192.168.1.0/24": Subnet(
                "192.168.1.0/24",
                status="complete",
                confidence=0.9,
                hosts={"192.168.1.10"},
                evidence={"method": "test"},
            )
        }
        self.links = [Link("192.168.1.10", "192.168.1.1", "route", 0.75, "hop")]


def test_database_persists_current_topology_and_history(tmp_path):
    db = Database(str(tmp_path / "nexora.db"))
    snapshot = Snapshot()
    scan_id = db.start_scan("2026-01-01T00:00:00+00:00", "192.168.1.0/24")
    db.event("2026-01-01T00:00:01+00:00", "HOST_DISCOVERED", {"ip": "192.168.1.10"})
    db.snapshot(snapshot, scan_id=scan_id)
    db.finish_scan(scan_id, "2026-01-01T00:00:02+00:00", snapshot)

    assert db.conn.execute("SELECT COUNT(*) FROM hosts").fetchone()[0] == 1
    assert db.conn.execute("SELECT COUNT(*) FROM subnets").fetchone()[0] == 1
    assert db.conn.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 1
    assert db.conn.execute("SELECT COUNT(*) FROM host_history").fetchone()[0] == 1
    assert db.conn.execute("SELECT COUNT(*) FROM subnet_history").fetchone()[0] == 1
    assert db.conn.execute("SELECT COUNT(*) FROM link_history").fetchone()[0] == 1

    scan = db.recent_scans(1)[0]
    assert scan["id"] == scan_id
    assert scan["status"] == "completed"
    assert scan["hosts"] == 1
    assert db.recent_events(1)[0]["type"] == "HOST_DISCOVERED"
    db.close()


def test_duplicate_current_link_is_upserted_but_history_is_retained(tmp_path):
    db = Database(str(tmp_path / "nexora.db"))
    snapshot = Snapshot()
    first = db.start_scan("2026-01-01T00:00:00+00:00", "192.168.1.0/24")
    db.snapshot(snapshot, scan_id=first)
    second = db.start_scan("2026-01-02T00:00:00+00:00", "192.168.1.0/24")
    snapshot.links[0].confidence = 0.9
    db.snapshot(snapshot, scan_id=second)

    assert db.conn.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 1
    row = db.conn.execute("SELECT confidence FROM links").fetchone()
    assert row[0] == 0.9
    assert db.conn.execute("SELECT COUNT(*) FROM link_history").fetchone()[0] == 2
    db.close()


def test_snapshot_serializes_metadata_deterministically(tmp_path):
    db = Database(str(tmp_path / "nexora.db"))
    snapshot = Snapshot()
    db.snapshot(snapshot)
    raw = db.conn.execute("SELECT data FROM hosts").fetchone()[0]
    decoded = json.loads(raw)
    assert decoded["services"] == {"443": "https"}
    assert decoded["reachable"] is True
    assert db.conn.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()[0] == "2"
    db.close()
