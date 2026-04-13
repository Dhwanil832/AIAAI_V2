"""
backfill_qdrant.py
──────────────────
One-time script to embed all existing HistoricalIncident rows into Qdrant.

Run from the backend/ directory:
    python scripts/backfill_qdrant.py

This is safe to re-run — Qdrant upsert overwrites existing points by ID.
Progress is printed every 50 records so you can watch it work.
3675 records will take a few minutes depending on Ollama speed.
"""

import asyncio
import sys
import os

# Allow imports from backend/ root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models.historical import HistoricalIncident
from core.qdrant import upsert_historical_incident, ensure_collection_exists


async def backfill():
    db = SessionLocal()

    try:
        total = db.query(HistoricalIncident).count()
        print(f"[backfill] found {total} historical incidents to index")

        if total == 0:
            print("[backfill] nothing to do — exiting")
            return

        # Make sure collection exists before upserting
        ensure_collection_exists()

        records = db.query(HistoricalIncident).order_by(HistoricalIncident.id).all()

        success = 0
        failed = 0

        for i, record in enumerate(records, start=1):
            try:
                await upsert_historical_incident(record)
                success += 1
            except Exception as e:
                print(f"[backfill] FAILED id={record.id}: {e}")
                failed += 1

            if i % 50 == 0 or i == total:
                print(f"[backfill] progress: {i}/{total} | success={success} failed={failed}")

        print(f"\n[backfill] complete — success={success} failed={failed} total={total}")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(backfill())