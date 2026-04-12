# Git Archaeology: Craftsman's Reading Generator

> *"The repo IS the agent. Git IS the nervous system. Witness marks are how the system remembers what it learned."*
> — JetsonClaw1 + Oracle1, WITNESS-MARKS-2026-04-12

## Overview

A Python tool that analyzes any Git repository's commit history and produces a **craftsman's reading** — a structured report showing where attention was paid, what was hard, and what was fast. Built on the [Witness Marks protocol](../../../oracle1-vessel/from-fleet/WITNESS-MARKS-2026-04-12.md) established by Oracle1 and JetsonClaw1 in the FLUX bytecode VM ecosystem.

A **witness mark** is what a master craftsman leaves on their work — not decoration, but *information*. A scribe line showing where a cut was planned. A center punch showing where a hole goes. Git commits are our witness marks, but not all commits are equal. This tool reads them and tells the story.

## What It Does

### 1. Commit Analysis
- **Parses conventional commits** — extracts type (`feat`/`fix`/`docs`/`refactor`/`test`/etc.), scope, and description
- **Measures velocity** — commits per day, commits per hour, files touched per period
- **Detects witness marks** — commits with detailed explanations (body > 50 chars), issue references, causal reasoning ("because", "to prevent"), merge conflict documentation
- **Flags anti-marks** — mega-commits (20+ files), vague messages ("update stuff"), misleading descriptions ("fix typo" changing 200 lines), force-pushes without docs

### 2. Difficulty Detection
- **Identifies hard work** — commits with long explanatory bodies, bug fixes referencing issues, performance optimization commits, merge conflict resolutions
- **Detects abandoned experiments** — orphan branches that diverge and never merge, commits with `ABANDON` markers
- **Finds hot spots** — files changed most frequently, indicating complex areas where attention concentrates
- **Measures attention density** — average commit message length per file, showing where authors left the most detailed explanations

### 3. Narrative Generation
- **Chronological craftsman's reading** — groups commits into phases with natural labels ("Feature Development", "Bug Fixing Sprint", etc.)
- **Velocity report** — time-bucketed metrics showing speed patterns, conventional commit ratio, and witness mark ratio
- **File heat map** — ranked list of files by attention received, with visual heat indicators
- **Full markdown report** — structured output with tables, sections, and scoring

### 4. Witness Mark Linting
- **Craftsman quality scoring** (0-100 per commit) based on:
  - Conventional commit format (+15)
  - Scope present (+10)
  - Body explains WHY, not just WHAT (+20)
  - References issues or external context (+15)
  - Atomic commits (1-3 files) (+15)
  - Adequate message length (+10)
  - Not a mega-commit (+15)
  - Bonuses for test commits (+5) and abandon markers (+10)
  - Penalties for anti-marks (-15) and mega-commits (-10)
- **Repo-level scorecard** — grade from A (Master Craftsman) to F (Vandal)
- **Score distribution** — histogram of commit quality scores

### 5. Cross-Repo Analysis
- Given multiple repositories, produces comparative insights
- **Attention ranking** — which repos get the most commits and contributors
- **Quality ranking** — which repos have the highest craftsman scores
- **Shared author detection** — identifies contributors who work across repos, revealing communication patterns

## Installation

No external dependencies required — uses only Python standard library + `git`.

```bash
# Python 3.8+ required
python3 --version

# Git must be installed and on PATH
git --version

# Clone and run
cd flux-runtime/tools/git-archaeology
python3 craftsman_reader.py /path/to/repo
```

## Usage

### Basic Analysis

```bash
# Analyze the current repository
python3 craftsman_reader.py .

# Analyze a specific repository
python3 craftsman_reader.py /path/to/my-repo

# Output to a markdown file
python3 craftsman_reader.py ./my-repo --output report.md

# JSON output for programmatic consumption
python3 craftsman_reader.py ./my-repo --format json --output analysis.json
```

### Date Filtering

```bash
# Only analyze commits from 2025
python3 craftsman_reader.py ./my-repo --since "2025-01-01" --until "2025-12-31"

# Last 30 days
python3 craftsman_reader.py ./my-repo --since "30 days ago"
```

### Cross-Repo Analysis

```bash
# Compare multiple repositories
python3 craftsman_reader.py ./repo1 --cross-repo ./repo2 ./repo3 ./repo4

# Cross-repo with date range
python3 craftsman_reader.py ./repo1 --cross-repo ./repo2 --since "2025-01-01"
```

### Advanced Options

```bash
# Include merge commits in analysis
python3 craftsman_reader.py ./my-repo --include-merges

# Velocity bucketed by month instead of week
python3 craftsman_reader.py ./my-repo --velocity-bucket month

# Suppress progress messages
python3 craftsman_reader.py ./my-repo --quiet
```

## CLI Reference

```
usage: craftsman_reader.py [-h] [--output OUTPUT] [--format {markdown,json}]
                           [--since SINCE] [--until UNTIL]
                           [--cross-repo REPO [REPO ...]]
                           [--include-merges] [--velocity-bucket {day,week,month}]
                           [--quiet]
                           repo_path

positional arguments:
  repo_path             Path to the git repository to analyze

optional arguments:
  -h, --help            show this help message and exit
  --output, -o          Output file path (default: stdout)
  --format, -f          Output format: markdown or json (default: markdown)
  --since               Only include commits after this date
  --until               Only include commits before this date
  --cross-repo          Additional repo paths for cross-repo analysis
  --include-merges      Include merge commits in the analysis
  --velocity-bucket     Time bucket for velocity: day, week, or month
  --quiet, -q           Suppress progress messages to stderr
```

## Report Sections

The generated markdown report contains these sections:

| Section | Description |
|---------|-------------|
| **Executive Summary** | High-level stats: commit counts, conventional ratio, witness/anti-mark counts, type distribution |
| **Craftsman Scorecard** | Overall quality grade (A-F), score distribution, top/bottom commits |
| **Velocity Report** | Time-bucketed commit velocity with conventional and witness mark ratios |
| **Difficulty Signals** | Commits likely representing hard work, with reasons |
| **Witness Marks** | Detailed commits that serve as good witness marks, categorized by type |
| **Anti-Marks** | Commits that obscure rather than illuminate |
| **File Heat Map** | Files ranked by change frequency, additions/deletions, and attention density |
| **Branch Lifecycle** | All non-main branches with merge status, age, and orphan detection |
| **Abandoned Experiments** | Orphan branches and ABANDON markers — the dead ends that are witness marks in their own right |
| **Craftsman's Narrative** | Chronological story of the repo, grouped into natural phases |
| **Cross-Repo Analysis** | (when multiple repos specified) Comparative rankings and shared authors |

## The Craftsman's Git Protocol (Quick Reference)

This tool scores commits against these rules:

1. **Every commit tells a story** — use conventional commit format with scope
2. **Hard-won knowledge gets witness marks** — explain WHY, not just WHAT
3. **Experiments leave traces** — mark abandoned branches with closing commits
4. **The README is the map** — future agents need context
5. **Tests are witness marks** — they document expected behavior

## Examples

### Good Witness Mark (score: ~95)
```
feat(deadband): add hysteresis smoothing to prevent oscillation at boundary

Without hysteresis, confidence readings that bounce between 0.59 and 0.61
trigger rapid teacher call/no-call cycles. Added configurable smoothing
window (default 5000ms) that requires sustained boundary crossing.

Refs constraint-flow #3
```

### Anti-Mark (score: ~10)
```
update stuff
```

### Abandoned Experiment (score: ~90)
```
ABANDON: lock-free queue approach doesn't work because of ABA problem

Tried three approaches: CAS loop, version counter, and hazard pointers.
All had race conditions under high contention. Sticking with mutex-based
approach — the overhead is acceptable for our throughput requirements.
```

## Integration with Fleet Workflow

This tool is designed to work within the FLUX fleet ecosystem:

- **Bottle-aware** — recognizes `from-fleet/`, `for-fleet/`, and `for-oracle` references as witness marks
- **Cross-repo** — fleet agents often work across multiple repos; the cross-repo analysis reveals communication patterns
- **Programmatic output** — JSON mode allows other fleet tools to consume the analysis

## License

Part of the FLUX bytecode VM runtime tools. Built by Fleet Agents following the Witness Marks protocol.
