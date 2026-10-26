"""Operations tooling for race week (E12): DB pooling, results export, preflight."""

import csv

from sqlalchemy import select

from app.core.database import engine_options
from app.core.security import hash_pin
from app.models import Checkpoint
from scripts import create_admin, demo_race, export_results, preflight
from scripts.seed import seed


def test_transaction_pooler_turns_off_statement_caching():
    pooled = engine_options(
        "postgresql+asyncpg://u:p@ep-cool-name-pooler.eu-central-1.aws.neon.tech/db"
    )
    direct = engine_options("postgresql+asyncpg://u:p@ep-cool-name.eu-central-1.aws.neon.tech/db")

    assert pooled["connect_args"] == {"statement_cache_size": 0, "prepared_statement_cache_size": 0}
    assert "connect_args" not in direct
    assert direct["pool_pre_ping"] is True


def test_time_format():
    assert export_results.hms(None) == ""
    assert export_results.hms(59) == "0:00:59"
    assert export_results.hms(2 * 3600 + 5 * 60 + 7) == "2:05:07"


async def test_results_export(session, tmp_path):
    await seed(session)
    await demo_race.setup(session, runners=80, started_minutes_ago=60)

    written = await export_results.export(session, tmp_path)

    assert set(written) == {"FULL", "HALF", "10K", "FUN"}
    with (tmp_path / "FUN.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == written["FUN"] > 0
    first = rows[0]
    assert (first["position"], first["status"]) == ("1", "finished")
    assert first["finish_time"].count(":") == 2


async def test_preflight_flags_what_needs_doing(session, redis):
    report = preflight.Report()
    await preflight.check_race_data(session, report)
    assert report.failed  # no categories yet

    await seed(session)
    await demo_race.setup(session, runners=20, started_minutes_ago=10)
    report = preflight.Report()
    await preflight.check_race_data(session, report)
    by_check = {check: (level, detail) for level, check, detail in report.lines}

    assert by_check["course HALF"][0] == "WARN"  # no scanner PINs yet
    assert "checkpoint_pins" in by_check["course HALF"][1]
    assert by_check["runners"][0] == "WARN"  # demo data in development
    assert "demo_race reset" in by_check["runners"][1]

    assert by_check["admins"][0] == "WARN"  # nobody can sign in yet

    for cp in await session.scalars(select(Checkpoint)):
        cp.pin_hash = hash_pin("123456")
    await demo_race.reset(session)
    await create_admin.create(session, "ada@ekitirun.ng", "Ada", "a long enough password")
    report = preflight.Report()
    await preflight.check_race_data(session, report)
    assert all(level == "PASS" for level, _, _ in report.lines), report.lines


async def test_preflight_checks_redis(redis):
    report = preflight.Report()

    await preflight.check_redis(redis, report)

    checks = {check: level for level, check, _ in report.lines}
    assert checks["redis"] == "PASS"
    assert checks["gps writer"] == "WARN"  # no GPS stream yet
