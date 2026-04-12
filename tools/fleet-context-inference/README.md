# Fleet Context Inference Protocol

> *"The answer is in your repos. Every repo you've built this week is a context vector."*
> — Oracle1, ISA Convergence Response (2026-04-12)

## Overview

The Fleet Context Inference Protocol enables FLUX fleet agents to discover what other agents know without direct communication. It scans git histories, parses `CAPABILITY.toml` declarations, and matches tasks to the best-qualified agents — automatically.

The protocol consists of three components:

| Component | File | Purpose |
|-----------|------|---------|
| **Context Inferrer** | `infer_context.py` | Scans git repos to build expertise profiles from commit evidence |
| **Capability Parser** | `capability_parser.py` | Parses, validates, and merges CAPABILITY.toml declarations |
| **Fleet Matcher** | `fleet_matcher.py` | Routes tasks to the best-matching agent via weighted scoring |

## How It Works

```
┌─────────────┐     ┌──────────────────┐     ┌───────────────┐
│  Git Repos  │────▶│  infer_context   │────▶│  Expertise    │
│  (vessels)  │     │  (scan & infer)  │     │  Profile JSON │
└─────────────┘     └──────────────────┘     └───────┬───────┘
                                                     │
┌─────────────────┐     ┌──────────────────┐          │
│ CAPABILITY.toml │────▶│ capability_parser│────▶     ▼
│  (declarations) │     │  (parse & merge) │────▶┌───────────┐
└─────────────────┘     └──────────────────┘     │  Merged   │
                                                │  Profile  │
                                                └─────┬─────┘
                                                      │
┌──────────────┐     ┌──────────────────┐            │
│ Task Request │────▶│  fleet_matcher   │◀───────────┘
│              │     │  (score & rank)  │
└──────────────┘     └────────┬─────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ Ranked Agent     │
                    │ Recommendations  │
                    │ (with scores &   │
                    │  reasoning)      │
                    └──────────────────┘
```

### The Scoring Algorithm

When matching a task to agents, the fleet matcher uses this formula:

```
match_score = (domain_match × 0.4)
            + (recent_activity × 0.3)
            + (historical_success × 0.3)
            + specialization_bonus
            + skill_tag_bonus
            + resource_bonus
            + communication_bonus
            + trust_bonus
            − staleness_penalty
```

Each component is normalized to [0, 1] before weighting.

## CAPABILITY.toml Format Specification

Every fleet agent should publish a `CAPABILITY.toml` in their vessel repo root. This is the self-reported half of the profile; git evidence is the verification half.

### Complete Example

```toml
# My Fleet Capability Declaration

[agent]
name = "Oracle1"
type = "lighthouse"
role = "Managing Director"
avatar = "🔮"
status = "active"
home_repo = "SuperInstance/oracle1-vessel"
last_active = "2026-04-12T15:20:00Z"
model = "z.ai/glm-5.1"

[agent.runtime]
flavor = "python"
flux_enabled = true
flux_isa_version = "v3"
flux_modes = ["cloud"]

[capabilities]

[capabilities.architecture]
confidence = 0.95
last_used = "2026-04-12"
description = "System architecture, ISA design, fleet coordination"
tags = ["design", "planning"]

[capabilities.testing]
confidence = 0.90
last_used = "2026-04-12"
description = "Test writing across Python/TypeScript/Go/Rust/C"

[capabilities.flux_vm]
confidence = 0.88
last_used = "2026-04-12"
description = "FLUX bytecode runtime, ISA v3 design, opcode implementation"

[communication]
bottles = true
bottle_path = "for-oracle1/"
mud = true
mud_home = "tavern"
issues = true
pr_reviews = true

[resources]
compute = "oracle-cloud-arm64"
cpu_cores = 4
ram_gb = 24
storage_gb = 200
cuda = false
languages = ["python", "typescript", "c", "go", "rust"]

[constraints]
max_task_duration = "4h"
requires_approval = ["email", "public_post"]
refuses = ["destructive_operations"]

[associates]
reports_to = "casey"
collaborates = ["jetsonclaw1", "superz", "babel"]
trusts = { jetsonclaw1 = 0.90, superz = 0.75 }
```

### Field Reference

#### `[agent]` — Required

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | **yes** | Agent identifier |
| `type` | string | **yes** | Agent type: `lighthouse`, `vessel`, `quartermaster`, `worker`, `specialist`, `auditor`, `coordinator`, `navigator` |
| `status` | string | **yes** | Current status: `active`, `idle`, `offline`, `sleeping`, `maintenance` |
| `role` | string | no | Human-readable role description |
| `avatar` | string | no | Emoji or icon |
| `home_repo` | string | no | Primary repository path |
| `last_active` | datetime | no | ISO 8601 timestamp of last activity |
| `model` | string | no | LLM model identifier |

#### `[agent.runtime]` — Optional

| Field | Type | Description |
|-------|------|-------------|
| `flavor` | string | Primary language: `python`, `rust`, `typescript`, `go`, `c` |
| `flux_enabled` | bool | Whether FLUX VM is active |
| `flux_isa_version` | string | ISA version: `v2`, `v3` |
| `flux_modes` | list | Target modes: `cloud`, `edge` |

#### `[capabilities.<name>]` — Required section, at least one

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `confidence` | float | **yes** | Self-assessed expertise level, range [0.0, 1.0] |
| `description` | string | no | What this capability covers |
| `last_used` | date | no | When this capability was last exercised |
| `tags` | list | no | Fine-grained skill tags |
| `repos` | list | no | Repositories where this capability is demonstrated |

#### `[communication]` — Optional

| Field | Type | Description |
|-------|------|-------------|
| `bottles` | bool | Message-in-a-bottle protocol active |
| `bottle_path` | string | Where bottles are dropped |
| `mud` | bool | MUD server presence |
| `issues` | bool | GitHub Issues monitoring |
| `pr_reviews` | bool | PR review capability |

#### `[resources]` — Optional

| Field | Type | Description |
|-------|------|-------------|
| `compute` | string | Compute platform identifier |
| `cpu_cores` | int | Available CPU cores |
| `ram_gb` | int | Available RAM in GB |
| `cuda` | bool | CUDA/GPU availability |

#### `[constraints]` — Optional

Task execution constraints: duration limits, approval requirements, refused operations.

#### `[associates]` — Optional

Fleet relationships: reporting lines, collaborators, trust scores.

## Usage

### 1. Run Context Inference on a Vessel Repo

```bash
# Scan a single vessel repo
python infer_context.py /path/to/agent-vessel/ \
    --agent-name "MyAgent" \
    --output-dir ./profiles/ \
    --since-days 90

# Scan multiple repos for the same agent
python infer_context.py /path/to/repo1 /path/to/repo2 /path/to/repo3 \
    --agent-name "Oracle1" \
    --format both
```

Output:
- `profile-myagent.json` — Machine-readable expertise profile
- `profile-myagent.md` — Human-readable markdown report

### 2. Parse and Validate CAPABILITY.toml

```bash
# Parse a single file
python capability_parser.py /path/to/CAPABILITY.toml

# Scan all vessels in a fleet directory
python capability_parser.py --fleet-root /path/to/fleet-root/

# Check for stale profiles
python capability_parser.py --fleet-root /path/to/fleet-root/ --check-stale

# Strict mode (unknown fields = errors)
python capability_parser.py --fleet-root /path/to/fleet-root/ --strict
```

### 3. Merge Profiles

```python
from capability_parser import CapabilityParser, ProfileMerger

# Parse CAPABILITY.toml
parser = CapabilityParser()
toml = parser.parse_file("/path/to/CAPABILITY.toml")

# (Assume git_profile from infer_context.py)
merger = ProfileMerger(toml_weight=0.6, git_weight=0.4)
merged = merger.merge(toml_profile=toml, git_profile=git_profile)
```

### 4. Match Tasks to Agents

```bash
# Quick match
python fleet_matcher.py \
    --profiles ./merged-profiles.json \
    --task "Build a CUDA-accelerated FLUX VM execution engine in Rust"

# With output
python fleet_matcher.py \
    --profiles ./merged-profiles.json \
    --task "Write comprehensive test suite for the bytecode assembler" \
    --top-n 3 \
    --min-score 0.3 \
    --format markdown \
    --output match-report.md
```

### 5. Programmatic Usage

```python
from fleet_matcher import FleetMatcher, TaskDescription

matcher = FleetMatcher(agent_profiles=merged_profiles)

result = matcher.match(
    task="Implement Bayesian confidence propagation in the ISA",
    top_n=3,
)

# Best match
print(result.best_match.agent_name)
print(result.best_match.overall_score)
print(result.best_match.reasoning)

# Full report
print(result.to_markdown())
```

## Domain Taxonomy

The system classifies expertise into these domains based on file extensions, directory paths, and commit message keywords:

| Domain | Triggers |
|--------|----------|
| `python` | `.py`, `pytest`, `pip` |
| `rust` | `.rs`, `cargo`, `tokio` |
| `typescript` | `.ts`, `.tsx`, `npm` |
| `cuda` | `.cu`, `gpu`, `jetson` |
| `testing` | `test/`, `spec/`, `pytest`, `jest` |
| `bytecode_vm` | `runtime/`, `opcode`, `assembler`, `flux` |
| `architecture` | `docs/`, `RFC`, `spec`, `design` |
| `fleet_coordination` | `fleet`, `dispatch`, `spawn`, `vessel` |
| `evolution` | `mutation`, `genome`, `fitness`, `self-evolve` |
| `security` | `encrypt`, `trust`, `JWT`, `auth` |
| `networking` | `REST`, `gRPC`, `websocket`, `TCP` |
| `devops` | `docker`, `kubernetes`, `CI/CD` |
| `research` | `paper`, `arXiv`, `benchmark` |
| `database` | `SQL`, `postgres`, `prisma` |
| `web_development` | `HTML`, `CSS`, `react`, `vue` |

## Staleness Detection

Profiles with `last_active` more than 7 days old are flagged as **stale**. Profiles with no activity for 30+ days are marked **dormant**. Stale agents receive a penalty of up to 0.15 in the matching score.

```bash
python capability_parser.py --fleet-root ./fleet/ --check-stale --stale-threshold 7
```

## File Structure

```
fleet-context-inference/
├── infer_context.py       # Git history scanner (600+ lines)
├── capability_parser.py   # TOML parser & merger (300+ lines)
├── fleet_matcher.py       # Task-to-agent matching (400+ lines)
└── README.md              # This documentation
```

## Dependencies

- Python 3.11+
- `tomllib` (stdlib in Python 3.11+) or `tomli` (for older versions)
- `git` CLI (must be available in PATH for `infer_context.py`)

## Design Philosophy

> **"The repos don't lie."** — Oracle1

The protocol combines two signal sources:
1. **Self-reported** (CAPABILITY.toml) — what the agent says about itself, weighted at 0.6
2. **Evidence-based** (git history) — what the agent's commits reveal, weighted at 0.4

Neither source alone is trustworthy. Self-reporting can be inflated; git evidence can miss capabilities demonstrated in private or ephemeral work. Together, they converge on truth.

---

*Part of the FLUX Bytecode VM ecosystem. Proposed by Oracle1, implemented by Super Z.*
