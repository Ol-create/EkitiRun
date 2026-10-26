"""Manage admin (organiser) accounts. Owner: Lead (E16).

From apps/api, or the API's shell on the host:

    python -m scripts.create_admin create --email ada@ekitirun.ng --name "Ada Okafor"
    python -m scripts.create_admin create --email ... --name ... --generate   # random password
    python -m scripts.create_admin reset-password --email ada@ekitirun.ng
    python -m scripts.create_admin sign-out --email ada@ekitirun.ng   # end all their sessions
    python -m scripts.create_admin deactivate --email ada@ekitirun.ng
    python -m scripts.create_admin activate --email ada@ekitirun.ng
    python -m scripts.create_admin list

Passwords are typed (not shown) unless --generate prints a random one once.
Changing a password, deactivating or signing out ends that admin's sessions.
"""

import argparse
import asyncio
import getpass
import secrets
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import MIN_PASSWORD_LENGTH, hash_password
from app.models import AdminUser


class AdminError(Exception):
    pass


def check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AdminError(f"Use at least {MIN_PASSWORD_LENGTH} characters.")


async def _get(session: AsyncSession, email: str) -> AdminUser:
    admin = await session.scalar(select(AdminUser).where(AdminUser.email == email.strip().lower()))
    if admin is None:
        raise AdminError(f"No admin with email {email}.")
    return admin


async def create(session: AsyncSession, email: str, name: str, password: str) -> AdminUser:
    check_password(password)
    email = email.strip().lower()
    if await session.scalar(select(AdminUser.id).where(AdminUser.email == email)):
        raise AdminError(f"{email} already has an account (use reset-password).")
    admin = AdminUser(email=email, name=name.strip(), password_hash=hash_password(password))
    session.add(admin)
    await session.commit()
    return admin


async def reset_password(session: AsyncSession, email: str, password: str) -> AdminUser:
    check_password(password)
    admin = await _get(session, email)
    admin.password_hash = hash_password(password)
    admin.session_version += 1
    await session.commit()
    return admin


async def sign_out(session: AsyncSession, email: str) -> AdminUser:
    admin = await _get(session, email)
    admin.session_version += 1
    await session.commit()
    return admin


async def set_active(session: AsyncSession, email: str, active: bool) -> AdminUser:
    admin = await _get(session, email)
    admin.is_active = active
    admin.session_version += 1
    await session.commit()
    return admin


def _ask_password(generate: bool) -> str:
    if generate:
        password = secrets.token_urlsafe(15)
        print(f"Password (shown once, give it to them privately): {password}")
        return password
    first = getpass.getpass("New password: ")
    if getpass.getpass("Again: ") != first:
        raise AdminError("The passwords don't match.")
    return first


async def main(args: argparse.Namespace) -> None:
    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        if args.command == "list":
            for a in await session.scalars(select(AdminUser).order_by(AdminUser.email)):
                state = "active" if a.is_active else "DEACTIVATED"
                print(f"{a.email:35} {a.name:25} {state:11} last sign-in {a.last_login_at or '-'}")
        elif args.command == "create":
            admin = await create(session, args.email, args.name, _ask_password(args.generate))
            print(f"Created {admin.email}.")
        elif args.command == "reset-password":
            admin = await reset_password(session, args.email, _ask_password(args.generate))
            print(f"New password set for {admin.email}; their old sessions are ended.")
        elif args.command == "sign-out":
            print(f"Signed {(await sign_out(session, args.email)).email} out everywhere.")
        else:
            admin = await set_active(session, args.email, args.command == "activate")
            print(f"{admin.email} is now {'active' if admin.is_active else 'deactivated'}.")


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    create_p = sub.add_parser("create")
    create_p.add_argument("--email", required=True)
    create_p.add_argument("--name", required=True)
    create_p.add_argument("--generate", action="store_true", help="print a random password")
    reset_p = sub.add_parser("reset-password")
    reset_p.add_argument("--email", required=True)
    reset_p.add_argument("--generate", action="store_true")
    for name in ("sign-out", "deactivate", "activate"):
        sub.add_parser(name).add_argument("--email", required=True)
    sub.add_parser("list")
    try:
        asyncio.run(main(parser.parse_args()))
    except AdminError as exc:
        sys.exit(f"Error: {exc}")


if __name__ == "__main__":
    cli()
