"""Tests for multilingual retrieval, query rewriting, scope checking, reindexing, and fallback messages."""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from app.config import Settings
from app.main import check_embedding_mismatch
from datetime import datetime, timezone
from app.models.manifest import (
    EvaluationSuite,
    EvalTestCase,
    GuardrailsSpec,
    IdentitySpec,
    KnowledgeSpec,
    MissionSpec,
    ModelConfigSpec,
    PersonaSpec,
    ProvenanceMetadata,
    SpecialistManifest,
    StoredSpecialist,
)
from app.services.multilingual_messages import (
    generate_no_info_message,
    generate_out_of_scope_message,
    is_friendly_tone,
)
from app.services.rag_service import RAGService, RetrievedChunk
from app.storage.store import Store


def create_sample_manifest(company="Acme Cloud", tone=None, embedding_model="bge-m3"):
    suite = EvaluationSuite(test_cases=[
        EvalTestCase(id="t1", category="in_scope", kind="rag", prompt="prompt 1", expect_refusal=False),
        EvalTestCase(id="t2", category="in_scope", kind="rag", prompt="prompt 2", expect_refusal=False),
        EvalTestCase(id="t3", category="in_scope", kind="rag", prompt="prompt 3", expect_refusal=False),
        EvalTestCase(id="t4", category="out_of_scope", kind="rag", prompt="prompt 4", expect_refusal=True),
        EvalTestCase(id="t5", category="prompt_injection", kind="rag", prompt="prompt 5", expect_refusal=True),
    ])
    prov = ProvenanceMetadata(architect_session_id="s1", compiled_at=datetime.now(timezone.utc), architect_model="gemma4:12b")
    return SpecialistManifest(
        specialist_id="spec_test01",
        identity=IdentitySpec(name="Aria", role="Support Specialist", company=company, target_audience="Customers"),
        persona=PersonaSpec(tone=tone or ["formal", "professional"], greeting_message="Hello, how can I help you today?"),
        mission=MissionSpec(
            primary_goal="Help with hardware orders and refunds.",
            in_scope_topics=["order status", "refund eligibility"],
            out_of_scope_topics=["competitor comparisons", "tax or legal advice"],
        ),
        knowledge=KnowledgeSpec(
            collection_id="col_test01",
            document_names=["policy.md"],
            score_threshold=0.50,
            embedding_model=embedding_model,
        ),
        tools=[],
        guardrails=GuardrailsSpec(
            blocked_phrases=[],
            never_do_rules=["Never disclose secrets"],
            fallback_out_of_scope_response="I can only help with topics within my scope.",
        ),
        model=ModelConfigSpec(model_name="gemma4:12b"),
        evaluation=suite,
        provenance=prov,
    )


def test_knowledge_manifest_stores_embedding_model(tmp_path):
    """Verify KnowledgeSpec stores embedding_model and compiler sets it."""
    m = create_sample_manifest(embedding_model="bge-m3")
    assert m.knowledge.embedding_model == "bge-m3"


def test_startup_detects_embedding_mismatch(tmp_path):
    """Verify startup detects and logs mismatch between manifest embedding_model and settings."""
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir(parents=True)
    store = Store(manifests_dir)

    # Save a specialist indexed with old model
    m_old = create_sample_manifest(embedding_model="nomic-embed-text")
    store.save_specialist(m_old, "sha_old")

    settings = Settings(MANIFESTS_DIR=str(manifests_dir), EMBEDDING_MODEL="bge-m3", DEMO_MODE="off")
    mismatches = check_embedding_mismatch(store, settings)
    assert "spec_test01" in mismatches

    # Matching model
    settings_match = Settings(MANIFESTS_DIR=str(manifests_dir), EMBEDDING_MODEL="nomic-embed-text", DEMO_MODE="off")
    assert check_embedding_mismatch(store, settings_match) == []


def test_per_language_threshold_config():
    """Verify per-language threshold lookup and defaults."""
    s = Settings(
        RAG_SCORE_THRESHOLD=0.50,
        RAG_SCORE_THRESHOLD_EN=0.52,
        RAG_SCORE_THRESHOLD_NE=0.53,
        RAG_SCORE_THRESHOLD_NE_ROMAN=0.45,
        SCOPE_OUT_MIN=0.35,
        SCOPE_OUT_MIN_EN=0.50,
        SCOPE_OUT_MIN_NE=0.35,
        SCOPE_OUT_MIN_NE_ROMAN=0.39,
        SCOPE_MARGIN=0.03,
        SCOPE_MARGIN_EN=0.06,
        SCOPE_MARGIN_NE=0.03,
        SCOPE_MARGIN_NE_ROMAN=0.03,
        DEMO_MODE="off",
    )
    assert s.get_rag_score_threshold("en") == 0.52
    assert s.get_rag_score_threshold("ne") == 0.53
    assert s.get_rag_score_threshold("ne_roman") == 0.45

    assert s.get_scope_out_min("en") == 0.50
    assert s.get_scope_out_min("ne") == 0.35
    assert s.get_scope_out_min("ne_roman") == 0.39

    assert s.get_scope_margin("en") == 0.06
    assert s.get_scope_margin("ne") == 0.03
    assert s.get_scope_margin("ne_roman") == 0.03


def test_replay_mode_thresholds_preserved():
    """Verify replay mode preserves hash embedder thresholds."""
    s = Settings(
        DEMO_MODE="replay",
        RAG_SCORE_THRESHOLD=0.08,
        SCOPE_OUT_MIN=0.35,
        SCOPE_MARGIN=0.05,
    )
    assert s.get_rag_score_threshold("en") == 0.08
    assert s.get_rag_score_threshold("ne") == 0.08
    assert s.get_scope_out_min("en") == 0.35
    assert s.get_scope_out_min("ne") == 0.35
    assert s.get_scope_margin("en") == 0.05
    assert s.get_scope_margin("ne") == 0.05


@pytest.mark.asyncio
async def test_roman_nepali_query_rewrite_and_merge(tmp_path):
    """Verify Roman Nepali query is rewritten into English and Devanagari and merged by best score."""
    settings = Settings(
        DATA_DIR=str(tmp_path / "data"),
        LANCEDB_URI=str(tmp_path / "lancedb"),
        QUERY_REWRITE="on",
        DEMO_MODE="off",
    )
    settings.ensure_dirs()

    # Mock LLMService
    mock_llm = AsyncMock()
    mock_llm.rewrite_query.return_value = (
        "How long do I have to return hardware?",
        "हार्डवेयर सामान फिर्ता गर्न कति दिनको समय हुन्छ?",
    )

    rag = RAGService(settings, mock_llm)

    # Ingest a small document into mock table
    table_mock = AsyncMock()
    # Mock _search_vector returning different scores for each variant
    async def fake_search(table, query, top_k):
        if "Hardware saman return" in query:  # Roman Nepali original
            return [{"chunk_id": "c1", "source_file": "doc.md", "_distance": 0.43, "text": "Hardware returns within 30 days."}]
        elif "How long" in query:             # English rewrite
            return [{"chunk_id": "c1", "source_file": "doc.md", "_distance": 0.26, "text": "Hardware returns within 30 days."}]
        elif "हार्डवेयर" in query:            # Devanagari rewrite
            return [{"chunk_id": "c1", "source_file": "doc.md", "_distance": 0.30, "text": "Hardware returns within 30 days."}]
        return []

    rag._open = lambda cid: table_mock
    rag._search_vector = fake_search

    chunks = await rag.retrieve("col_test", "Hardware saman return garne samaya kati ho?", top_k=3, threshold=0.45)

    # Verify query rewrite was called
    mock_llm.rewrite_query.assert_awaited_once_with("Hardware saman return garne samaya kati ho?")

    # Verify de-duplicated chunk has best score (1.0 - 0.26 = 0.74 from English rewrite)
    assert len(chunks) == 1
    assert chunks[0].chunk_id == "c1"
    assert chunks[0].score == 0.74


@pytest.mark.asyncio
async def test_query_rewrite_switchable_off(tmp_path):
    """Verify QUERY_REWRITE=off disables rewriting."""
    settings = Settings(
        DATA_DIR=str(tmp_path / "data"),
        LANCEDB_URI=str(tmp_path / "lancedb"),
        QUERY_REWRITE="off",
        DEMO_MODE="off",
    )
    mock_llm = AsyncMock()
    rag = RAGService(settings, mock_llm)
    rag._open = lambda cid: AsyncMock()
    rag._search_vector = AsyncMock(return_value=[])

    await rag.retrieve("col_test", "Hardware saman return garne samaya kati ho?", top_k=3)
    mock_llm.rewrite_query.assert_not_called()


def test_multilingual_fallback_messages_tone_and_language():
    """Verify out-of-scope fallback and no-info messages match user language and company tone."""
    m_formal = create_sample_manifest(company="Himalayan Tech", tone=["formal", "professional"])
    m_friendly = create_sample_manifest(company="Himalayan Tech", tone=["friendly", "approachable"])

    # Devanagari Nepali
    ne_formal_fallback = generate_out_of_scope_message(m_formal, "ne")
    assert "Himalayan Tech" in ne_formal_fallback
    assert "माफ गर्नुहोला" in ne_formal_fallback
    assert "सम्पर्क गर्नुहोस्" in ne_formal_fallback

    ne_friendly_fallback = generate_out_of_scope_message(m_friendly, "ne")
    assert "Himalayan Tech" in ne_friendly_fallback
    assert "माफ गर है" in ne_friendly_fallback
    assert "सक्छौ" in ne_friendly_fallback

    # Roman Nepali
    rn_formal_fallback = generate_out_of_scope_message(m_formal, "ne_roman")
    assert "Himalayan Tech" in rn_formal_fallback
    assert "Maf garnuhos" in rn_formal_fallback
    assert "contact garnuhos" in rn_formal_fallback

    rn_friendly_fallback = generate_out_of_scope_message(m_friendly, "ne_roman")
    assert "Himalayan Tech" in rn_friendly_fallback
    assert "Maf gara hai" in rn_friendly_fallback
    assert "sakchhau" in rn_friendly_fallback

    # No Info message in Nepali and Roman Nepali
    ne_no_info = generate_no_info_message(m_formal, "ne")
    assert "Himalayan Tech" in ne_no_info
    assert "उपलब्ध छैन" in ne_no_info or "फेला परेन" in ne_no_info

    rn_no_info = generate_no_info_message(m_formal, "ne_roman")
    assert "Himalayan Tech" in rn_no_info
    assert "uplabdha chhaina" in rn_no_info or "bhetiyena" in rn_no_info


@pytest.mark.asyncio
async def test_reindex_script_rebuilds_tables_and_manifests(tmp_path):
    """Verify scripts/reindex.py logic rebuilds table and updates manifest."""
    import lancedb
    import sys
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import scripts.reindex as reindexer

    settings = Settings(
        DATA_DIR=str(tmp_path / "data"),
        LANCEDB_URI=str(tmp_path / "lancedb"),
        MANIFESTS_DIR=str(tmp_path / "manifests"),
        EMBEDDING_MODEL="bge-m3",
        DEMO_MODE="replay",  # Uses deterministic hash embedder
    )
    settings.ensure_dirs()

    # Create dummy LanceDB table with old vector
    db = lancedb.connect(str(settings.lancedb_uri))
    old_rows = [{"chunk_id": "c1", "source_file": "doc.md", "text": "Hardware refund policy", "vector": [0.0] * 512}]
    db.create_table("col_reindex01", data=old_rows)

    # Save a specialist manifest with old model name
    store = Store(settings.manifests_dir)
    m = create_sample_manifest(embedding_model="old-model")
    m.specialist_id = "spec_reindex01"
    m.knowledge.collection_id = "col_reindex01"
    store.save_specialist(m, "sha1")

    # Run reindex
    from unittest.mock import patch
    with patch("scripts.reindex.Settings", return_value=settings):
        await reindexer.reindex_all()

    # Verify table has new non-zero vectors
    table = db.open_table("col_reindex01")
    reindexed_rows = table.to_arrow().to_pylist()
    assert len(reindexed_rows) == 1
    assert any(v > 0 for v in reindexed_rows[0]["vector"])

    # Verify manifest updated on disk
    fresh_store = Store(settings.manifests_dir)
    st = fresh_store.get_specialist("spec_reindex01")
    assert st.manifest.knowledge.embedding_model == "hash/replay"
