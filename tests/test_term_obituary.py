"""Tests for Term Obituary — graceful vocabulary death."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from flux.open_interp.term_obituary import (
    Obituary, TermCemetery, DeathReason
)


class TestObituary:
    def test_create(self):
        obit = Obituary(term="old_compute", reason=DeathReason.SUPERSEDED, replacement="compute")
        assert obit.term == "old_compute"
        assert obit.has_replacement
        assert obit.replacement == "compute"
    
    def test_no_replacement(self):
        obit = Obituary(term="obsolete_thing", reason=DeathReason.OBSOLETE)
        assert not obit.has_replacement
    
    def test_serialization(self):
        obit = Obituary(
            term="old_term",
            reason=DeathReason.AMBIGUOUS,
            replacement="new_term",
            migration_notes="old_term was too vague",
            old_pattern="old $x",
        )
        d = obit.to_dict()
        obit2 = Obituary.from_dict(d)
        assert obit2.term == "old_term"
        assert obit2.reason == DeathReason.AMBIGUOUS
        assert obit2.replacement == "new_term"
        assert obit2.old_pattern == "old $x"


class TestTermCemetery:
    def setup_method(self):
        self.cemetery = TermCemetery()
    
    def test_bury_and_exhume(self):
        obit = Obituary(term="old", reason=DeathReason.SUPERSEDED, replacement="new")
        self.cemetery.bury(obit)
        assert self.cemetery.is_dead("old")
        assert not self.cemetery.is_dead("new")
        exhumed = self.cemetery.exhume("old")
        assert exhumed.replacement == "new"
    
    def test_migration_map(self):
        self.cemetery.bury(Obituary(term="a", reason=DeathReason.SUPERSEDED, replacement="b"))
        self.cemetery.bury(Obituary(term="c", reason=DeathReason.OBSOLETE))
        mmap = self.cemetery.migration_map()
        assert mmap == {"a": "b"}
        assert "c" not in mmap
    
    def test_rewrite_guide(self):
        self.cemetery.bury(Obituary(term="old_compute", reason=DeathReason.SUPERSEDED, replacement="compute"))
        self.cemetery.bury(Obituary(term="old_factorial", reason=DeathReason.MERGED, replacement="factorial"))
        text = "use old_compute and old_factorial"
        rewritten = self.cemetery.rewrite_guide(text)
        assert "compute" in rewritten
        assert "factorial" in rewritten
        assert "old_" not in rewritten
    
    def test_stats(self):
        self.cemetery.bury(Obituary(term="a", reason=DeathReason.SUPERSEDED, replacement="b"))
        self.cemetery.bury(Obituary(term="c", reason=DeathReason.OBSOLETE))
        self.cemetery.bury(Obituary(term="d", reason=DeathReason.AMBIGUOUS, replacement="e"))
        stats = self.cemetery.stats()
        assert stats["total_dead"] == 3
        assert stats["with_replacement"] == 2
        assert stats["orphaned"] == 1
    
    def test_save_load(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode='w') as f:
            path = f.name
        
        self.cemetery.bury(Obituary(term="old", reason=DeathReason.SUPERSEDED, replacement="new"))
        self.cemetery.save(path)
        
        cemetery2 = TermCemetery(path=path)
        assert cemetery2.is_dead("old")
        assert cemetery2.get_replacement("old") == "new"
        
        os.unlink(path)
    
    def test_migration_report(self):
        self.cemetery.bury(Obituary(term="deprecated_op", reason=DeathReason.INCORRECT, 
                                    replacement="correct_op", migration_notes="Was off by 1"))
        report = self.cemetery.migration_report()
        assert "deprecated_op" in report
        assert "correct_op" in report
