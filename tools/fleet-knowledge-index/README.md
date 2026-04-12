# Fleet Knowledge Index

**Version:** 2.0.0 | **Purpose:** Searchable index of knowledge domains across all FLUX fleet repositories

---

## Overview

The Fleet Knowledge Index is a tool that scans all fleet repositories (800+ repos across SuperInstance and Lucineer orgs) and builds a searchable inverted index of knowledge domains. It answers the question: *"What does the fleet know, and where does that knowledge live?"*

This tool complements the `fleet-context-inference` tool:
- **fleet-context-inference** profiles *individual agents* — their capabilities, context needs, and expertise
- **fleet-knowledge-index** indexes the *collective knowledge* across all repos — what domains exist, where they live, and how they connect

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Fleet Repos (800+)                        │
│  SuperInstance/*  Lucineer/*  (local or GitHub API)         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  index_builder.py                            │
│  ┌─────────────┐  ┌──────────────────┐  ┌────────────────┐ │
│  │ RepoScanner │→ │ ArtifactExtractor │→ │ DomainClassifier│ │
│  └─────────────┘  └──────────────────┘  └───────┬────────┘ │
└────────────────────────────────────────────────┼────────────┘
                                                 │
                                                 ▼
┌─────────────────────────────────────────────────────────────┐
│              Fleet Knowledge Index (JSON)                    │
│  ┌───────────┐ ┌────────────┐ ┌────────────┐ ┌───────────┐ │
│  │ Inverted  │ │  Domain    │ │ Language   │ │    Org    │ │
│  │  Index    │ │  Index     │ │  Index     │ │  Index    │ │
│  └───────────┘ └────────────┘ └────────────┘ └───────────┘ │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  search_engine.py                            │
│  TF-IDF scoring · Fuzzy matching · Multi-filter search      │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.8+ (no external dependencies — everything is stdlib)
- (Optional) GitHub token for API-based scanning (`GITHUB_TOKEN` env var)

### Building the Index

```bash
# From local repositories
python index_builder.py build --repos-dir /path/to/fleet/repos --output-dir ./index_output

# From GitHub organizations
python index_builder.py build \
  --github-orgs SuperInstance,Lucineer \
  --github-token $GITHUB_TOKEN \
  --clone-dir /tmp/fleet-clones \
  --output-dir ./index_output

# Incremental update (only scans changed repos since last run)
python index_builder.py build --repos-dir /path/to/repos --incremental
```

### Searching the Index

```bash
# Basic full-text search
python search_engine.py search "CUDA kernel optimization"

# Filter by domain
python search_engine.py search "memory allocator" --domain runtimes

# Filter by language
python search_engine.py search "parser combinator" --language rust

# Filter by organization
python search_engine.py search "agent dispatch protocol" --org SuperInstance

# Filter by artifact type (code, doc, test, readme, config)
python search_engine.py search "test suite" --type test

# JSON output for programmatic use
python search_engine.py search "wasm runtime" --json

# Get query suggestions (fuzzy corrections, domain hints)
python search_engine.py suggest "how does the fleet handle agent dispatch?"

# View index statistics
python search_engine.py stats

# List all indexed domains
python search_engine.py list-domains

# List all indexed languages
python search_engine.py list-languages
```

---

## Knowledge Domain Taxonomy

The classifier supports **20+ knowledge domains** specific to the FLUX fleet:

| Domain | Category | Description |
|--------|----------|-------------|
| `bytecode_vm` | Systems | Virtual machines, bytecode interpreters, opcodes, JIT |
| `cuda` | Systems | CUDA programming, GPU kernels, tensor operations |
| `compilers` | Systems | Compiler construction, lexing, parsing, LLVM, SSA |
| `runtimes` | Systems | Language runtimes, GC, memory management, sandboxing |
| `fleet_protocol` | Infrastructure | Fleet communication, agent orchestration, task dispatch |
| `networking` | Infrastructure | Network protocols, sockets, HTTP, load balancing |
| `security` | Security | Cryptography, authentication, vulnerability scanning |
| `cryptography` | Security | ZK proofs, homomorphic encryption, post-quantum crypto |
| `testing` | Software | Unit tests, fuzzing, property testing, coverage |
| `observability` | Operations | Logging, metrics, tracing, OpenTelemetry |
| `devops` | Operations | CI/CD, Docker, Kubernetes, Terraform |
| `ml_ai` | Research | ML/DL, neural networks, LLMs, inference |
| `data_processing` | Software | ETL, stream processing, databases, data formats |
| `web_development` | Software | Frontend/backend, REST APIs, web frameworks |
| `systems_programming` | Systems | OS internals, concurrency, async, zero-copy |
| `formal_methods` | Research | Formal verification, model checking, theorem provers |
| `database` | Systems | Query engines, storage engines, transactions |
| `distributed_systems` | Infrastructure | Consensus, replication, CRDTs, partition tolerance |
| `cli_tools` | Software | CLI tools, argument parsing, terminal UI |
| `api_design` | Software | REST design, OpenAPI, GraphQL, versioning |
| `embedded` | Systems | Microcontrollers, firmware, RTOS |
| `documentation` | Software | Technical writing, specs, ADRs |
| `build_systems` | Infrastructure | Cargo, npm, CMake, reproducible builds |

### Domain Categories

- **Systems** — Low-level programming, VMs, compilers, databases
- **Software** — Application development, testing, documentation
- **Infrastructure** — Distributed systems, networking, build systems
- **Security** — Cryptography, authentication, secure coding
- **Research** — Formal methods, ML/AI
- **Operations** — DevOps, observability, monitoring

---

## Module Reference

### `domain_classifier.py` — Knowledge Domain Classifier

Keyword-based classifier with confidence scoring. No ML dependencies.

```python
from domain_classifier import DomainClassifier

clf = DomainClassifier()

# Classify any text
result = clf.classify_text("This implements a CUDA kernel for matrix multiply")
print(result.primary_domain)  # "cuda"
print(result.top_domains(5))  # [("cuda", 1.0), ("ml_ai", 0.6), ...]

# Classify a file
result = clf.classify_file("path/to/kernel.cu")

# Bulk classify a directory
results = clf.classify_directory("/path/to/repo", extensions=[".rs", ".py"])

# Get domain summary
summary = clf.get_domain_summary(results)

# Suggest domains for a search query
suggestions = clf.suggest_domains_for_query("how does the fleet handle agent dispatch?")
```

### `index_builder.py` — Index Construction

Scans repositories, extracts artifacts, classifies domains, builds inverted index.

```python
from index_builder import IndexBuilder

builder = IndexBuilder(output_dir="./index_output")

# Build from local repos
index = builder.build_from_local_repos("/path/to/repos", incremental=True)

# Build from GitHub
index = builder.build_from_github(
    orgs=["SuperInstance", "Lucineer"],
    github_token="ghp_...",
    clone_dir="/tmp/clones",
)

# Save index and summary
builder.save_index()
builder.generate_summary_markdown()

# Load existing index
builder.load_index()
```

**Artifact extraction** from each file:
- README files → summary, project description
- Documentation → section titles, headings, key paragraphs
- Source code → module/class/function names, signatures
- Test files → test descriptions, fixture names, test module names
- Config files → tool names, dependency names

### `search_engine.py` — Full-Text Search

Ranked search with TF-IDF scoring and fuzzy matching.

```python
from search_engine import FleetSearchEngine

engine = FleetSearchEngine()
engine.load_index()

# Simple search
results = engine.search_simple("CUDA kernel optimization")

# Advanced search with filters
from search_engine import SearchQuery
query = engine.parse_query(
    "memory allocator",
    domains=["runtimes", "systems_programming"],
    languages=["rust", "c"],
    limit=10,
)
results = engine.search(query)

for result in results:
    print(f"#{result.rank} [{result.score:.4f}] {result.repo}/{result.file}")
    print(f"  Title: {result.title}")
    print(f"  Domains: {result.domains}")
    print(f"  {result.excerpt[:200]}")
```

**Search features:**
- **TF-IDF scoring** with BM25-style term saturation (k1=1.5, b=0.75)
- **Fuzzy matching** using combined Levenshtein + SequenceMatcher similarity
- **Domain-aware query expansion** — suggests relevant domain keywords
- **Filters**: domain, language, org, artifact type, date range
- **Pagination**: limit/offset for large result sets

---

## Index File Structure

The generated `fleet_knowledge_index.json` contains:

```json
{
  "index_version": "2.0.0",
  "build_timestamp": "2025-01-15T12:00:00Z",
  "total_repos": 800,
  "total_artifacts": 45000,
  "inverted_index": {
    "cuda": [
      {"repo": "flux-gpu-kernels", "file": "src/matmul.cu", "title": "matmul", ...}
    ]
  },
  "domain_index": {
    "cuda": [
      {"repo": "flux-gpu-kernels", "file": "src/matmul.cu", "score": 1.0, ...}
    ]
  },
  "language_index": { "rust": ["repo1", "repo2"], "python": ["repo3"] },
  "org_index": { "SuperInstance": ["repo1", "repo2"] },
  "domain_statistics": { ... }
}
```

---

## Integration with fleet-context-inference

Both tools work together to provide fleet-wide intelligence:

1. **Use `fleet-knowledge-index`** to discover which repos contain relevant knowledge for a task
2. **Use `fleet-context-inference`** to profile which agents are best suited for that task
3. **Combine** to route agents to the right repos with the right context

Example workflow:
```bash
# Step 1: Find knowledge about CUDA optimization
python search_engine.py search "CUDA kernel optimization" --domain cuda --json > results.json

# Step 2: Identify the best agent for the task
python ../fleet-context-inference/infer_context.py --capability cuda --json

# Step 3: The agent receives the relevant repo context from Step 1
```

---

## Incremental Updates

The index builder tracks scan state in `scan_state.json`:

```json
{
  "repo_timestamps": {
    "/path/to/repo1": "2025-01-15T12:00:00Z",
    "/path/to/repo2": "2025-01-15T12:05:00Z"
  },
  "last_full_scan": "2025-01-15T12:30:00Z"
}
```

On incremental runs, only repos with new commits since their last scan timestamp are re-scanned. Use `--incremental` flag:

```bash
python index_builder.py build --repos-dir /path/to/repos --incremental --state-file ./state.json
```

---

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--output-dir` | `./index_output` | Directory for index files |
| `--state-file` | `./scan_state.json` | Incremental scan state |
| `--max-files` | 500 (per repo) | Max files to scan per repo |
| `--max-repos` | unlimited | Max repos to scan |
| `MAX_FILE_SIZE` | 10MB | Skip files larger than this |
| Fuzzy threshold | 0.65 | Minimum similarity for fuzzy matches |
| TF-IDF k1 | 1.5 | BM25 term frequency saturation |
| TF-IDF b | 0.75 | BM25 length normalization |

---

## Output Files

| File | Description |
|------|-------------|
| `index_output/fleet_knowledge_index.json` | Complete searchable index |
| `index_output/fleet_knowledge_summary.md` | Human-readable markdown report |
| `scan_state.json` | Incremental scan state |

---

## License

Internal tool for FLUX fleet operations. Oracle1-approved.
