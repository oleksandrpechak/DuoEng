"""Simple migration bootstrap for SQLite schema initialization."""

from app.db import init_db, seed_from_dmklinger


if __name__ == "__main__":
    init_db()
    seeded = seed_from_dmklinger()
    print(f"Schema initialized. Seeded words: {seeded}")
