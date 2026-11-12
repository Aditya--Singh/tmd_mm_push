"""The demo accounts.

The accounts are read from `seed/users.csv`, which holds the same content as the `users` and
`refer` worksheets of the account sheet: the account name, the password in plain text, the
role in the News Feed and the role in Peer Benchmarking.

The plain password never reaches the database. It is hashed here, and only the hash is
stored, exactly as it is for every other account.

The file is read fresh on every run, and the password and the two roles of every account are
written from it. That way a password changed in the sheet is applied by running the script
again.
"""

import csv
from datetime import datetime
from pathlib import Path

# The repair has to happen before SQLAlchemy is imported, so it is imported first.
# It does nothing on a machine that loads compiled parts as usual.
from app import blocked_extensions  # noqa: F401

import bcrypt
from sqlalchemy import func

from app.database.database import Base, SessionLocal, engine
from app.models.user import User


SEED_FILE = Path(__file__).resolve().parent / "seed" / "users.csv"


def read_seed_file(path: Path = SEED_FILE) -> list[dict]:
    """Read the accounts from the sheet."""
    if not path.exists():
        raise SystemExit(
            f"The account sheet is missing: {path}\n"
            "It holds the account name, the password and the two roles."
        )

    accounts: list[dict] = []

    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            username = (row.get("username") or "").strip()

            if not username:
                continue

            accounts.append(
                {
                    "username": username,
                    "password": row.get("password") or "",
                    "role_news": (row.get("role_news") or "user").strip(),
                    "role_bench": (row.get("role_bench") or "viewer").strip(),
                    "is_active": int(row.get("is_active") or 1),
                }
            )

    if not accounts:
        raise SystemExit(f"The account sheet is empty: {path}")

    return accounts


def seed_users() -> None:
    """
    Bring the accounts in line with the sheet.

    The sheet is the source of truth: the password and the two roles of every account are
    taken from it and written afresh. The plain password is hashed here, and only the hash
    is stored.
    """
    # The accounts are created before the server has ever run, so the
    # tables may not be there yet.
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        accounts = read_seed_file()

        for item in accounts:
            existing = (
                db.query(User)
                .filter(User.username == item["username"])
                .first()
            )

            password_hash = bcrypt.hashpw(
                item["password"].encode("utf-8"),
                bcrypt.gensalt(),
            ).decode("utf-8")

            if existing:
                existing.password_hash = password_hash
                existing.role_news = item["role_news"]
                existing.role_bench = item["role_bench"]
                existing.is_active = item["is_active"]

                print(f"User '{item['username']}' brought up to date.")

                continue

            user = User(
                username=item["username"],
                password_hash=password_hash,
                role_news=item["role_news"],
                role_bench=item["role_bench"],
                is_active=item["is_active"],
                created_at=datetime.utcnow(),
            )

            db.add(user)

            print(f"User '{item['username']}' created.")

        db.commit()

        # An account that was made under a different spelling of the same name - the
        # account sheet writes the names in lower case, an older installation may
        # have "Admin" - is the same person and is replaced by it. Leaving both would
        # make the sign-in ambiguous.
        superseded = 0

        for item in accounts:
            others = (
                db.query(User)
                .filter(
                    func.lower(User.username) == item["username"].lower(),
                    User.username != item["username"],
                )
                .all()
            )

            for other in others:
                db.delete(other)

                superseded += 1

                print(f"User '{other.username}' replaced by '{item['username']}'.")

        if superseded:
            db.commit()

        print("Demo users seeded successfully.")

    finally:
        db.close()


if __name__ == "__main__":
    seed_users()
