"""Race-day load test (E12). Owner: Lead. Run against STAGING, never production.

Simulates race day at full size:
- spectators polling the leaderboard and the live map (every 5 s),
- spectators holding live streams open (/stream/results, /stream/positions),
- 20 checkpoint scanners uploading a batch every 10 s,
- GPS from every tracker, one point every 5 s each (5 gateway users share them).

Setup (see docs/runbook.md, "Load test"):
    python -m scripts.demo_race setup --runners 5000            # on staging
    python -m scripts.loadtest_fixtures > loadtest/fixtures.json # with staging's settings
    uv sync --group load
    uv run --group load locust -f loadtest/locustfile.py --host https://<staging api> \
        --users 5025 --spawn-rate 50 --run-time 15m --headless --processes -1

At the end it prints PASS or FAIL against the targets below and exits 1 on FAIL.
"""

import json
import os
import random
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from locust import HttpUser, between, constant, events, task

FIXTURES = json.loads(
    Path(os.environ.get("LOAD_FIXTURES", Path(__file__).with_name("fixtures.json"))).read_text()
)
SCANNERS = 20
GATEWAYS = 5

# Race-day targets: p95 response time per endpoint group (ms) and overall error rate.
TARGET_P95_MS = {"results": 500, "positions": 500, "scans": 1000, "gps": 1000}
TARGET_FAIL_RATIO = 0.01


class Spectator(HttpUser):
    """Someone following the race on the website."""

    weight = 90
    wait_time = between(4, 6)

    @task(5)
    def leaderboard(self):
        category = random.choice(FIXTURES["categories"])
        self.client.get(f"/api/v1/results?category={category}&limit=50", name="results")

    @task(3)
    def live_map(self):
        self.client.get("/api/v1/positions", name="positions")


class StreamWatcher(HttpUser):
    """Someone with a live page open: holds an SSE stream for a minute, then reconnects."""

    weight = 10
    wait_time = between(1, 3)

    @task
    def watch(self):
        if random.random() < 0.5:
            url, name = "/api/v1/stream/results", "stream results"
        else:
            url, name = (
                f"/api/v1/stream/positions?bib={random.choice(FIXTURES['bibs'])}",
                "stream positions",
            )
        started = time.monotonic()
        with self.client.get(
            url, name=name, stream=True, timeout=90, catch_response=True
        ) as response:
            if response.status_code not in (200, 404):  # 404: that runner has no tracker
                response.failure(f"status {response.status_code}")
                return
            for _ in response.iter_lines():
                if time.monotonic() - started > 60:
                    break
            response.success()


class Scanner(HttpUser):
    """One checkpoint phone, uploading what it scanned every 10 s."""

    fixed_count = SCANNERS
    wait_time = constant(10)

    def on_start(self):
        self.checkpoint = random.choice(FIXTURES["scanners"])
        self.runners = FIXTURES["runners_by_route"].get(str(self.checkpoint["route_id"]), [])

    @task
    def upload(self):
        if not self.runners:
            return
        now = datetime.now(UTC).isoformat()
        scans = [
            {"client_id": str(uuid.uuid4()), "qr_token": r["qr"], "scanned_at": now}
            for r in random.sample(self.runners, min(25, len(self.runners)))
        ]
        checkpoint_id = self.checkpoint["checkpoint_id"]
        body = {
            "device_id": f"loadtest-cp-{checkpoint_id}",
            "checkpoint_id": checkpoint_id,
            "scans": scans,
            "sent_at": now,
        }
        headers = {"Authorization": f"Bearer {self.checkpoint['token']}"}
        self.client.post("/api/v1/scans/batch", json=body, headers=headers, name="scans")


class GpsGateway(HttpUser):
    """Part of the Traccar gateway: a share of every tracker's fix, every 5 s."""

    fixed_count = GATEWAYS
    wait_time = constant(5)

    def on_start(self):
        index = getattr(GpsGateway, "_next", 0)
        GpsGateway._next = index + 1
        self.devices = FIXTURES["devices"][index::GATEWAYS]
        self.step = {d["device_id"]: random.randrange(50) for d in self.devices}

    @task
    def forward(self):
        now = datetime.now(UTC).isoformat()
        points = []
        for d in self.devices:
            course = FIXTURES["courses"][d["route_id"]]
            i = min(self.step[d["device_id"]], len(course) - 1)
            self.step[d["device_id"]] += 1
            lng, lat = course[i]
            points.append({"device_id": d["device_id"], "lat": lat, "lng": lng, "recorded_at": now})
        for start in range(0, len(points), 1000):
            self.client.post(
                "/api/v1/gps/positions",
                json={"positions": points[start : start + 1000]},
                headers={"X-Gateway-Secret": FIXTURES["gateway_secret"]},
                name="gps",
            )


@events.quitting.add_listener
def judge(environment, **_):
    """PASS/FAIL against the race-day targets; exit code 1 on FAIL."""
    stats = environment.stats
    problems = []
    for name, target in TARGET_P95_MS.items():
        entry = next((e for e in stats.entries.values() if e.name == name), None)
        if entry and entry.num_requests:
            p95 = entry.get_response_time_percentile(0.95)
            if p95 > target:
                problems.append(f"{name} p95 {p95:.0f} ms > {target} ms")
    if stats.total.fail_ratio > TARGET_FAIL_RATIO:
        problems.append(f"errors {stats.total.fail_ratio:.1%} > {TARGET_FAIL_RATIO:.0%}")
    if problems:
        print("LOAD TEST FAIL: " + "; ".join(problems))
        environment.process_exit_code = 1
    else:
        print("LOAD TEST PASS: all race-day targets met")
