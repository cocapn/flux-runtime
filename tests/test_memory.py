"""Tests for the FLUX memory system — persistent memory, experience, bandit, and learning."""

import os
import shutil
import time
import tempfile

import pytest

from flux.memory.store import MemoryStore, MemoryEntry, MemoryStats, TIER_ORDER
from flux.memory.experience import Experience, ExperienceRecorder, GeneralizedRule
from flux.memory.bandit import MutationBandit, StrategyStats
from flux.memory.learning import LearningRateAdapter, LearningState


# ── Helpers ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_dir():
    """Provide a temporary directory that is cleaned up after each test."""
    d = tempfile.mkdtemp(prefix="flux_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def store(tmp_dir):
    """Provide a MemoryStore with a temporary directory."""
    s = MemoryStore(base_path=os.path.join(tmp_dir, "memory"))
    s.startup()
    yield s
    s.shutdown()


@pytest.fixture
def recorder():
    """Provide an ExperienceRecorder without persistence."""
    return ExperienceRecorder()


@pytest.fixture
def bandit():
    """Provide a MutationBandit with fixed seed."""
    return MutationBandit(seed=42)


@pytest.fixture
def adapter():
    """Provide a LearningRateAdapter with default settings."""
    return LearningRateAdapter()


# ══════════════════════════════════════════════════════════════════════════════
# MemoryStore Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestMemoryStoreBasics:
    """Basic store and retrieve operations."""

    def test_store_and_retrieve_hot(self, store):
        store.store("key1", {"data": "hello"}, tier="hot")
        assert store.retrieve("key1") == {"data": "hello"}

    def test_store_and_retrieve_warm(self, store):
        store.store("key2", [1, 2, 3], tier="warm")
        assert store.retrieve("key2") == [1, 2, 3]

    def test_store_and_retrieve_cold(self, store):
        store.store("key3", "cold_value", tier="cold")
        assert store.retrieve("key3") == "cold_value"

    def test_store_and_retrieve_frozen(self, store):
        store.store("key4", {"frozen": True}, tier="frozen")
        assert store.retrieve("key4") == {"frozen": True}

    def test_retrieve_missing_key(self, store):
        assert store.retrieve("nonexistent") is None

    def test_store_overwrites_previous_tier(self, store):
        """Storing the same key at a different tier removes it from the old tier."""
        store.store("key", "hot_val", tier="hot")
        store.store("key", "warm_val", tier="warm")
        assert store.retrieve("key") == "warm_val"

    def test_store_invalid_tier_raises(self, store):
        with pytest.raises(ValueError, match="Invalid tier"):
            store.store("key", "val", tier="invalid")

    def test_store_string_value(self, store):
        store.store("str_key", "just a string")
        assert store.retrieve("str_key") == "just a string"

    def test_store_numeric_value(self, store):
        store.store("num_key", 42)
        assert store.retrieve("num_key") == 42

    def test_store_bool_value(self, store):
        store.store("bool_key", True)
        assert store.retrieve("bool_key") is True


class TestMemoryEntry:
    """Tests for MemoryEntry data structure."""

    def test_creation(self):
        entry = MemoryEntry(key="test", value=42)
        assert entry.key == "test"
        assert entry.value == 42
        assert entry.tier == "hot"
        assert entry.access_count == 0
        assert entry.relevance == 1.0

    def test_touch(self):
        entry = MemoryEntry(key="test", value=42)
        entry.touch()
        assert entry.access_count == 1

    def test_is_expired_no_ttl(self):
        entry = MemoryEntry(key="test", value=42, ttl=0)
        assert entry.is_expired() is False

    def test_is_expired_with_ttl(self):
        entry = MemoryEntry(
            key="test", value=42, ttl=-1,  # Already expired
        )
        assert entry.is_expired() is True

    def test_decay_relevance(self):
        entry = MemoryEntry(key="test", value=42)
        entry.last_accessed = time.time() - 7200  # 2 hours ago
        entry.decay_relevance(half_life=3600.0)
        assert entry.relevance < 1.0

    def test_to_dict_roundtrip(self):
        entry = MemoryEntry(key="test", value={"nested": True}, tier="warm", ttl=60)
        d = entry.to_dict()
        restored = MemoryEntry.from_dict(d)
        assert restored.key == entry.key
        assert restored.value == entry.value
        assert restored.tier == entry.tier
        assert restored.ttl == entry.ttl


class TestMemoryPromotion:
    """Tests for tier promotion."""

    def test_promote_cold_to_warm(self, store):
        store.store("key", "value", tier="cold")
        store.promote("key")
        # Should now be in warm, not cold
        assert store.retrieve("key") == "value"
        assert "key" in store._warm_cache
        assert "key" not in store._cold_cache

    def test_promote_warm_to_hot(self, store):
        store.store("key", "value", tier="warm")
        store.promote("key")
        assert "key" in store._hot
        assert "key" not in store._warm_cache

    def test_promote_hot_is_noop(self, store):
        store.store("key", "value", tier="hot")
        store.promote("key")
        assert "key" in store._hot

    def test_promote_frozen_to_cold(self, store):
        store.store("key", {"archived": True}, tier="frozen")
        store.promote("key")
        # Frozen → cold after promotion
        assert store.retrieve("key") == {"archived": True}

    def test_promote_nonexistent_is_noop(self, store):
        store.promote("nonexistent")  # Should not raise


class TestMemoryDecay:
    """Tests for the forgetting curve / decay behavior."""

    def test_decay_demotes_low_relevance_hot(self, store):
        store.store("key", "value", tier="hot")
        # Manually set very low relevance
        entry = store._hot["key"]
        entry.relevance = 0.001
        entry.last_accessed = time.time() - 100000  # Very old

        demoted = store.decay()
        assert demoted >= 1
        # Should be demoted from hot
        assert "key" not in store._hot

    def test_decay_demotes_low_relevance_warm(self, store):
        store.store("key", "value", tier="warm")
        entry = store._warm_cache["key"]
        entry.relevance = 0.001
        entry.last_accessed = time.time() - 100000

        demoted = store.decay()
        assert demoted >= 1
        assert "key" not in store._warm_cache

    def test_decay_demotes_low_relevance_cold(self, store):
        store.store("key", "value", tier="cold")
        entry = store._cold_cache["key"]
        entry.relevance = 0.001
        entry.last_accessed = time.time() - 100000

        demoted = store.decay()
        assert demoted >= 1
        assert "key" not in store._cold_cache

    def test_no_decay_for_fresh_items(self, store):
        store.store("key", "value", tier="hot")
        demoted = store.decay()
        # Fresh items should not be demoted
        assert "key" in store._hot
        # No items should be demoted
        assert demoted == 0


class TestTTLExpiry:
    """Tests for time-to-live behavior."""

    def test_expired_item_not_retrieved(self, store):
        store.store("key", "value", tier="hot", ttl=-1)  # Already expired
        assert store.retrieve("key") is None

    def test_expired_item_removed_from_tier(self, store):
        store.store("key", "value", tier="hot", ttl=-1)
        store.retrieve("key")  # Triggers removal
        assert "key" not in store._hot


class TestArchiveAndFrozen:
    """Tests for archiving and frozen storage."""

    def test_archive_moves_all_cold_to_frozen(self, store):
        store.store("k1", "v1", tier="cold")
        store.store("k2", "v2", tier="cold")
        store.store("k3", "v3", tier="cold")

        archived = store.archive()
        assert archived == 3
        assert len(store._cold_cache) == 0

        # Should still be retrievable from frozen
        assert store.retrieve("k1") == "v1"
        assert store.retrieve("k2") == "v2"
        assert store.retrieve("k3") == "v3"

    def test_archive_empty_cold(self, store):
        archived = store.archive()
        assert archived == 0

    def test_frozen_uses_gzip(self, store):
        store.store("gz_key", {"compressed": True}, tier="frozen")
        # File should exist
        filepath = os.path.join(store._frozen_path, "gz_key.json.gz")
        assert os.path.exists(filepath)

    def test_frozen_long_key_uses_hash(self, store):
        long_key = "a" * 100
        store.store(long_key, "value", tier="frozen")
        # Should use hashed filename
        files = os.listdir(store._frozen_path)
        assert len(files) == 1
        assert files[0].endswith(".json.gz")


class TestMemoryStats:
    """Tests for memory statistics."""

    def test_stats_empty(self, store):
        stats = store.stats()
        assert stats.total_count == 0
        assert stats.hot_count == 0
        assert stats.warm_count == 0
        assert stats.cold_count == 0
        assert stats.frozen_count == 0

    def test_stats_with_data(self, store):
        store.store("h1", 1, tier="hot")
        store.store("w1", 2, tier="warm")
        store.store("c1", 3, tier="cold")
        store.store("f1", 4, tier="frozen")

        stats = store.stats()
        assert stats.hot_count == 1
        assert stats.warm_count == 1
        assert stats.cold_count == 1
        assert stats.frozen_count == 1
        assert stats.total_count == 4

    def test_stats_to_dict(self, store):
        store.store("k", "v", tier="hot")
        stats = store.stats()
        d = stats.to_dict()
        assert "hot_count" in d
        assert "total_count" in d


class TestForgetAndClear:
    """Tests for forgetting and clearing memory."""

    def test_forget_removes_from_all_tiers(self, store):
        store.store("key", "value", tier="hot")
        found = store.forget("key")
        assert found is True
        assert store.retrieve("key") is None

    def test_forget_nonexistent(self, store):
        found = store.forget("nonexistent")
        assert found is False

    def test_forget_frozen(self, store):
        store.store("key", "value", tier="frozen")
        found = store.forget("key")
        assert found is True
        assert store.retrieve("key") is None

    def test_clear_tier_hot(self, store):
        store.store("k1", 1, tier="hot")
        store.store("k2", 2, tier="hot")
        store.store("k3", 3, tier="warm")  # Should not be cleared

        cleared = store.clear_tier("hot")
        assert cleared == 2
        assert store.retrieve("k1") is None
        assert store.retrieve("k2") is None
        assert store.retrieve("k3") == 3  # Still in warm

    def test_clear_tier_warm(self, store):
        store.store("k1", 1, tier="warm")
        cleared = store.clear_tier("warm")
        assert cleared == 1

    def test_clear_tier_cold(self, store):
        store.store("k1", 1, tier="cold")
        cleared = store.clear_tier("cold")
        assert cleared == 1

    def test_clear_tier_frozen(self, store):
        store.store("k1", 1, tier="frozen")
        cleared = store.clear_tier("frozen")
        assert cleared == 1
        assert store.retrieve("k1") is None

    def test_clear_invalid_tier_raises(self, store):
        with pytest.raises(ValueError, match="Invalid tier"):
            store.clear_tier("nonexistent")


class TestQuery:
    """Tests for memory querying."""

    def test_query_all(self, store):
        store.store("module_heat", 1, tier="hot")
        store.store("module_cool", 2, tier="warm")
        store.store("other_thing", 3, tier="cold")

        results = store.query("module")
        assert len(results) == 2

    def test_query_specific_tier(self, store):
        store.store("x_key", 1, tier="hot")
        store.store("x_key_warm", 2, tier="warm")

        results = store.query("x_key", tier="hot")
        assert len(results) == 1
        assert results[0]["tier"] == "hot"

    def test_query_case_insensitive(self, store):
        store.store("MODULE_DATA", 1, tier="hot")
        results = store.query("module_data")
        assert len(results) == 1

    def test_query_empty(self, store):
        results = store.query("nonexistent")
        assert results == []


class TestStartupShutdown:
    """Tests for persistence across startup/shutdown cycles."""

    def test_startup_creates_dirs(self, tmp_dir):
        path = os.path.join(tmp_dir, "mem")
        s = MemoryStore(base_path=path)
        s.startup()
        assert os.path.exists(path)
        assert os.path.exists(s._frozen_path)
        s.shutdown()

    def test_warm_persists_across_restart(self, tmp_dir):
        path = os.path.join(tmp_dir, "mem")
        s1 = MemoryStore(base_path=path)
        s1.startup()
        s1.store("persistent_key", {"saved": True}, tier="warm")
        s1.shutdown()

        s2 = MemoryStore(base_path=path)
        s2.startup()
        assert s2.retrieve("persistent_key") == {"saved": True}
        s2.shutdown()

    def test_cold_persists_across_restart(self, tmp_dir):
        path = os.path.join(tmp_dir, "mem")
        s1 = MemoryStore(base_path=path)
        s1.startup()
        s1.store("cold_key", [1, 2, 3], tier="cold")
        s1.shutdown()

        s2 = MemoryStore(base_path=path)
        s2.startup()
        assert s2.retrieve("cold_key") == [1, 2, 3]
        s2.shutdown()

    def test_hot_not_persisted(self, tmp_dir):
        path = os.path.join(tmp_dir, "mem")
        s1 = MemoryStore(base_path=path)
        s1.startup()
        s1.store("hot_key", "ephemeral", tier="hot")
        s1.shutdown()

        s2 = MemoryStore(base_path=path)
        s2.startup()
        assert s2.retrieve("hot_key") is None  # Hot is not persisted
        s2.shutdown()

    def test_frozen_persists_across_restart(self, tmp_dir):
        path = os.path.join(tmp_dir, "mem")
        s1 = MemoryStore(base_path=path)
        s1.startup()
        s1.store("frozen_key", {"ice": True}, tier="frozen")
        s1.shutdown()

        s2 = MemoryStore(base_path=path)
        s2.startup()
        assert s2.retrieve("frozen_key") == {"ice": True}
        s2.shutdown()


# ══════════════════════════════════════════════════════════════════════════════
# ExperienceRecorder Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestExperienceCreation:
    """Tests for Experience data structure."""

    def test_create_experience(self):
        exp = Experience(
            context={"heat_level": "HOT"},
            action={"type": "recompile_language"},
            outcome="success",
            metrics={"speedup": 2.5},
        )
        assert exp.outcome == "success"
        assert exp.metrics["speedup"] == 2.5
        assert exp.timestamp > 0

    def test_experience_tags_from_list(self):
        exp = Experience(tags=["python", "hot"])
        assert isinstance(exp.tags, set)
        assert "python" in exp.tags

    def test_experience_to_dict_roundtrip(self):
        exp = Experience(
            context={"heat": "HOT"},
            action={"type": "fuse"},
            outcome="success",
            metrics={"speedup": 1.5},
            tags={"compute"},
            generation=3,
        )
        d = exp.to_dict()
        restored = Experience.from_dict(d)
        assert restored.context == exp.context
        assert restored.outcome == exp.outcome
        assert restored.metrics["speedup"] == 1.5
        assert restored.generation == 3


class TestExperienceRecording:
    """Tests for recording and retrieving experiences."""

    def test_record_and_count(self, recorder):
        recorder.record_experience(
            context={"heat_level": "HOT"},
            action={"type": "recompile_language"},
            outcome="success",
            generation=1,
        )
        assert recorder.count == 1

    def test_record_returns_experience(self, recorder):
        exp = recorder.record_experience(
            context={"heat_level": "WARM"},
            action={"type": "fuse_pattern"},
            outcome="failure",
            generation=2,
        )
        assert isinstance(exp, Experience)
        assert exp.generation == 2

    def test_record_multiple(self, recorder):
        for i in range(10):
            recorder.record_experience(
                context={"heat_level": "HOT"},
                action={"type": "recompile_language"},
                outcome="success" if i % 2 == 0 else "failure",
                generation=i,
            )
        assert recorder.count == 10

    def test_experiences_property(self, recorder):
        recorder.record_experience(
            context={},
            action={"type": "test"},
            outcome="success",
        )
        exps = recorder.experiences
        assert len(exps) == 1
        assert isinstance(exps[0], Experience)


class TestSimilaritySearch:
    """Tests for case-based similarity search."""

    def test_find_similar_returns_matches(self, recorder):
        recorder.record_experience(
            context={"heat_level": "HOT", "language": "python", "module": "data"},
            action={"type": "recompile_language"},
            outcome="success",
            metrics={"speedup": 3.0},
        )
        recorder.record_experience(
            context={"heat_level": "COOL", "language": "rust"},
            action={"type": "fuse_pattern"},
            outcome="failure",
        )

        similar = recorder.find_similar(
            {"heat_level": "HOT", "language": "python"},
            n=1,
        )
        assert len(similar) == 1
        assert similar[0].context["heat_level"] == "HOT"

    def test_find_similar_empty(self, recorder):
        similar = recorder.find_similar({"heat_level": "HOT"})
        assert similar == []

    def test_find_similar_n_limit(self, recorder):
        for i in range(5):
            recorder.record_experience(
                context={"heat_level": "HOT"},
                action={"type": f"strategy_{i}"},
                outcome="success",
            )

        similar = recorder.find_similar({"heat_level": "HOT"}, n=2)
        assert len(similar) <= 2


class TestRuleGeneralization:
    """Tests for extracting generalized rules from experiences."""

    def test_generalize_produces_rules(self, recorder):
        """With enough similar successful experiences, should produce a rule."""
        for i in range(5):
            recorder.record_experience(
                context={"heat_level": "HOT", "language": "python"},
                action={"type": "recompile_language"},
                outcome="success",
                metrics={"speedup": 3.0},
                tags={"recompile"},
                generation=i,
            )

        rules = recorder.generalize()
        assert len(rules) >= 1
        rule = rules[0]
        assert rule.action == "recompile_language"
        assert rule.confidence > 0.5
        assert rule.evidence_count >= 3

    def test_generalize_insufficient_data(self, recorder):
        """With too few experiences, should return empty."""
        recorder.record_experience(
            context={"heat_level": "HOT"},
            action={"type": "recompile_language"},
            outcome="success",
        )
        rules = recorder.generalize()
        assert rules == []

    def test_generalize_low_confidence_filtered(self, recorder):
        """Rules below confidence threshold should be filtered out."""
        for i in range(3):
            recorder.record_experience(
                context={"heat_level": "WARM"},
                action={"type": "replace_tile"},
                outcome="failure",
                generation=i,
            )

        rules = recorder.generalize()
        # All failures → low confidence → filtered
        assert len(rules) == 0

    def test_generalize_multiple_rules(self, recorder):
        """Different mutation types should produce different rules."""
        for i in range(4):
            recorder.record_experience(
                context={"heat_level": "HOT"},
                action={"type": "recompile_language"},
                outcome="success",
                metrics={"speedup": 3.0},
                generation=i,
            )
        for i in range(4):
            recorder.record_experience(
                context={"heat_level": "HOT"},
                action={"type": "fuse_pattern"},
                outcome="success",
                metrics={"speedup": 1.5},
                generation=i + 4,
            )

        rules = recorder.generalize()
        actions = {r.action for r in rules}
        assert "recompile_language" in actions
        assert "fuse_pattern" in actions


class TestSuccessRate:
    """Tests for success rate calculations."""

    def test_success_rate_basic(self, recorder):
        for _ in range(7):
            recorder.record_experience(
                context={"heat_level": "HOT"},
                action={"type": "recompile_language"},
                outcome="success",
            )
        for _ in range(3):
            recorder.record_experience(
                context={"heat_level": "HOT"},
                action={"type": "recompile_language"},
                outcome="failure",
            )
        rate = recorder.success_rate_for("recompile_language", "HOT")
        assert abs(rate - 0.7) < 0.01

    def test_success_rate_no_data(self, recorder):
        rate = recorder.success_rate_for("unknown", "HOT")
        assert rate == 0.0

    def test_success_rate_pending_excluded(self, recorder):
        recorder.record_experience(
            context={"heat_level": "HOT"},
            action={"type": "test"},
            outcome="pending",
        )
        rate = recorder.success_rate_for("test", "HOT")
        assert rate == 0.0


class TestBestMutation:
    """Tests for best mutation recommendation."""

    def test_best_mutation_for_heat(self, recorder):
        # recompile_language has 80% success at HOT
        for _ in range(8):
            recorder.record_experience(
                context={"heat_level": "HEAT"},
                action={"type": "recompile_language"},
                outcome="success",
            )
        for _ in range(2):
            recorder.record_experience(
                context={"heat_level": "HEAT"},
                action={"type": "recompile_language"},
                outcome="failure",
            )
        # fuse_pattern has 50% success at HEAT
        for _ in range(5):
            recorder.record_experience(
                context={"heat_level": "HEAT"},
                action={"type": "fuse_pattern"},
                outcome="success",
            )
        for _ in range(5):
            recorder.record_experience(
                context={"heat_level": "HEAT"},
                action={"type": "fuse_pattern"},
                outcome="failure",
            )

        best = recorder.best_mutation_for({"heat_level": "HEAT"})
        assert best == "recompile_language"

    def test_best_mutation_no_data(self, recorder):
        best = recorder.best_mutation_for({"heat_level": "UNKNOWN"})
        assert best is None

    def test_best_mutation_no_heat_level(self, recorder):
        best = recorder.best_mutation_for({})
        assert best is None


class TestGeneralizedRule:
    """Tests for GeneralizedRule data structure."""

    def test_success_rate(self):
        rule = GeneralizedRule(
            success_count=7,
            failure_count=3,
        )
        assert abs(rule.success_rate - 0.7) < 0.01

    def test_success_rate_no_evidence(self):
        rule = GeneralizedRule()
        assert rule.success_rate == 0.0

    def test_to_dict_roundtrip(self):
        rule = GeneralizedRule(
            condition={"heat_level": "HOT"},
            action="recompile_language",
            expected_outcome={"avg_speedup": 2.0},
            confidence=0.8,
            evidence_count=10,
            success_count=8,
            failure_count=2,
        )
        d = rule.to_dict()
        restored = GeneralizedRule.from_dict(d)
        assert restored.action == rule.action
        assert restored.confidence == rule.confidence
        assert restored.evidence_count == rule.evidence_count


# ══════════════════════════════════════════════════════════════════════════════
# MutationBandit Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestBanditCreation:
    """Tests for bandit initialization."""

    def test_default_strategies(self, bandit):
        assert bandit.strategy_count == 5

    def test_custom_strategies(self):
        b = MutationBandit(strategies=["a", "b", "c"], seed=1)
        assert b.strategy_count == 3

    def test_laplace_prior(self, bandit):
        """All strategies should start with Laplace prior (1, 1)."""
        for stats in bandit.all_stats().values():
            assert stats.successes == 1
            assert stats.failures == 1


class TestBanditSelection:
    """Tests for Thompson Sampling selection."""

    def test_select_returns_valid_strategy(self, bandit):
        for _ in range(20):
            choice = bandit.select()
            assert choice in MutationBandit.STRATEGIES

    def test_select_exploit(self, bandit):
        """Exploit should always return the best strategy."""
        bandit.update("recompile_language", success=True)
        bandit.update("recompile_language", success=True)
        bandit.update("recompile_language", success=True)
        bandit.update("fuse_pattern", success=False)
        bandit.update("fuse_pattern", success=False)

        best = bandit.select_exploit()
        assert best == "recompile_language"

    def test_bandit_repr(self, bandit):
        r = repr(bandit)
        assert "MutationBandit" in r
        assert "strategies=5" in r


class TestBanditUpdate:
    """Tests for bandit updates and convergence."""

    def test_update_success(self, bandit):
        bandit.update("recompile_language", success=True)
        stats = bandit.get_stats("recompile_language")
        assert stats.successes == 2  # 1 prior + 1 actual
        assert stats.failures == 1   # 1 prior

    def test_update_failure(self, bandit):
        bandit.update("recompile_language", success=False)
        stats = bandit.get_stats("recompile_language")
        assert stats.successes == 1   # 1 prior
        assert stats.failures == 2    # 1 prior + 1 actual

    def test_update_unknown_strategy(self, bandit):
        bandit.update("new_strategy", success=True)
        stats = bandit.get_stats("new_strategy")
        assert stats is not None
        assert stats.successes == 2

    def test_reset(self, bandit):
        bandit.update("recompile_language", success=True)
        bandit.update("recompile_language", success=True)
        bandit.reset()
        stats = bandit.get_stats("recompile_language")
        assert stats.successes == 1
        assert stats.failures == 1

    def test_convergence_after_many_successes(self, bandit):
        """After many successes, best_strategy should stabilize."""
        for _ in range(50):
            bandit.update("recompile_language", success=True)
        for _ in range(10):
            bandit.update("fuse_pattern", success=False)

        best = bandit.best_strategy()
        assert best == "recompile_language"


class TestBanditDistribution:
    """Tests for distribution analysis."""

    def test_get_distribution(self, bandit):
        dist = bandit.get_distribution()
        assert len(dist) == 5
        for name, (mean, std) in dist.items():
            assert 0.0 <= mean <= 1.0
            assert std >= 0.0

    def test_best_strategy(self, bandit):
        bandit.update("fuse_pattern", success=True)
        bandit.update("fuse_pattern", success=True)
        bandit.update("recompile_language", success=False)
        assert bandit.best_strategy() == "fuse_pattern"

    def test_worst_strategy(self, bandit):
        bandit.update("fuse_pattern", success=True)
        bandit.update("fuse_pattern", success=True)
        bandit.update("recompile_language", success=False)
        bandit.update("recompile_language", success=False)
        assert bandit.worst_strategy() == "recompile_language"

    def test_exploration_rate(self, bandit):
        """Uniform prior → high exploration."""
        rate = bandit.exploration_rate()
        assert 0.0 <= rate <= 1.0

    def test_exploration_rate_decreases_with_exploitation(self, bandit):
        """After many updates favoring one strategy, exploration should drop."""
        initial_rate = bandit.exploration_rate()

        for _ in range(100):
            bandit.update("recompile_language", success=True)
            bandit.update("fuse_pattern", success=False)
            bandit.update("replace_tile", success=False)
            bandit.update("merge_tiles", success=False)
            bandit.update("inline_optimization", success=False)

        later_rate = bandit.exploration_rate()
        assert later_rate < initial_rate

    def test_total_trials(self, bandit):
        assert bandit.total_trials == 0
        bandit.update("a", True)
        bandit.update("b", False)
        assert bandit.total_trials == 2

    def test_regret(self, bandit):
        regret = bandit.regret()
        assert regret >= 0.0


class TestStrategyStats:
    """Tests for StrategyStats data structure."""

    def test_properties(self):
        stats = StrategyStats(name="test", successes=7, failures=3)
        assert stats.total == 10
        assert abs(stats.empirical_rate - 0.7) < 0.01
        assert stats.variance > 0.0
        assert stats.std > 0.0

    def test_sample_range(self):
        stats = StrategyStats(name="test", successes=9, failures=1)
        samples = [stats.sample() for _ in range(100)]
        assert all(0.0 <= s <= 1.0 for s in samples)

    def test_to_dict(self):
        stats = StrategyStats(name="test", successes=5, failures=3)
        d = stats.to_dict()
        assert d["name"] == "test"
        assert d["successes"] == 5
        assert "empirical_rate" in d


# ══════════════════════════════════════════════════════════════════════════════
# LearningRateAdapter Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestLearningRateInit:
    """Tests for adapter initialization."""

    def test_default_values(self, adapter):
        assert adapter.current_rate == 0.3
        assert adapter.base_rate == 0.3

    def test_custom_base_rate(self):
        a = LearningRateAdapter(base_rate=0.5)
        assert a.current_rate == 0.5
        assert a.base_rate == 0.5

    def test_rate_clamped(self):
        a = LearningRateAdapter(base_rate=2.0)
        assert a.current_rate == LearningRateAdapter.MAX_RATE

    def test_repr(self, adapter):
        r = repr(adapter)
        assert "LearningRateAdapter" in r


class TestLearningRateUpdate:
    """Tests for exploration rate adaptation."""

    def test_steady_improvement_decreases_rate(self, adapter):
        """Meaningful improvement → exploit more (lower rate)."""
        adapter.current_rate = 0.6  # Set above base so decay is measurable
        initial = adapter.current_rate
        new_rate = adapter.update(0.05)  # 5% improvement (between thresholds)
        assert new_rate < initial

    def test_spike_increases_rate(self, adapter):
        """Big improvement → spike exploration."""
        initial = adapter.current_rate
        new_rate = adapter.update(0.15)  # 15% improvement (> spike threshold)
        assert new_rate > initial
        assert adapter.spike_detected is True

    def test_plateau_increases_rate(self, adapter):
        """No improvement → explore more (increase rate)."""
        adapter.current_rate = 0.3  # Start from known value
        new_rate = adapter.update(0.001)  # < 1% improvement
        assert new_rate > 0.3
        assert adapter.plateau_detected is True

    def test_rate_never_below_min(self):
        a = LearningRateAdapter(base_rate=0.05)
        # Keep sending plateaus
        for _ in range(100):
            a.update(0.0)
        assert a.current_rate >= LearningRateAdapter.MIN_RATE

    def test_rate_never_above_max(self):
        a = LearningRateAdapter()
        # Keep sending spikes
        for _ in range(100):
            a.update(0.5)
        assert a.current_rate <= LearningRateAdapter.MAX_RATE


class TestPlateauDetection:
    """Tests for plateau detection."""

    def test_consecutive_plateaus(self, adapter):
        for _ in range(3):
            adapter.update(0.0)
        assert adapter.generations_no_improvement == 3

    def test_improvement_resets_counter(self, adapter):
        adapter.update(0.0)
        adapter.update(0.0)
        adapter.update(0.05)  # Meaningful improvement
        assert adapter.generations_no_improvement == 0

    def test_spike_resets_counter(self, adapter):
        adapter.update(0.0)
        adapter.update(0.15)  # Spike
        assert adapter.generations_no_improvement == 0


class TestConvergenceDetection:
    """Tests for convergence (should_stop)."""

    def test_should_stop_false_early(self, adapter):
        adapter.update(0.05)
        assert adapter.should_stop() is False

    def test_should_stop_after_plateau(self, adapter):
        for _ in range(5):
            adapter.update(0.0)
        assert adapter.should_stop() is True
        assert adapter.converged is True

    def test_should_stop_custom_threshold(self, adapter):
        for _ in range(3):
            adapter.update(0.0)
        assert adapter.should_stop(max_generations_no_improvement=3) is True
        assert adapter.should_stop(max_generations_no_improvement=5) is False


class TestLearningRateAnalysis:
    """Tests for learning rate analysis methods."""

    def test_recent_improvement(self, adapter):
        for imp in [0.1, 0.05, 0.08]:
            adapter.update(imp)
        recent = adapter.recent_improvement(n=3)
        expected = (0.1 + 0.05 + 0.08) / 3
        assert abs(recent - expected) < 0.001

    def test_recent_improvement_empty(self, adapter):
        assert adapter.recent_improvement() == 0.0

    def test_improvement_trend_insufficient_data(self, adapter):
        assert adapter.improvement_trend() == "insufficient_data"

    def test_improvement_trend_improving(self, adapter):
        # First half: small improvements; Second half: larger
        for _ in range(5):
            adapter.update(0.01)
        for _ in range(5):
            adapter.update(0.08)
        assert adapter.improvement_trend() == "improving"

    def test_improvement_trend_declining(self, adapter):
        for _ in range(5):
            adapter.update(0.08)
        for _ in range(5):
            adapter.update(0.01)
        assert adapter.improvement_trend() == "declining"

    def test_improvement_trend_flat(self, adapter):
        for _ in range(10):
            adapter.update(0.05)
        assert adapter.improvement_trend() == "flat"


class TestLearningRateReset:
    """Tests for adapter reset."""

    def test_reset(self, adapter):
        adapter.update(0.05)
        adapter.update(0.15)
        adapter.reset()
        assert adapter.current_rate == adapter.base_rate
        assert adapter.total_updates == 0
        assert adapter.history_len == 0
        assert adapter.generations_no_improvement == 0
        assert adapter.converged is False


class TestLearningState:
    """Tests for LearningState snapshot."""

    def test_get_state(self, adapter):
        adapter.update(0.05)
        state = adapter.get_state()
        assert isinstance(state, LearningState)
        assert state.current_rate > 0
        assert len(state.improvement_history) == 1

    def test_state_to_dict(self, adapter):
        adapter.update(0.05)
        state = adapter.get_state()
        d = state.to_dict()
        assert "current_rate" in d
        assert "improvement_history" in d
        assert "total_updates" in d
