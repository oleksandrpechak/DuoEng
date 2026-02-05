#!/usr/bin/env python3
"""
CSV Import Script for DuoVocab Duel vocabulary

Usage:
    python import_words.py path/to/words.csv

CSV Format:
    ua,en,level
    привіт,hello,B1
    незважаючи на,despite,B2
    ...

The script will:
- Skip duplicate words (based on UA text)
- Validate level values (B1/B2 only)
- Report import statistics
"""

import csv
import sqlite3
import uuid
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / 'duovocab.db'

def import_words(csv_path: str):
    """Import words from CSV file into SQLite database"""
    
    if not Path(csv_path).exists():
        print(f"Error: File not found: {csv_path}")
        sys.exit(1)
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get existing words
    cursor.execute("SELECT ua FROM words")
    existing = {row['ua'] for row in cursor.fetchall()}
    
    imported = 0
    skipped = 0
    errors = 0
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        # Validate headers
        required_headers = {'ua', 'en', 'level'}
        if not required_headers.issubset(set(reader.fieldnames or [])):
            print(f"Error: CSV must have headers: {required_headers}")
            sys.exit(1)
        
        for row_num, row in enumerate(reader, start=2):
            ua = row['ua'].strip()
            en = row['en'].strip()
            level = row['level'].strip().upper()
            
            # Validate
            if not ua or not en:
                print(f"Row {row_num}: Skipping empty word")
                errors += 1
                continue
            
            if level not in ('B1', 'B2'):
                print(f"Row {row_num}: Invalid level '{level}', must be B1 or B2")
                errors += 1
                continue
            
            if ua in existing:
                skipped += 1
                continue
            
            # Insert
            try:
                cursor.execute(
                    "INSERT INTO words (id, ua, en, level) VALUES (?, ?, ?, ?)",
                    (str(uuid.uuid4()), ua, en, level)
                )
                existing.add(ua)
                imported += 1
            except Exception as e:
                print(f"Row {row_num}: Error inserting - {e}")
                errors += 1
    
    conn.commit()
    conn.close()
    
    print("\n=== Import Complete ===")
    print(f"Imported: {imported}")
    print(f"Skipped (duplicates): {skipped}")
    print(f"Errors: {errors}")
    
    # Show totals
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM words")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT level, COUNT(*) as cnt FROM words GROUP BY level")
    by_level = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    
    print(f"\nTotal words in database: {total}")
    for level, count in sorted(by_level.items()):
        print(f"  {level}: {count}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python import_words.py path/to/words.csv")
        print("\nCSV Format:")
        print("  ua,en,level")
        print("  привіт,hello,B1")
        sys.exit(1)
    
    import_words(sys.argv[1])
