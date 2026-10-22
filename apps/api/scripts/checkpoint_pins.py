"""Create the 6-digit PINs that unlock the scanner at each checkpoint. Owner: Lead (E7).

From apps/api (or `docker compose exec api python -m scripts.checkpoint_pins`):

    python -m scripts.checkpoint_pins              # PINs for checkpoints that have none
    python -m scripts.checkpoint_pins --reset-all  # new PINs everywhere (old ones stop working)

PINs are printed ONCE and only a hash is stored, so copy them to the volunteer
briefing sheet straight away. Phones already logged in keep working until their
24-hour login expires.
"""

import argparse
import asyncio
import secrets

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_pin
from app.models import Category, Checkpoint


def new_pin(taken: set[str]) -> str:
    while True:
        pin = f"{secrets.randbelow(1_000_000):06d}"
        if pin not in taken and len(set(pin)) > 2:  # unique, and not 000000 / 121212
            taken.add(pin)
            return pin


async def main(reset_all: bool) -> None:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(Checkpoint, Category.code)
                .join(Category, Category.route_id == Checkpoint.route_id)
                .order_by(Category.sort_order, Checkpoint.sort_order)
            )
        ).all()
        taken: set[str] = set()
        printed = []
        for checkpoint, category_code in rows:
            if checkpoint.pin_hash and not reset_all:
                continue
            pin = new_pin(taken)
            checkpoint.pin_hash = hash_pin(pin)
            printed.append((category_code, checkpoint.code, checkpoint.name, pin))
        await session.commit()

    if not printed:
        print("Every checkpoint already has a PIN. Use --reset-all to make new ones.")
        return
    print("category,checkpoint,name,pin")
    for row in printed:
        print(",".join(row))
    print(f"\n{len(printed)} PIN(s) set. They are not stored anywhere else: save them now.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reset-all", action="store_true", help="replace every existing PIN")
    asyncio.run(main(parser.parse_args().reset_all))
