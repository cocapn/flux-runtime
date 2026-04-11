"""Tests for Edge Profile — I2I collaboration test case."""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from flux.open_interp.edge_profile import EdgeProfiler, EdgeConstraints
from flux.open_interp.vocabulary import Vocabulary


class TestEdgeConstraints:
    def test_jetson_orin(self):
        c = EdgeConstraints.jetson_orin()
        assert c.arch == "arm64"
        assert c.has_gpu is True
        assert c.max_ram_mb == 512
        assert c.max_vocab == 50
    
    def test_embedded_minimal(self):
        c = EdgeConstraints.embedded_minimal()
        assert c.no_loops is True
        assert c.no_float is True
        assert c.max_vocab == 20
    
    def test_custom(self):
        c = EdgeConstraints(max_ram_mb=256, max_vocab=30, arch="riscv")
        assert c.arch == "riscv"
        assert c.max_vocab == 30


class TestEdgeProfiler:
    def _make_vocab(self):
        vocab = Vocabulary()
        vocab.entries = []
        for i, (name, tags) in enumerate([
            ("compute", ["essential", "core"]),
            ("store", ["essential", "core"]),
            ("halt", ["essential", "core"]),
            ("add", ["math", "arithmetic"]),
            ("mul", ["math", "arithmetic"]),
            ("sub", ["math", "arithmetic"]),
            ("loop_n", ["loops", "core"]),
            ("loop_while", ["loops", "core"]),
            ("maritime_nav", ["maritime", "domain"]),
            ("predict_catch", ["maritime", "domain"]),
        ]):
            from flux.open_interp.vocabulary import VocabEntry
            vocab.entries.append(VocabEntry(
                name=name,
                pattern=f"pattern for {name} $x",
                bytecode_template=f"OP_{name.upper()}",
                tags=tags,
            ))
        return vocab
    
    def test_profile_fits_budget(self):
        profiler = EdgeProfiler(EdgeConstraints(max_vocab=5))
        profile = profiler.profile(self._make_vocab())
        assert profile["selected_count"] <= 5
    
    def test_essential_first(self):
        profiler = EdgeProfiler(EdgeConstraints(max_vocab=3))
        profile = profiler.profile(self._make_vocab())
        assert "compute" in profile["selected"]
        assert "store" in profile["selected"]
    
    def test_jetson_profile(self):
        profiler = EdgeProfiler(EdgeConstraints.jetson_orin())
        profile = profiler.profile(self._make_vocab())
        assert profile["selected_count"] <= 50
        assert profile["constraints"]["arch"] == "arm64"
        assert profile["constraints"]["has_gpu"] is True
    
    def test_generate_standalone(self):
        profiler = EdgeProfiler(EdgeConstraints(max_vocab=5))
        vocab = self._make_vocab()
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode='w') as f:
            path = f.name
        profiler.generate_standalone(vocab, path)
        content = open(path).read()
        assert "VOCAB" in content
        assert "lookup" in content
        os.unlink(path)


class TestRealVocabEdge:
    def test_prune_real_vocab_to_edge(self):
        """Test pruning real vocabulary to Jetson constraints."""
        vocab = Vocabulary()
        vocab.load_folder("vocabularies/core")
        profiler = EdgeProfiler(EdgeConstraints.jetson_orin())
        profile = profiler.profile(vocab)
        print(f"  Total: {profile['total']}, Selected: {profile['selected_count']}")
        print(f"  RAM estimate: {profile['estimated_ram_kb']}KB")
        print(f"  Fits: {profile['fits']}")
        assert profile["selected_count"] <= 50
