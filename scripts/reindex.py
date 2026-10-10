#!/usr/bin/env python
"""Rebuilds all existing LanceDB tables with the current embedding model.

    python scripts/reindex.py

Re-embeds chunks in each LanceDB table using Settings.EMBEDDING_MODEL (or hash
embeddings if DEMO_MODE=replay) and updates specialist knowledge manifests.
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import lancedb
from app.config import Settings
from app.models.manifest import StoredSpecialist
from app.services.llm_service import LLMService
from app.storage.store import Store

log = logging.getLogger("agentforge.reindex")


async def reindex_all() -> None:
    settings = Settings()
    llm = LLMService(settings)
    store = Store(settings.manifests_dir)
    db = lancedb.connect(str(settings.lancedb_uri))
    table_names = list(db.table_names())

    target_model = "hash/replay" if settings.DEMO_MODE == "replay" else settings.EMBEDDING_MODEL
    print(f"Starting reindex using embedding model: {target_model}")
    print(f"LanceDB URI: {settings.lancedb_uri}")
    print(f"Found {len(table_names)} tables in LanceDB: {table_names}\n")

    reindexed_count = 0
    total_chunks = 0

    for name in table_names:
        table = db.open_table(name)
        rows = table.to_arrow().to_pylist()
        if not rows:
            print(f"  [{name}] Table is empty; skipping.")
            continue

        print(f"  [{name}] Re-embedding {len(rows)} chunks...")
        texts = [r["text"] for r in rows]
        new_vecs = await llm.embed(texts, "document")
        new_rows = [
            {
                "chunk_id": r["chunk_id"],
                "source_file": r.get("source_file", ""),
                "text": r["text"],
                "vector": v,
            }
            for r, v in zip(rows, new_vecs)
        ]

        # Drop and recreate table with new embeddings
        db.drop_table(name)
        db.create_table(name, data=new_rows)
        reindexed_count += 1
        total_chunks += len(new_rows)
        print(f"  [{name}] Successfully rebuilt with {len(new_rows)} chunks.")

    # Update manifests on disk with the current embedding model
    print("\nUpdating specialist manifests...")
    updated_manifests = 0
    for f in sorted(settings.manifests_dir.glob("spec_*.json")):
        if f.name.endswith(".status.json"):
            continue
        sid = f.stem
        st = store.get_specialist(sid)
        if st and st.manifest.knowledge.collection_id:
            old_model = st.manifest.knowledge.embedding_model
            st.manifest.knowledge.embedding_model = target_model
            # Recompute manifest JSON
            f.write_text(st.model_dump_json(indent=2))
            store._specialists[sid] = st
            updated_manifests += 1
            print(f"  [{sid}] Updated manifest embedding_model: {old_model} -> {target_model}")

    print("\n" + "=" * 50)
    print(f"Reindex complete: {reindexed_count} tables ({total_chunks} chunks), {updated_manifests} manifests updated.")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(reindex_all())
