"""
Pre-seed script to load Hackathon Fixtures Batch 1 and Batch 2 into chronotrace.db.
Run with: python seed_fixtures.py
"""
import asyncio
import json
import logging
from app.database import AsyncSessionLocal, init_db
from app.schemas.ingestion import IngestBatchRequest, SourceRecordIn
from app.services.ingestion_service import ingest_batch

logging.basicConfig(level=logging.INFO)

async def seed():
    await init_db()
    print("Database schema initialized.")

    async with AsyncSessionLocal() as db:
        # Ingest Batch 1
        with open("fixtures/batch1_records.json", encoding="utf-8") as f:
            records_1 = [SourceRecordIn(**r) for r in json.load(f)]
        res1 = await ingest_batch(db, IngestBatchRequest(records=records_1), batch_id="batch-001")
        await db.commit()
        print(f"Batch 1 Seeded: {res1.records_processed} records, {res1.total_events_extracted} events, {res1.total_features_identified} features.")

        # Ingest Batch 2 (Incremental update without overwriting)
        with open("fixtures/batch2_records.json", encoding="utf-8") as f:
            records_2 = [SourceRecordIn(**r) for r in json.load(f)]
        res2 = await ingest_batch(db, IngestBatchRequest(records=records_2), batch_id="batch-002")
        await db.commit()
        print(f"Batch 2 Seeded: {res2.records_processed} records, {res2.total_events_extracted} events, {res2.total_features_identified} features.")

if __name__ == "__main__":
    asyncio.run(seed())

