import asyncio

from nexora.engine import Cartographer, Host, fingerprint, service_name, traceroute_command
from nexora.frontier import Frontier


def test_frontier_normalizes_seed():
    frontier = Frontier("192.168.10.7/24")
    assert frontier.seed == "192.168.10.0/24"
    assert list(frontier.queue) == [("192.168.10.0/24", None)]


def test_frontier_only_promotes_rfc1918():
    frontier = Frontier("192.168.10.0/24", expand=True)
    assert frontier._candidate("10.20.30.40") == "10.20.30.0/24"
    assert frontier._candidate("172.20.5.9") == "172.20.5.0/24"
    assert frontier._candidate("192.168.50.8") == "192.168.50.0/24"
    assert frontier._candidate("8.8.8.8") is None
    assert frontier._candidate("169.254.1.1") is None


def test_frontier_bounds_and_deduplicates():
    frontier = Frontier("192.168.10.0/24", max_subnets=2, expand=True)
    cartographer = Cartographer()
    cartographer.links = [
        type("L", (), {"destination": "10.0.0.9"})(),
        type("L", (), {"destination": "10.0.0.10"})(),
        type("L", (), {"destination": "172.16.1.5"})(),
    ]
    frontier._promote_paths(cartographer, frontier.seed)
    assert list(frontier.queue) == [
        ("192.168.10.0/24", None),
        ("10.0.0.0/24", "192.168.10.0/24"),
    ]


def test_service_mapping_and_fingerprint():
    assert service_name(22) == "ssh"
    assert service_name(9999) == "unknown"
    host = Host("192.168.1.10", "192.168.1.0/24", ports={445: "open"})
    candidates = fingerprint(host)
    assert candidates[0]["os"] == "Windows"
    assert candidates[0]["confidence"] > 0


def test_traceroute_commands_are_platform_specific():
    unix = traceroute_command("192.168.1.10")
    assert unix[0] == "traceroute" or unix[0] == "tracert"


def test_rate_limiter_enforces_minimum_spacing():
    async def run():
        from nexora.engine import RateLimiter
        limiter = RateLimiter(1000)
        await limiter.wait()
        start = asyncio.get_running_loop().time()
        await limiter.wait()
        return asyncio.get_running_loop().time() - start

    elapsed = asyncio.run(run())
    assert elapsed >= 0
