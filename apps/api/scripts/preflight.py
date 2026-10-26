"""Race-readiness check. Owner: Lead (E12).

    python -m scripts.preflight        # locally, or in the API's shell on the host

Prints PASS / WARN / FAIL for each check and exits with status 1 if anything
FAILs. Run it after every deploy, the evening before the race, and on race
morning (see docs/runbook.md).
"""

import asyncio
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AdminUser, Category, Checkpoint, Runner, Tracker
from app.modules.gps import ingest


@dataclass
class Report:
    lines: list[tuple[str, str, str]] = field(default_factory=list)

    def add(self, level: str, check: str, detail: str) -> None:
        self.lines.append((level, check, detail))

    @property
    def failed(self) -> bool:
        return any(level == "FAIL" for level, _, _ in self.lines)

    def print(self) -> None:
        for level, check, detail in self.lines:
            print(f"[{level:4}] {check}: {detail}")
        counts = {
            lvl: sum(1 for x in self.lines if x[0] == lvl) for lvl in ("PASS", "WARN", "FAIL")
        }
        print(f"\n{counts['PASS']} passed, {counts['WARN']} warnings, {counts['FAIL']} failed")


def check_settings(report: Report) -> None:
    prod = settings.environment == "production"
    report.add("PASS" if prod else "WARN", "environment", settings.environment)
    for name in ("public_api_url", "public_web_url"):
        url = getattr(settings, name)
        ok = url.startswith("https://") or not prod
        report.add("PASS" if ok else "FAIL", name, url + ("" if ok else " (needs https)"))
    web_allowed = settings.public_web_url in settings.cors_origins
    report.add(
        "PASS" if web_allowed else "FAIL",
        "cors_origins",
        ", ".join(settings.cors_origins)
        + ("" if web_allowed else f" (missing {settings.public_web_url})"),
    )
    report.add(
        "PASS" if settings.race_date else "WARN",
        "race_date",
        str(settings.race_date or "not set: ages are checked against today"),
    )
    report.add(
        "PASS" if settings.sms_provider == "termii" else "WARN", "sms", settings.sms_provider
    )
    live_key = settings.paystack_secret_key.startswith("sk_live_")
    report.add(
        "PASS" if settings.payment_provider == "paystack" and live_key else "WARN",
        "payments",
        f"{settings.payment_provider}, {'live' if live_key else 'not a live'} key",
    )


async def check_database(session: AsyncSession, report: Report) -> None:
    await session.execute(text("SELECT 1"))
    report.add("PASS", "database", "reachable")
    current = await session.scalar(text("SELECT version_num FROM alembic_version"))
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    report.add(
        "PASS" if current == head else "FAIL",
        "migrations",
        f"at {current}"
        + ("" if current == head else f", head is {head}: run alembic upgrade head"),
    )


async def check_race_data(session: AsyncSession, report: Report) -> None:
    categories = list(await session.scalars(select(Category).order_by(Category.sort_order)))
    if not categories:
        report.add("FAIL", "categories", "none: run python -m scripts.seed")
        return
    for c in categories:
        cps = list(
            await session.scalars(select(Checkpoint).where(Checkpoint.route_id == c.route_id))
        )
        has_ends = any(cp.is_start for cp in cps) and any(cp.is_finish for cp in cps)
        no_pin = [cp.code for cp in cps if not cp.pin_hash]
        gun = c.gun_start_at.isoformat(timespec="minutes") if c.gun_start_at else "not recorded"
        level = "FAIL" if not has_ends else ("WARN" if no_pin else "PASS")
        detail = f"{len(cps)} checkpoints, gun {gun}"
        if no_pin:
            detail += f"; no scanner PIN at {', '.join(no_pin)} (python -m scripts.checkpoint_pins)"
        if not has_ends:
            detail += "; missing START or FINISH checkpoint"
        report.add(level, f"course {c.code}", detail)

    runners = await session.scalar(select(func.count()).select_from(Runner)) or 0
    demo = await session.scalar(
        select(func.count()).select_from(Runner).where(Runner.phone.like("+23480900%"))
    )
    report.add(
        "FAIL" if demo and settings.environment == "production" else ("WARN" if demo else "PASS"),
        "runners",
        f"{runners} registered"
        + (f", {demo} DEMO (python -m scripts.demo_race reset)" if demo else ""),
    )
    admins = await session.scalar(
        select(func.count()).select_from(AdminUser).where(AdminUser.is_active.is_(True))
    )
    report.add(
        "PASS" if admins else ("FAIL" if settings.environment == "production" else "WARN"),
        "admins",
        f"{admins} active" + ("" if admins else " (python -m scripts.create_admin create ...)"),
    )
    trackers = dict(
        (await session.execute(select(Tracker.status, func.count()).group_by(Tracker.status))).all()
    )
    usable = (
        trackers.get("available", 0) + trackers.get("returned", 0) + trackers.get("assigned", 0)
    )
    report.add(
        "PASS" if usable >= runners else "WARN",
        "trackers",
        f"{usable} usable for {runners} runners ({trackers or 'none'})",
    )


async def check_redis(redis: Redis, report: Report) -> None:
    await redis.ping()
    report.add("PASS", "redis", "reachable")
    try:
        policy = (await redis.config_get("maxmemory-policy")).get("maxmemory-policy")
        report.add(
            "PASS" if policy == "noeviction" else "WARN",
            "redis eviction",
            f"{policy} (want noeviction: streams and caches must not be dropped)",
        )
    except Exception:
        report.add(
            "WARN", "redis eviction", "can't read maxmemory-policy; check it in the dashboard"
        )
    try:
        groups = await redis.xinfo_groups(ingest.STREAM)
        lag = sum(int(g.get("pending", 0)) for g in groups)
        report.add(
            "PASS" if lag < 10_000 else "WARN",
            "gps writer",
            f"{len(groups)} group(s), {lag} pending",
        )
    except Exception:
        report.add("WARN", "gps writer", "no GPS stream yet (is the gps-writer running?)")


async def run(session: AsyncSession, redis: Redis) -> Report:
    report = Report()
    check_settings(report)
    for name, check in (("database", check_database), ("race data", check_race_data)):
        try:
            await check(session, report)
        except Exception as exc:
            report.add("FAIL", name, f"{type(exc).__name__}: {exc}")
            break
    try:
        await check_redis(redis, report)
    except Exception as exc:
        report.add("FAIL", "redis", f"{type(exc).__name__}: {exc}")
    return report


async def main() -> int:
    from app.core.database import SessionLocal

    print(f"EkitiRun preflight, {datetime.now(UTC):%Y-%m-%d %H:%M} UTC\n")
    redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=5)
    async with SessionLocal() as session:
        report = await run(session, redis)
    await redis.aclose()
    report.print()
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
