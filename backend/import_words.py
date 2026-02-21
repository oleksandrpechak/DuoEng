#!/usr/bin/env python3
import csv
import sqlite3
import uuid
# import sys
from pathlib import Path
import argparse

def import_words(csv_path: str, db_path: str):
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise SystemExit(f"Error: File not found: {csv_path}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Ensure table + unique constraint (adjust if your app already migrated this)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS words (
        id TEXT PRIMARY KEY,
        ua TEXT NOT NULL,
        en TEXT NOT NULL,
        level TEXT NOT NULL,
        UNIQUE(ua, level)
    )
    """)

    errors = 0

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"ua", "en", "level"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise SystemExit(f"Error: CSV must have headers: {required}")

        rows = []
        for row_num, row in enumerate(reader, start=2):
            ua = (row.get("ua") or "").strip()
            en = (row.get("en") or "").strip()
            level = (row.get("level") or "").strip().upper()

            if not ua or not en:
                errors += 1
                continue
            if level not in ("B1", "B2"):
                errors += 1
                continue

            rows.append((str(uuid.uuid4()), ua, en, level))

    # Bulk insert with ignore-on-duplicate
    cur.executemany(
        "INSERT OR IGNORE INTO words (id, ua, en, level) VALUES (?, ?, ?, ?)",
        rows
    )
    conn.commit()

    # Stats
    cur.execute("SELECT COUNT(*) FROM words")
    total = cur.fetchone()[0]
    cur.execute("SELECT level, COUNT(*) FROM words GROUP BY level")
    by_level = dict(cur.fetchall())

    # Rough imported/skipped estimate: compare attempts vs changes
    # SQLite doesn't give per-row counts easily; keep it simple:
    print("=== Import Complete ===")
    print(f"Attempted: {len(rows)}")
    print(f"Total in DB: {total}")
    print("By level:", by_level)

    conn.close()

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("csv", help="Path to words.csv (headers: ua,en,level)")
    p.add_argument("--db", default=str(Path(__file__).parent / "duovocab.db"),
                   help="Path to SQLite db file")
    args = p.parse_args()
    import_words(args.csv, args.db)





# #!/usr/bin/env python3
# """
# CSV Import Script for DuoVocab Duel vocabulary

# Usage:
#     python import_words.py path/to/words.csv

# CSV Format:
#     ua,en,level
#     привіт,hello,B1
#     незважаючи на,despite,B2
#     ...

# The script will:
# - Skip duplicate words (based on UA text)
# - Validate level values (B1/B2 only)
# - Report import statistics
# """

# import csv
# import sqlite3
# import uuid
# import sys
# from pathlib import Path

# DB_PATH = Path(__file__).parent / 'duovocab.db'

# def import_words(csv_path: str):
#     """Import words from CSV file into SQLite database"""
    
#     if not Path(csv_path).exists():
#         print(f"Error: File not found: {csv_path}")
#         sys.exit(1)
    
#     conn = sqlite3.connect(str(DB_PATH))
#     conn.row_factory = sqlite3.Row
#     cursor = conn.cursor()
    
#     # Get existing words
#     cursor.execute("SELECT ua FROM words")
#     existing = {row['ua'] for row in cursor.fetchall()}
    
#     imported = 0
#     skipped = 0
#     errors = 0
    
#     with open(csv_path, 'r', encoding='utf-8') as f:
#         reader = csv.DictReader(f)
        
#         # Validate headers
#         required_headers = {'ua', 'en', 'level'}
#         if not required_headers.issubset(set(reader.fieldnames or [])):
#             print(f"Error: CSV must have headers: {required_headers}")
#             sys.exit(1)
        
#         for row_num, row in enumerate(reader, start=2):
#             ua = row['ua'].strip()
#             en = row['en'].strip()
#             level = row['level'].strip().upper()
            
#             # Validate
#             if not ua or not en:
#                 print(f"Row {row_num}: Skipping empty word")
#                 errors += 1
#                 continue
            
#             if level not in ('B1', 'B2'):
#                 print(f"Row {row_num}: Invalid level '{level}', must be B1 or B2")
#                 errors += 1
#                 continue
            
#             if ua in existing:
#                 skipped += 1
#                 continue
            
#             # Insert
#             try:
#                 cursor.execute(
#                     "INSERT INTO words (id, ua, en, level) VALUES (?, ?, ?, ?)",
#                     (str(uuid.uuid4()), ua, en, level)
#                 )
#                 existing.add(ua)
#                 imported += 1
#             except Exception as e:
#                 print(f"Row {row_num}: Error inserting - {e}")
#                 errors += 1
    
#     conn.commit()
#     conn.close()
    
#     print("\n=== Import Complete ===")
#     print(f"Imported: {imported}")
#     print(f"Skipped (duplicates): {skipped}")
#     print(f"Errors: {errors}")
    
#     # Show totals
#     conn = sqlite3.connect(str(DB_PATH))
#     cursor = conn.cursor()
#     cursor.execute("SELECT COUNT(*) as total FROM words")
#     total = cursor.fetchone()[0]
#     cursor.execute("SELECT level, COUNT(*) as cnt FROM words GROUP BY level")
#     by_level = {row[0]: row[1] for row in cursor.fetchall()}
#     conn.close()
    
#     print(f"\nTotal words in database: {total}")
#     for level, count in sorted(by_level.items()):
#         print(f"  {level}: {count}")

# if __name__ == "__main__":
#     if len(sys.argv) != 2:
#         print("Usage: python import_words.py path/to/words.csv")
#         print("\nCSV Format:")
#         print("  ua,en,level")
#         print("  привіт,hello,B1")
#         sys.exit(1)
    
#     import_words(sys.argv[1])
