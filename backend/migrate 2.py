"""Simple migration bootstrap for SQLite schema initialization."""

from app.db import init_db, seed_sample_words_if_empty


if __name__ == "__main__":
    init_db()
    seeded = seed_sample_words_if_empty()
    print(f"Schema initialized. Seeded words: {seeded}")
