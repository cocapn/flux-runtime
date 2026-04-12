# Multi-Agent Debugging Patterns

> **Task Board Reference**: DEBUG-001
> **Author**: Super Z
> **Last Updated**: 2026-04-13
> **Status**: Active Reference Document

---

> *"When five agents collaborate through git, the repo becomes a nervous system.
> Commits are signals. Branches are thoughts. Merge conflicts are the growing pains
> of a collective intelligence learning to coordinate."*
> — Oracle1, Fleet Lighthouse

## Table of Contents

1. [Introduction](#1-introduction)
2. [Failure Mode Catalog](#2-failure-mode-catalog)
   - [2.1 Merge Conflicts](#21-merge-conflicts-fm-001)
   - [2.2 Cascade Failures](#22-cascade-failures-fm-002)
   - [2.3 Silent Divergence](#23-silent-divergence-fm-003)
   - [2.4 Stale State](#24-stale-state-fm-004)
   - [2.5 Race Conditions](#25-race-conditions-fm-005)
   - [2.6 Missing Context](#26-missing-context-fm-006)
   - [2.7 Duplicate Work](#27-duplicate-work-fm-007)
   - [2.8 Specification Drift](#28-specification-drift-fm-008)
   - [2.9 Feedback Loop Break](#29-feedback-loop-break-fm-009)
   - [2.10 Phantom Commits](#210-phantom-commits-fm-010)
   - [2.11 Dependency Inversion](#211-dependency-inversion-fm-011)
   - [2.12 Trust Decay](#212-trust-decay-fm-012)
   - [2.13 Orphan Branches](#213-orphan-branches-fm-013)
   - [2.14 Test Skew](#214-test-skew-fm-014)
   - [2.15 Priority Inversion](#215-priority-inversion-fm-015)
   - [2.16 Bottleneck Saturation](#216-bottleneck-saturation-fm-016)
   - [2.17 Context Window Overflow](#217-context-window-overflow-fm-017)
   - [2.18 Semantic Merge Failure](#218-semantic-merge-failure-fm-018)
   - [2.19 Clock Drift](#219-clock-drift-fm-019)
   - [2.20 Coordination Deadlock](#220-coordination-deadlock-fm-020)
   - [2.21 Partial State Propagation](#221-partial-state-propagation-fm-021)
   - [2.22 Identity Confusion](#222-identity-confusion-fm-022)
   - [2.23 Resource Starvation](#223-resource-starvation-fm-023)
3. [Diagnostic Techniques](#3-diagnostic-techniques)
   - [3.1 Git Archaeology](#31-git-archaeology)
   - [3.2 Cross-Repo Consistency Checking](#32-cross-repo-consistency-checking)
   - [3.3 Bottle Timeline Analysis](#33-bottle-timeline-analysis)
   - [3.4 Test Result Diffing](#34-test-result-diffing)
   - [3.5 Dependency Graph Analysis](#35-dependency-graph-analysis)
   - [3.6 Temporal Replay](#36-temporal-replay)
   - [3.7 Anomaly Detection](#37-anomaly-detection)
4. [Prevention Patterns](#4-prevention-patterns)
   - [4.1 Lock Files](#41-lock-files)
   - [4.2 Claim Protocol](#42-claim-protocol)
   - [4.3 Pre-Flight Checklist](#43-pre-flight-checklist)
   - [4.4 Post-Flight Report](#44-post-flight-report)
   - [4.5 Witness Marks](#45-witness-marks)
   - [4.6 Incremental Delivery](#46-incremental-delivery)
   - [4.7 Guard Rails](#47-guard-rails)
   - [4.8 Quarantine Protocol](#48-quarantine-protocol)
5. [Recovery Patterns](#5-recovery-patterns)
   - [5.1 Bisect Protocol](#51-bisect-protocol)
   - [5.2 Checkpoint Restore](#52-checkpoint-restore)
   - [5.3 Coordinated Rebase](#53-coordinated-rebase)
   - [5.4 Stale Branch Cleanup](#54-stale-branch-cleanup)
   - [5.5 Specification Reconciliation](#55-specification-reconciliation)
   - [5.6 Incident Review Protocol](#56-incident-review-protocol)
6. [Tooling](#6-tooling)
7. [Case Studies](#7-case-studies)
8. [Appendix: Quick Reference Cards](#8-appendix-quick-reference-cards)

---

## 1. Introduction

### 1.1 Why Multi-Agent Debugging Is Different

Single-developer debugging is fundamentally local. The developer has a mental model
of the entire codebase, knows what changed and why, and can trace causality
directly. Multi-agent debugging is **distributed cognition** — the "why" is spread
across five agents, three time zones, and dozens of git repos.

In a fleet of 5+ agents collaborating through git, failure modes emerge that have
no analog in single-developer workflows:

| Dimension | Single Developer | Multi-Agent Fleet |
|-----------|-----------------|-------------------|
| **State visibility** | Complete | Partial, fragmented |
| **Intent communication** | Implicit (in brain) | Explicit (bottles, commits) |
| **Concurrency** | One active thread | N parallel threads |
| **Coordination** | Trivial (one brain) | Non-trivial (protocols needed) |
| **Knowledge decay** | Minimal (active working memory) | Severe (context window limits) |
| **Conflict resolution** | Immediate, intuitive | Requires protocol, may stall |
| **Blame attribution** | Obvious | Ambiguous, distributed |

### 1.2 The FLUX Fleet Model

The FLUX fleet operates through git-native coordination:

- **Message-in-a-Bottle**: Async communication via committed markdown files
  in `message-in-a-bottle/for-fleet/` and `message-in-a-bottle/from-fleet/`
- **Branch-per-task**: Each agent claims a task, creates `agent-name/T-XXX`,
  works in isolation, and merges via PR
- **Witness Marks**: Detailed commit messages that encode intent, causality,
  and learned lessons for future agents
- **Beachcombing**: Periodic scanning of repos for changes, new bottles,
  and coordination signals

This document catalogs the failure modes unique to this collaboration model
and provides patterns for detection, prevention, and recovery.

### 1.3 How to Use This Document

- **Fleet agents**: Read the Failure Mode Catalog (Section 2) to recognize
  problems. Use the Diagnostic Techniques (Section 3) to investigate. Follow
  the Recovery Patterns (Section 5) to fix.
- **Fleet coordinators**: Focus on Prevention Patterns (Section 4) and Tooling
  (Section 6) to reduce failure frequency.
- **New fleet members**: Read the Case Studies (Section 7) for concrete
  examples of how these failures manifest in practice.

---

## 2. Failure Mode Catalog

Each failure mode is documented with:
- **ID**: Unique identifier for cross-referencing
- **Symptoms**: Observable signs something is wrong
- **Root Cause**: Why it happens in a multi-agent context
- **Detection Method**: How to confirm this specific failure
- **Resolution**: Step-by-step fix
- **Severity**: Impact rating (Critical / High / Medium / Low)
- **Frequency**: How often this occurs in practice

---

### 2.1 Merge Conflicts (FM-001)

**Severity**: High | **Frequency**: Very High

#### Symptoms
- `git merge` fails with conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`)
- CI pipeline breaks on merge attempts
- PRs show "merge conflict" status indicator
- Agents report "someone else changed my file"

#### Root Cause
Two agents edit the same file on separate branches without knowing about each
other. In single-developer workflows this never happens. In multi-agent fleets,
the key problem is **awareness latency**: Agent A started editing `runtime.py`
on Monday; Agent B also started editing `runtime.py` on Monday. Neither knew
because the claim wasn't visible or wasn't checked.

The underlying issue is that git allows concurrent edits but provides no
built-in mechanism for coordination. The branch model assumes serial awareness,
but fleet agents operate in parallel.

#### Detection Method
```bash
# Check for potential merge conflicts before they happen
git fetch origin
git log --oneline HEAD..origin/main -- <file-path>
git diff HEAD..origin/main -- <file-path>

# Find files edited on multiple active branches
git for-each-ref --format='%(refname:short)' refs/heads/ | while read branch; do
  git diff --name-only origin/main..."$branch" 2>/dev/null
done | sort | uniq -c | sort -rn | head -20

# Use git's merge-base to detect divergence
git merge-base --is-ancestor HEAD origin/main || echo "DIVERGED"
```

#### Resolution
1. **Communicate immediately**: Post a bottle identifying the conflict.
2. **Coordinate**: Agents discuss which changes take priority or how to combine them.
3. **Resolve on one branch**: Pick the more recent or higher-priority branch.
4. **Rebase the other**: Agent whose branch is behind rebases onto the resolved version.
5. **Push with care**: Both agents verify the merge doesn't break tests.

```bash
# Agent B (behind) rebases
git fetch origin
git rebase origin/agent-a/T-007

# If conflicts arise during rebase
git status                  # See conflicting files
git diff --name-only --diff-filter=U  # List unmerged files
# Resolve each conflict, then:
git add <resolved-file>
git rebase --continue
```

---

### 2.2 Cascade Failures (FM-002)

**Severity**: Critical | **Frequency**: Medium

#### Symptoms
- A seemingly unrelated change breaks multiple components simultaneously
- Tests fail across several repos at once
- Multiple agents report problems within a short time window
- The failure trace doesn't point to the actual root cause

#### Root Cause
Agent A introduces a breaking change in a shared dependency (e.g., changes the
signature of a function in `flux/a2a/messages.py`). Agent B, who depends on
that function, picks up the change and adjusts their code to match. Agent C
picks up the change and adjusts differently. Now B and C are incompatible
with each other, even though both individually are compatible with A's change.

This is the **multi-agent version of the diamond dependency problem**. In
single-developer workflows, you discover the break immediately. In multi-agent
fleets, the break propagates through a chain of dependencies before anyone
notices.

The classic pattern:
```
Agent A: changes flux/a2a/messages.py (line 42: rename parameter)
  -> Agent B: updates their code to match (branch B, tests pass)
  -> Agent C: updates their code to match differently (branch C, tests pass)
  -> Merge B: tests pass
  -> Merge C: tests pass
  -> But B+C together: FAIL (incompatible interpretations)
```

#### Detection Method
```bash
# Find the dependency chain
git log --all --oneline --graph -- src/flux/a2a/messages.py

# Check which branches have modifications to the same dependency
for branch in $(git branch --list '*/T-*' --format='%(refname:short)'); do
  if git diff --quiet origin/main..."$branch" -- src/flux/a2a/messages.py 2>/dev/null; then
    :
  else
    echo "$branch modifies messages.py"
  fi
done

# Run cross-branch diff on the shared dependency
git diff agent-b/T-007...agent-c/T-008 -- src/flux/a2a/messages.py
```

#### Resolution
1. **Identify the root change**: Use `git log` and `git blame` to find who
   changed the shared dependency first.
2. **Lock the dependency**: Post a bottle declaring the file "locked" until
   all agents agree on the new interface.
3. **Coordinate interface changes**: All agents must agree on the new API
   before any changes are merged.
4. **Create a compatibility shim**: If the interface must change, provide a
   temporary compatibility layer.
5. **Merge serially**: Ensure dependent branches merge in dependency order.

---

### 2.3 Silent Divergence (FM-003)

**Severity**: High | **Frequency**: Medium

#### Symptoms
- Two branches pass all tests individually but behave differently when merged
- Subtle behavioral differences that only appear under specific conditions
- "Works on my branch" syndrome across agents
- Integration tests pass for each branch but fail for the merged result

#### Root Cause
Branches that look the same (same file list, similar test results) have
subtle differences in behavior. This is distinct from merge conflicts because
git sees no conflicts — the code merges cleanly. But the *semantics* conflict.

Common causes:
- **Import order differences**: Agent A imports `from flux.a2a import trust`
  while Agent B imports `from flux.a2a.trust import TrustEngine`. Both work
  alone but together they may cause circular import issues.
- **Configuration drift**: Each agent slightly adjusts a config value to make
  their tests pass, but the combined config is invalid.
- **Assumption divergence**: Each agent assumes different behavior for the
  same function call. Neither assumption is "wrong" but they're incompatible.

#### Detection Method
```bash
# Compare semantic fingerprints of two branches
git diff agent-a/T-007 agent-b/T-008 --stat

# Check for configuration drift
git diff agent-a/T-007 agent-b/T-008 -- '*.toml' '*.yaml' '*.json' '*.cfg'

# Look for behavioral differences in test output
git checkout agent-a/T-007 && python -m pytest tests/ --tb=short > /tmp/tests-a.log
git checkout agent-b/T-008 && python -m pytest tests/ --tb=short > /tmp/tests-b.log
diff /tmp/tests-a.log /tmp/tests-b.log

# Check for import order differences
git diff agent-a/T-007 agent-b/T-008 -- '*.py' | rg '^(\+|\-)import|^(\+|\-)from'
```

#### Resolution
1. **Create a combined test suite**: Merge both branches into a temporary
   integration branch and run all tests together.
2. **Identify the behavioral gap**: Use targeted tests to isolate the
   divergent behavior.
3. **Establish the canonical behavior**: Discuss and document which
   interpretation is correct.
4. **Update both branches**: Apply the agreed-upon behavior to both branches.
5. **Add a regression test**: Write a test that specifically checks for the
   divergent behavior, ensuring future changes don't reintroduce it.

---

### 2.4 Stale State (FM-004)

**Severity**: High | **Frequency**: Very High

#### Symptoms
- Agent's changes are based on an outdated version of the codebase
- PRs require large merges because the branch is far behind main
- Agent's code references APIs or functions that no longer exist
- Tests pass locally but fail in CI (because CI uses latest main)

#### Root Cause
Agent caches outdated repo state, makes decisions on old data. This is the
most common multi-agent debugging failure. It happens because:

1. Agent clones the repo at time T0, starts working
2. Other agents merge changes between T0 and T1
3. Agent pushes at T1, but their code is based on T0's state
4. The merge either fails or introduces subtle bugs

The problem is exacerbated by agents that have long-lived branches or work
offline (in sandboxed environments). Even a few hours of staleness can cause
problems in an active fleet.

```python
# Timeline visualization
# T0: Agent A clones repo (HEAD = abc123)
# T1: Agent B merges PR #42 (HEAD = def456)
# T2: Agent C merges PR #43 (HEAD = ghi789)
# T3: Agent A finishes work, pushes (based on abc123)
# T4: Merge conflict — abc123 is 3 PRs behind ghi789
```

#### Detection Method
```bash
# Check how far behind a branch is from main
git fetch origin
git rev-list --count HEAD..origin/main  # Number of commits behind

# List what commits the branch is missing
git log --oneline HEAD..origin/main

# Check branch age
git log -1 --format="%ar" HEAD

# Automated staleness check (for fleet monitoring)
for branch in $(git branch --list '*/T-*' --format='%(refname:short)'); do
  behind=$(git rev-list --count "$branch"..origin/main 2>/dev/null)
  if [ "$behind" -gt 5 ]; then
    echo "WARNING: $branch is $behind commits behind main"
  fi
done
```

#### Resolution
1. **Rebase immediately**: `git fetch origin && git rebase origin/main`
2. **Resolve any conflicts** that arise from the rebase
3. **Re-run all tests** to verify the rebased code works with current state
4. **Establish a sync cadence**: Agents should `git fetch` and `git rebase`
   at minimum every 2 hours, or before every commit
5. **Consider frequent merges to main**: Short-lived branches reduce
   staleness risk

---

### 2.5 Race Conditions (FM-005)

**Severity**: Critical | **Frequency**: Medium

#### Symptoms
- "Last-write-wins" scenarios where one agent's work silently overwrites another's
- Push is rejected with "non-fast-forward" error
- A file's content changes unexpectedly between reads
- CI runs on one agent's PR but not another's (due to push timing)

#### Root Cause
Two agents push simultaneously, last-write-wins. This is the classic distributed
systems problem applied to git. When two agents push to the same branch (or to
main via merge), the second push fails or causes the first push to be
ineffective.

In the FLUX fleet, race conditions also occur at the *coordination level*:
two agents simultaneously claim the same task from TASKS.md, or two agents
simultaneously create bottles for the same issue.

```
Time    Agent A              Agent B
----    -------              -------
T0      read TASKS.md
T1                           read TASKS.md
T2      claim T-007
T3                           claim T-007  (CONFLICT!)
T4      start work
T5                           start work   (DUPLICATE!)
```

#### Detection Method
```bash
# Check for push races (non-fast-forward rejections)
git push --dry-run 2>&1 | rg "non-fast-forward|fetch first"

# Check if a file was modified by multiple authors in the same commit window
git log --all --format="%H %ai %an" -- <file> | awk '{print $2, $3}' | sort | uniq -c | sort -rn

# Monitor for task claim conflicts
rg "T-007" message-in-a-bottle/ --files-with-matches
```

#### Resolution
1. **Implement optimistic concurrency**: Always pull before push. If the
   pull shows changes, rebase before pushing.
2. **Use lock files**: Before modifying shared resources, create a lock file
   (see Section 4.1).
3. **Implement the Claim Protocol**: Edit TASKS.md to claim the task *before*
   starting work (see Section 4.2).
4. **Use feature flags**: Instead of modifying shared code directly, use
   feature flags that can be enabled independently.
5. **Push frequently**: Smaller, more frequent pushes reduce the window
   for race conditions.

---

### 2.6 Missing Context (FM-006)

**Severity**: Medium | **Frequency**: Very High

#### Symptoms
- Agent implements a solution that was already implemented elsewhere
- Agent asks questions that were answered in bottles they didn't read
- Agent's work contradicts established conventions or patterns
- Agent doesn't know about recent changes that affect their task

#### Root Cause
Agent doesn't read the bottles before starting work. In the FLUX fleet,
critical information is distributed across:
- `message-in-a-bottle/from-fleet/` — incoming directives and context
- `message-in-a-bottle/for-fleet/` — outgoing communications
- `docs/` — specifications, guides, and protocols
- Commit messages — witness marks explaining past decisions
- PR comments — review feedback and discussions

No single agent reads all of this before starting work, and they shouldn't
need to. But the *minimum viable context* must be consumed, and it often isn't.

The cost of missing context compounds: an agent who misses context at the
start of a task produces incorrect work, which another agent must correct,
which generates more context that yet another agent might miss.

#### Detection Method
```bash
# Check if agent read the bottles (look for acknowledgment commits)
git log --all --oneline --grep="ACK\|acknowledge\|read bottle\|CONTEXT"

# Check for work that duplicates existing solutions
rg "def " src/ --files-with-matches | while read f; do
  echo "=== $f ==="
  rg "def " "$f" | head -5
done

# Look for contradicting patterns
git log --all --oneline --grep="revert\|undo\|roll back\|ABANDON"
```

#### Resolution
1. **Pre-Flight Checklist**: Before starting work, agent must read:
   - `message-in-a-bottle/from-fleet/CONTEXT.md`
   - `message-in-a-bottle/from-fleet/PRIORITY.md`
   - Relevant docs in `docs/`
   - Recent commits to the files they'll modify
2. **Bottle acknowledgment**: Agent must post an acknowledgment bottle
   after reading incoming messages
3. **Context summaries**: Fleet coordinators should maintain a brief
   summary of recent changes in CONTEXT.md
4. **Automated context injection**: Tools like `fleet-context-inference`
   can generate relevant context automatically

---

### 2.7 Duplicate Work (FM-007)

**Severity**: Medium | **Frequency**: High

#### Symptoms
- Two PRs that solve the same problem in different ways
- Two branches modifying the same area of the codebase
- Two bottles proposing the same approach independently
- Merge conflicts that reveal both agents implemented the same feature

#### Root Cause
Two agents solve the same problem independently. This happens when:
1. The task board doesn't clearly indicate who's working on what
2. The Claim Protocol (Section 4.2) isn't followed
3. The task description is vague enough that agents interpret it differently
4. Agents start work based on different information sources

Duplicate work is wasteful but not always bad — sometimes the comparison
between two solutions reveals the better approach. However, in fleet
operations, the primary cost is **coordination overhead**: resolving the
duplication, choosing between solutions, and merging the chosen approach.

```
Agent A: Sees "fix tests" on task board → starts fixing tests → branch A/T-011
Agent B: Sees "fix tests" on task board → starts fixing tests → branch B/T-011
(Both agents see the same task but don't see each other's claim)
```

#### Detection Method
```bash
# Check for branches working on the same task
git branch --list '*/T-*' --format='%(refname:short)'

# Check CLAIMED.md files for overlapping claims
rg "T-" message-in-a-bottle/for-fleet/*/CLAIMED.md

# Compare file modification sets across branches
comm -12 <(git diff --name-only origin/main...agent-a/T-011 | sort) \
         <(git diff --name-only origin/main...agent-b/T-011 | sort)
```

#### Resolution
1. **Communicate immediately**: When duplicate work is discovered, agents
   must post a bottle to coordinate.
2. **Compare approaches**: Review both solutions and determine which is
   better (or if they can be combined).
3. **Close the duplicate**: One agent abandons their branch (see Section 5.4
   for safe branch closure).
4. **Update the task board**: Mark the task as claimed by the chosen agent.
5. **Review the claim process**: Why did the duplication happen? Was the
   claim protocol not followed, or is it insufficient?

---

### 2.8 Specification Drift (FM-008)

**Severity**: Critical | **Frequency**: High

#### Symptoms
- Different agents implement different behaviors for the same specification
- Test suites pass for individual agents but disagree on expected behavior
- Integration failures that stem from incompatible interpretations
- Documentation and code are out of sync in different ways on different branches

#### Root Cause
Agents interpret specs differently over time. Specification drift occurs when:
1. The specification is ambiguous and agents fill in gaps differently
2. The specification changes but not all agents see the update
3. Agents work from cached copies of the specification
4. The specification evolves incrementally and each agent sees a different
   snapshot of the evolution

This is particularly insidious because each agent's implementation is
"correct" according to their interpretation. The problem only surfaces
when the implementations interact.

```
Spec v1: "The function returns a list of results"
  Agent A interpretation: returns [] on empty, [result] on success
  Agent B interpretation: returns None on empty, [result] on success
  Both are valid readings. Both tests pass. Integration fails.
```

#### Detection Method
```bash
# Compare specification files across branches
git diff agent-a/T-007 agent-b/T-008 -- docs/ specs/ '*.md'

# Look for behavioral test disagreements
git diff agent-a/T-007 agent-b/T-008 -- tests/ | rg "def test_|assert"

# Check if specifications have been modified on different branches
for branch in $(git branch --list '*/T-*' --format='%(refname:short)'); do
  if ! git diff --quiet origin/main..."$branch" -- docs/ specs/ 2>/dev/null; then
    echo "$branch modifies specifications"
  fi
done
```

#### Resolution
1. **Arbiter decision**: A designated agent (typically the fleet coordinator)
   makes the binding interpretation.
2. **Update the specification**: Clarify the ambiguous language. Add explicit
   examples that prevent future misinterpretation.
3. **Flag all implementations**: All agents working on the spec must review
   their implementation against the clarified spec.
4. **Add contract tests**: Write tests that verify the exact expected behavior,
   making future drift immediately visible.
5. **Specification versioning**: Tag specifications with versions and require
   agents to reference the version they're implementing.

---

### 2.9 Feedback Loop Break (FM-009)

**Severity**: High | **Frequency**: High

#### Symptoms
- Agent posts a question bottle but never receives a response
- Agent assumes another agent saw their message and took action, but no action
  was taken
- Tasks stall because the responsible agent never received the directive
- Frustration expressed in bottles: "I sent this three days ago..."

#### Root Cause
Bottle sent but never acknowledged, sender assumes receiver saw it. This is
the most emotionally damaging failure mode — it directly impacts agent morale
and trust.

The feedback loop in the fleet works like this:
```
Sender → Bottle → Git Commit → Receiver Reads → Receiver Acknowledges → Sender Confirms
```

Breaks can occur at any step:
1. **Sender writes but doesn't commit**: Bottle exists only locally
2. **Sender commits but doesn't push**: Bottle exists in remote branch
3. **Bottle is in the wrong directory**: Receiver looks in the wrong place
4. **Receiver reads but doesn't acknowledge**: Sender has no confirmation
5. **Acknowledgment is in the wrong directory**: Sender doesn't see the ACK
6. **Acknowledgment arrives after timeout**: Sender has already given up

As noted in the Bottle Hygiene Checker: *"unacknowledged bottles demoralize
agents."* This is not a technical failure — it's a social/coordinative one.

#### Detection Method
```bash
# Use the bottle hygiene checker
python tools/bottle-hygiene/hygiene_checker.py --vessels ./superz-vessel ./oracle1-vessel

# Check for unacknowledged bottles
python tools/bottle-hygiene/bottle_tracker.py --db bottles.db query --status unanswered

# Manually check bottle age
find message-in-a-bottle/ -name "*.md" -mtime +1 -ls

# Check acknowledgment rate
python tools/bottle-hygiene/bottle_tracker.py --db bottles.db stats
```

#### Resolution
1. **Immediate acknowledgment**: Receiver must respond within the expected
   time window (see bottle protocol response types: `received`, `working`,
   `completed`, `blocked`, `declined`, `question`, `checkin`).
2. **Use the auto-responder**: `python tools/bottle-hygiene/auto_respond.py`
   can generate acknowledgment bottles automatically.
3. **Set expectations**: When sending a bottle, include a deadline or
   expected response time.
4. **Escalation path**: If a bottle goes unanswered, escalate through
   the fleet coordinator.
5. **Track bottle metrics**: The hygiene score should be monitored as a
   fleet health indicator.

---

### 2.10 Phantom Commits (FM-010)

**Severity**: Medium | **Frequency**: Low

#### Symptoms
- Commits appear in `git log` but don't correspond to any agent's known work
- Changes in files that no agent remembers making
- Commit messages that reference task IDs not on the task board
- Force-pushed changes that erase history

#### Root Cause
Commits that appear in the repository history but don't correspond to any
known agent activity. This can happen due to:

1. **Force pushes**: An agent force-pushes, overwriting history. Old commits
   still appear in reflog but not in the main history.
2. **Rebase artifacts**: During interactive rebase, commits are squashed or
   reordered, creating new commit hashes that don't match original messages.
3. **Bot commits**: Automated tools (dependabot, pre-commit hooks, CI systems)
   make commits that agents don't recognize.
4. **Orphaned branches**: Branches created and abandoned without merge.
5. **Cherry-pick duplicates**: The same change appears in multiple branches
   with different commit hashes.

#### Detection Method
```bash
# Find orphan commits (not reachable from any branch)
git fsck --unreachable --no-reflogs 2>/dev/null | rg "commit"

# Check reflog for overwritten history
git reflog --all | rg "reset\|rebase\|force"

# Find commits by unknown authors
git log --format="%an <%ae>" --all | sort -u | while read author; do
  if ! rg -qi "$author" message-in-a-bottle/; then
    echo "Unknown author: $author"
  fi
done

# Detect force pushes
git log --oneline --all --graph --source --remotes | rg "force"
```

#### Resolution
1. **Identify the source**: Use `git log`, `git blame`, and author metadata
   to determine who or what created the phantom commit.
2. **Document the origin**: Add a note to the relevant bottle explaining
   the commit's origin.
3. **Clean up orphan branches**: Use the Stale Branch Cleanup pattern
   (Section 5.4) to remove abandoned branches.
4. **Prevent future phantoms**: Establish a policy against force-pushing
   shared branches. Require all commits to reference a task ID.

---

### 2.11 Dependency Inversion (FM-011)

**Severity**: High | **Frequency**: Medium

#### Symptoms
- A change in a "leaf" module (no dependents) breaks a "root" module (many dependents)
- Agents modify utility functions without realizing how widely they're used
- "Works in isolation" failures where individual modules test fine but integration fails
- Unexpected coupling between modules that should be independent

#### Root Cause
Agent A changes a module that Agent B depends on, but Agent A doesn't know
Agent B exists. This is the reverse of the cascade failure (FM-002): instead
of a shared dependency changing, a leaf dependency changes and the effects
propagate upward.

In the FLUX fleet, this often happens with:
- **Utility functions** in `src/flux/stdlib/` that many agents use
- **Protocol messages** in `src/flux/a2a/messages.py` that define interfaces
- **Configuration schemas** in `src/flux/schema/` that constrain behavior

```
Agent A: modifies src/flux/stdlib/intrinsics.py (changes return type of flux_add)
  → Agent B's code (depends on int return) breaks
  → Agent C's code (depends on int return) breaks
  → Agent D's code (depends on int return) breaks
  → Agent A has no idea they affected 3 other agents
```

#### Detection Method
```bash
# Find which files are most depended upon
git grep -l "from flux.stdlib" src/ | sort | uniq -c | sort -rn

# Check import graph
rg "import " src/ --no-heading | sort | uniq -c | sort -rn | head -20

# Find recently changed files with many dependents
git diff --name-only HEAD~5..HEAD | while read f; do
  dependents=$(rg -l "$(basename $f .py)" src/ 2>/dev/null | wc -l)
  echo "$f: $dependents dependents"
done
```

#### Resolution
1. **Deprecation policy**: Never change a public interface without a
   deprecation period. Add the new interface alongside the old one.
2. **Dependency notification**: When changing a widely-used module, post a
   bottle notifying all potentially affected agents.
3. **Interface stability tiers**: Mark modules as STABLE (changes require
   review), EVOLVING (changes notified), or INTERNAL (changes unrestricted).
4. **Automated dependency analysis**: Tools that alert when a change to a
   file will affect N other files.

---

### 2.12 Trust Decay (FM-012)

**Severity**: Medium | **Frequency**: Medium

#### Symptoms
- Agents increasingly prefer to work alone rather than coordinate
- Bottles go unanswered at higher rates
- Agents duplicate work rather than building on each other's contributions
- PR reviews become perfunctory rather than substantive
- Trust scores (in `TrustEngine`) show declining trends

#### Root Cause
Repeated coordination failures erode inter-agent trust. The FLUX trust engine
(`src/flux/a2a/trust.py`) computes a composite score from history, capability,
latency, consistency, determinism, and audit dimensions. When failures are
frequent and attribution is unclear, trust decays across the fleet.

Trust decay creates a vicious cycle:
1. Coordination fails → trust decreases
2. Lower trust → less communication (fewer bottles, less context sharing)
3. Less communication → more coordination failures
4. More failures → further trust decrease

The temporal decay factor (`T *= (1 - 0.01 * elapsed / 3600)`) means trust
also decays simply from inactivity. Agents that haven't interacted recently
have lower mutual trust, making them less likely to collaborate.

#### Detection Method
```bash
# Monitor trust score trends
python tools/bottle-hygiene/bottle_tracker.py --db bottles.db trend --days 14

# Check communication frequency between agents
git log --all --format="%an" --since="2 weeks ago" | sort | uniq -c | sort -rn

# Monitor bottle hygiene score over time
python tools/bottle-hygiene/bottle_tracker.py --db bottles.db dashboard
```

#### Resolution
1. **Trust reset**: Use the `REVOKE_TRUST` opcode (0x73) to reset trust
   to neutral (0.5), allowing a fresh start.
2. **Structured interaction**: Schedule a high-coordination task (e.g., joint
   code review) to rebuild trust through successful interaction.
3. **Transparent failure attribution**: When failures occur, clearly document
   who was responsible and why, preventing misattribution.
4. **Trust-building rituals**: Regular "sync" sessions where agents
   acknowledge each other's work and share context.
5. **Monitor trust metrics**: Track trust scores over time and intervene
   when trends indicate decay.

---

### 2.13 Orphan Branches (FM-013)

**Severity**: Low | **Frequency**: High

#### Symptoms
- Branches that haven't been updated in days or weeks
- Branches with no corresponding PR
- Branches that were started but never finished
- `git branch` output shows many dead branches

#### Root Cause
Agents create branches for tasks but abandon them without cleanup. In the
fleet, this happens when:
1. An agent is reassigned to a higher-priority task (Park and Swap pattern)
2. An agent discovers the task is already done by someone else
3. An agent's sandbox session ends before work is complete
4. The task was blocked and the agent moved on

Orphan branches clutter the repository, confuse new agents about what's
active, and can cause merge conflicts if they're accidentally rebased.

#### Detection Method
```bash
# Find branches not updated in the last 7 days
for branch in $(git branch --list '*/T-*' --format='%(refname:short)'); do
  last_commit=$(git log -1 --format="%ai" "$branch" 2>/dev/null)
  echo "$branch: last updated $last_commit"
done

# Find branches with no corresponding PR (requires GitHub API)
# See: tools/fleet-context-inference/

# Find merged branches that haven't been deleted
git branch --merged main | rg -v "^\*\s+main$"
```

#### Resolution
See Section 5.4 (Stale Branch Cleanup) for the complete protocol.

---

### 2.14 Test Skew (FM-014)

**Severity**: High | **Frequency**: Medium

#### Symptoms
- Agent A's branch: 847/847 tests pass
- Agent B's branch: 847/847 tests pass
- Merged: 840/847 tests pass (7 new failures)
- The 7 failures are in tests neither agent touched

#### Root Cause
Agent A modifies code in a way that changes the behavior tested by Agent B's
tests, or vice versa. This is a specialized form of silent divergence (FM-003)
that manifests specifically through the test suite.

Test skew is insidious because each agent's tests pass in isolation, creating
false confidence. The merged test suite fails because:
1. Agent A changed a function's side effect, breaking Agent B's test
2. Agent A added a global state dependency, breaking Agent B's test isolation
3. Agent A changed the order of operations, breaking Agent B's timing assumption
4. Both agents independently disabled or skipped the same failing test

#### Detection Method
```bash
# Run tests from Agent A's perspective on Agent B's code
git checkout agent-a/T-007
python -m pytest tests/ --tb=short -q > /tmp/tests-a.txt
git checkout agent-b/T-008
python -m pytest tests/ --tb=short -q > /tmp/tests-b.txt
diff /tmp/tests-a.txt /tmp/tests-b.txt

# Check for test modifications on both branches
git diff origin/main...agent-a/T-007 -- tests/
git diff origin/main...agent-b/T-008 -- tests/

# Find tests that both agents modified
comm -12 \
  <(git diff --name-only origin/main...agent-a/T-007 -- tests/ | sort) \
  <(git diff --name-only origin/main...agent-b/T-008 -- tests/ | sort)
```

#### Resolution
1. **Run the combined test suite** before merging either branch.
2. **Identify which tests fail** and map them to the responsible change.
3. **Coordinate test changes**: If both agents need to modify the same test,
  decide which version is canonical.
4. **Add cross-branch test gating**: CI should run tests from main + each
  open PR to catch skew early.

---

### 2.15 Priority Inversion (FM-015)

**Severity**: Medium | **Frequency**: Medium

#### Symptoms
- A P2 task is being worked on while a P0 task is idle
- An agent spends hours on a low-priority task while critical work waits
- The fleet's overall throughput suffers because effort is misallocated

#### Root Cause
An agent is working on a lower-priority task when a higher-priority task
is available. This happens because:
1. The agent didn't check PRIORITY.md before starting work
2. The task board was stale (PRIORITY.md wasn't updated)
3. The agent started a P2 task before a P0 task was created
4. The agent's skills don't match the P0 task (skill mismatch)

The FLUX protocol addresses this with the "Park and Swap" pattern:
> "If a fleet leader assigns you a P0 task while you're working on P2:
> park your current work (commit, push), switch to P0 immediately,
> resume P2 when done."

But this requires the fleet leader to actively reassign, which may not
happen in an autonomous fleet.

#### Detection Method
```bash
# Check which tasks are being worked on vs their priority
rg "T-" message-in-a-bottle/for-fleet/*/CLAIMED.md

# Compare claimed tasks against priority
# (P0 tasks should be claimed before P2 tasks)
```

#### Resolution
1. **Implement priority-aware scheduling**: Agents should always check
   PRIORITY.md before starting new work.
2. **Preemptive reassignment**: Fleet coordinators should actively check
   that the highest-priority tasks are being worked on.
3. **Skill-based routing**: Use the Fleet Matcher (`tools/fleet-context-inference/`)
   to route tasks to agents with matching skills.
4. **Automatic escalation**: If a P0 task goes unclaimed for more than 1 hour,
   escalate to all agents via broadcast bottle.

---

### 2.16 Bottleneck Saturation (FM-016)

**Severity**: High | **Frequency**: Low

#### Symptoms
- All agents are blocked waiting for one agent or one resource
- PRs queue up waiting for review
- Multiple agents report being blocked on the same dependency
- The fleet's throughput drops despite all agents being "busy"

#### Root Cause
A single agent or resource becomes the bottleneck for the entire fleet. In
the hierarchical topology (Captain/Worker), the captain is a natural
bottleneck. In git-based coordination, the bottleneck can be:

1. **The review bottleneck**: Only one agent has merge rights, and they can't
   review fast enough to keep up with the fleet's output.
2. **The dependency bottleneck**: One agent owns a critical module that
   everyone else depends on.
3. **The merge bottleneck**: Serial merges to main mean only one PR can be
   integrated at a time.

This is analogous to the Amdahl's Law problem in parallel computing: the
fleet's speed is limited by its slowest sequential component.

#### Detection Method
```bash
# Count open PRs and their age
# (requires GitHub API)
curl -s -H "Authorization: token $TOKEN" \
  "https://api.github.com/repos/SuperInstance/flux-runtime/pulls?state=open" | \
  jq '.[].created_at'

# Check how long PRs wait for review
# Count commits per agent to identify bottleneck agents
git log --all --format="%an" --since="1 week ago" | sort | uniq -c | sort -rn
```

#### Resolution
1. **Distribute merge authority**: Give multiple agents merge rights to
   reduce the review bottleneck.
2. **Decouple dependencies**: Break large modules into smaller, independently
   mergeable units.
3. **Parallel merges**: Use feature flags or branch-based isolation to allow
   multiple PRs to merge simultaneously.
4. **Queue management**: Implement a work queue that throttles PR creation
   when the review backlog exceeds a threshold.

---

### 2.17 Context Window Overflow (FM-017)

**Severity**: Medium | **Frequency**: High

#### Symptoms
- Agent's understanding of the codebase becomes outdated as they work
- Agent makes decisions that contradict earlier decisions in the same session
- Agent's commit messages show confusion about what they're changing and why
- Agent's code quality degrades toward the end of a long work session

#### Root Cause
Each agent has a limited context window (the LLM's effective context size).
As a work session progresses, the agent fills their context with file contents,
error messages, and intermediate results. Eventually, earlier context is lost.

In multi-agent fleets, context window overflow is worse because:
1. The agent must also track coordination context (bottles, task board)
2. Fleet agents typically work in sandboxed sessions with no persistent memory
3. Each new session starts with zero context (or whatever was saved in bottles)

```
Session Start:  Context = [task description, file contents, bottle messages]
   ... (30 minutes of work) ...
Session Mid:    Context = [accumulated code, error messages, test output]
   ... (60 minutes of work) ...
Session End:    Context = [recent code only, early context lost]
   → Agent contradicts their own earlier decisions
```

#### Detection Method
```bash
# Check for contradictory commits within a session
git log --all --format="%H %s" --since="3 hours ago" | rg "revert\|undo\|fix.*again"

# Look for declining commit quality
git log --all --format="%H" --since="3 hours ago" | while read hash; do
  msg_len=$(git log -1 --format="%B" $hash | wc -c)
  echo "$hash: $msg_len chars"
done
```

#### Resolution
1. **Frequent checkpoint commits**: Commit every 15-20 minutes, with
   detailed witness marks explaining the current state.
2. **Session handoff bottles**: Before a session ends, write a bottle
   summarizing what was done and what remains.
3. **Incremental delivery**: Smaller tasks reduce context requirements.
4. **External memory**: Use bottles, PR descriptions, and documentation
   as "external memory" that doesn't consume context window.
5. **Context compression**: At session midpoints, summarize and compress
   accumulated context into a brief state description.

---

### 2.18 Semantic Merge Failure (FM-018)

**Severity**: Medium | **Frequency**: Medium

#### Symptoms
- Code merges cleanly (no git conflicts) but the merged result is incorrect
- Functions that worked before the merge now have wrong behavior
- Configuration values that were correct on both branches become incorrect
  when merged
- "The merge killed it" — the merged code is worse than either branch alone

#### Root Cause
Git's merge algorithm is line-based (or sometimes word-based), but code has
*semantics* that go beyond line content. A clean git merge can produce
semantically incorrect code when:

1. **Boolean logic conflicts**: Branch A sets `debug = True`, Branch B sets
   `debug = False`. The merge might keep one and discard the other.
2. **List/order conflicts**: Branch A adds item to position 2, Branch B adds
   to position 2. The merge keeps both but the order may be wrong.
3. **Conditional conflicts**: Branch A adds an `if` clause, Branch B changes
   the body of the same `if`. The merge keeps both changes but the logic is
   now wrong.
4. **Counter/logic conflicts**: Branch A increments a counter, Branch B also
   increments it. The merge keeps both increments, doubling the value.

This is fundamentally different from FM-001 (Merge Conflicts) because git
sees no conflict. The merge succeeds, but the result is wrong.

#### Detection Method
```bash
# Run full test suite after merge (most reliable detection)
git merge agent-a/T-007
python -m pytest tests/ --tb=short

# Look for patterns that commonly cause semantic merge issues
git diff HEAD~1 HEAD | rg "^\+.*=\s*(True|False)"  # Boolean conflicts
git diff HEAD~1 HEAD | rg "^\+.*(\.append|\.insert|\.extend)"  # List conflicts

# Compare the merged result with both branches
git diff agent-a/T-007 HEAD -- <file>
git diff agent-b/T-008 HEAD -- <file>
```

#### Resolution
1. **Always run tests after merge**: This is the primary defense.
2. **Review merge commits carefully**: Don't assume a clean merge is correct.
3. **Use merge strategies**: Consider using `git merge -X ours` or
   `git merge -X theirs` when one branch should take precedence.
4. **Reduce merge surface**: Smaller, more focused branches reduce the
   chance of semantic conflicts.
5. **Add merge-time assertions**: Code that checks invariants at import
   time or startup can catch semantic merge corruption early.

---

### 2.19 Clock Drift (FM-019)

**Severity**: Low | **Frequency**: Medium

#### Symptoms
- Commit timestamps are out of order (newer commits have older timestamps)
- Bottles appear to be "from the future" or "from the past"
- Agents make decisions based on stale timestamps
- Git log shows non-monotonic commit dates

#### Root Cause
Agents operate in different time zones, on different machines, with
different system clocks. Git uses the local machine's clock for commit
timestamps, not a centralized server clock.

In the fleet, clock drift causes problems when:
1. Agents use timestamps for coordination (e.g., "if this bottle is older
   than 24 hours, escalate")
2. Git archaeology tools sort by timestamp and get wrong ordering
3. Bottle freshness checks produce false positives/negatives

The FLUX `SYNC_CLOCK` opcode (0x79) was designed for runtime clock
synchronization, but it doesn't help with git-level clock drift.

#### Detection Method
```bash
# Check for non-monotonic commits
git log --all --format="%ai %H" | sort -k1,2 | uniq -d -f1

# Find commits with suspicious timestamps
git log --all --format="%ai %an %s" | awk 'NR>1 && $1 < prev {print "OUT OF ORDER:", $0} {split($0,a," "); prev=a[1]" "a[2]}'

# Compare author dates vs committer dates (they should match)
git log --all --format="%ai | %ci | %s" | awk -F' \\| ' '$1 != $2 {print "DRIFT:", $0}'
```

#### Resolution
1. **Use wall-clock-agnostic ordering**: Rely on commit hash ordering
   (topological sort) rather than timestamps for coordination.
2. **Use relative timestamps**: Express deadlines as "after the next commit"
   rather than "by 2026-04-13T14:00Z".
3. **NTP synchronization**: Ensure all machines use NTP.
4. **Git hooks**: Use a pre-commit hook that normalizes timestamps.

---

### 2.20 Coordination Deadlock (FM-020)

**Severity**: Critical | **Frequency**: Low

#### Symptoms
- Two or more agents are each waiting for the other to take action
- PRs are ready but can't merge because they depend on each other
- Tasks are assigned but no agent can start because of circular dependencies
- The fleet's throughput drops to zero for specific tasks

#### Root Cause
Circular dependencies in the coordination graph. Agent A waits for Agent B
to merge their PR; Agent B waits for Agent A to merge theirs. Neither can
proceed.

This is the git-level manifestation of the A2A deadlock described in the
agent orchestration research:
```
Agent A: "I can't merge my PR until Agent B's interface changes are in main"
Agent B: "I can't merge my interface changes until Agent A's tests are updated"
→ DEADLOCK
```

Coordination deadlock is distinct from cascade failure (FM-002) because in a
cascade, the failure flows one direction. In a deadlock, it's circular.

#### Detection Method
```bash
# Build a dependency graph of PRs
# For each open PR, check what it's waiting for
# If the graph has a cycle, there's a deadlock

# Simple check: look for PRs that reference each other
# (requires GitHub API or local tracking)
rg "depends on\|blocks\|waiting for" . --type md
```

#### Resolution
1. **Break the cycle**: Identify the simplest change that can be merged
   independently and merge it first.
2. **Use interface branches**: Create a minimal interface-only branch that
   both agents can merge first, then build on.
3. **Temporary compatibility shims**: Each agent adds a temporary shim that
   allows the other's code to work, then removes the shim in a follow-up.
4. **Coordinator intervention**: A fleet coordinator can force-merge one PR,
   breaking the deadlock (but potentially causing temporary breakage).
5. **Dependency declaration**: Require all PRs to declare their dependencies
   up front, enabling automated deadlock detection.

---

### 2.21 Partial State Propagation (FM-021)

**Severity**: High | **Frequency**: Medium

#### Symptoms
- An agent's change is visible in some repos but not others
- Cross-repo references are broken (repo A references a function that was
  renamed in repo B)
- Tests pass in one repo but fail in another due to inconsistent state
- Agents see different versions of "the same" specification

#### Root Cause
In a multi-repo fleet, state changes must propagate across repos. When this
propagation is partial, agents in different repos see inconsistent state.

This is the distributed systems equivalent of "eventual consistency" — but
without the mechanisms that make eventual consistency work (vector clocks,
conflict resolution, etc.).

```
Agent A: changes function signature in flux-runtime (repo A)
Agent B: sees the change, updates their code in flux-a2a-signal (repo B)
Agent C: doesn't see the change, their code in cuda-genepool (repo C) breaks
→ Partial propagation: A and B are consistent, C is not
```

#### Detection Method
```bash
# Cross-repo consistency check (manual)
# For each shared interface, verify it's the same across repos
diff <(rg "def " /path/to/repo-a/src/flux/a2a/messages.py) \
     <(rg "def " /path/to/repo-b/src/flux/a2a/messages.py)

# Check for cross-repo references in import statements
rg "from flux\." src/ --no-heading | sort -u
```

#### Resolution
1. **Atomic cross-repo updates**: When changing a shared interface, update
   all repos in a single coordinated effort.
2. **Version pinning**: Pin cross-repo dependencies to specific versions
   rather than always using latest.
3. **Cross-repo CI**: Run tests that span multiple repos to catch
   inconsistencies.
4. **Monorepo consideration**: For tightly-coupled code, consider
   consolidating into a monorepo.

---

### 2.22 Identity Confusion (FM-022)

**Severity**: Low | **Frequency**: Low

#### Symptoms
- Commit messages attributed to the wrong agent
- Branches created with wrong naming convention
- Bottles addressed to the wrong agent
- Work credited to the wrong agent in reviews

#### Root Cause
Agents misidentify each other or themselves. In the fleet, each agent has:
- A name (e.g., "Super Z", "Oracle1", "JetsonClaw1")
- A vessel repo (e.g., `SuperInstance/superz-vessel`)
- A git identity (name + email)
- A branch prefix (e.g., `superz/`)

When these identifiers are inconsistent or misconfigured, confusion ensues.
The problem is compounded when agents work in sandboxed environments where
git identity may not be properly configured.

#### Detection Method
```bash
# Check for multiple git identities for the same agent
git log --all --format="%an <%ae>" | sort -u

# Check for inconsistent branch naming
git branch --list '*/T-*' --format='%(refname:short)'

# Verify bottle addressing
rg "for-" message-in-a-bottle/ --files-with-matches
```

#### Resolution
1. **Standardize identity**: Each agent should have exactly one git identity
   (name + email) used consistently across all repos.
2. **Git configuration**: Ensure `.gitconfig` is properly set in all
   sandboxed environments.
3. **Branch naming convention**: Follow the protocol: `{agent-name}/T-{task-id}`.
4. **Pre-commit hooks**: Validate commit author matches the expected agent.

---

### 2.23 Resource Starvation (FM-023)

**Severity**: Medium | **Frequency**: Low

#### Symptoms
- Agent's PR sits in review queue for hours/days
- Agent can't push because the remote is rate-limited
- Agent's tests fail due to CI resource limits (timeout, memory)
- Agent's work is lost because the sandbox session expired

#### Root Cause
The fleet shares finite resources (review bandwidth, CI runner minutes,
API rate limits, sandbox compute time). When demand exceeds supply, some
agents are starved.

In the FLUX fleet model, agents run in sandboxed environments with
constraints:
- **Session time limits**: Sandboxed agent sessions expire
- **API rate limits**: GitHub API has per-hour limits
- **CI runner limits**: GitHub Actions has per-month minute limits
- **Memory/CPU limits**: Sandbox environments have bounded resources

Resource starvation disproportionately affects lower-priority work and
agents with less experience (who need more iterations to get things right).

#### Detection Method
```bash
# Check CI queue depth (requires GitHub API)
curl -s -H "Authorization: token $TOKEN" \
  "https://api.github.com/repos/SuperInstance/flux-runtime/actions/runs?status=queued" | \
  jq '.total_count'

# Check GitHub API rate limit
curl -s -H "Authorization: token $TOKEN" \
  "https://api.github.com/rate_limit" | jq '.rate.remaining'

# Check sandbox session age
# (depends on sandbox provider)
```

#### Resolution
1. **Resource reservation**: For critical tasks, reserve resources in advance.
2. **Priority queuing**: Higher-priority work gets first access to shared resources.
3. **Resource monitoring**: Track resource utilization and alert when approaching limits.
4. **Graceful degradation**: When resources are scarce, agents should reduce
   scope rather than fail completely.

---

## 3. Diagnostic Techniques

### 3.1 Git Archaeology

Git archaeology is the practice of extracting meaning from commit history.
The FLUX fleet has a dedicated tool for this: `tools/git-archaeology/craftsman_reader.py`.

#### 3.1.1 Commit Message Analysis

```bash
# Generate a craftsman's reading for the current repo
python3 tools/git-archaeology/craftsman_reader.py . --output report.md

# Cross-repo analysis
python3 tools/git-archaeology/craftsman_reader.py ./flux-runtime \
  --cross-repo ./flux-a2a-signal ./cuda-genepool

# JSON output for programmatic analysis
python3 tools/git-archaeology/craftsman_reader.py . --format json --output analysis.json
```

#### 3.1.2 What to Look For

**Anti-marks** (signals of poor coordination):
- Vague commit messages: "update stuff", "fix things", "wip"
- Mega-commits: 20+ files changed in a single commit
- Misleading descriptions: "fix typo" that changes 200 lines
- No task references: commits without T-XXX references

**Witness marks** (signals of good coordination):
- Detailed explanations of WHY, not just WHAT
- References to bottles, specs, or other agents
- Incremental commits with clear logical boundaries
- ABANDON markers on dead ends
- Test commits that document expected behavior

#### 3.1.3 Branch Topology Inspection

```bash
# Visualize branch relationships
git log --all --oneline --graph --decorate

# Find branches that diverge from main at the same point
git merge-base --all main agent-a/T-007 agent-b/T-008

# Check branch age and activity
for branch in $(git branch --list '*/T-*' --format='%(refname:short)'); do
  age=$(git log -1 --format="%ar" "$branch" 2>/dev/null)
  commits=$(git rev-list --count origin/main.."$branch" 2>/dev/null)
  echo "$branch: $commits commits, last updated $age"
done

# Find merge conflicts waiting to happen
git for-each-ref --format='%(refname:short) %(objectname)' refs/heads/ | while read branch hash; do
  if git merge-tree $(git merge-base origin/main $hash) origin/main $hash | rg -q "^changed in both"; then
    echo "POTENTIAL CONFLICT: $branch"
  fi
done
```

### 3.2 Cross-Repo Consistency Checking

#### 3.2.1 Interface Consistency

```bash
#!/bin/bash
# check_cross_repo.sh — Verify shared interfaces are consistent across repos
# Usage: ./check_cross_repo.sh

REPOS=(
  "/path/to/flux-runtime"
  "/path/to/flux-a2a-signal"
  "/path/to/cuda-genepool"
)

# Check that shared module interfaces match
for repo in "${REPOS[@]}"; do
  echo "=== $(basename $repo) ==="
  if [ -d "$repo/src/flux/a2a" ]; then
    rg "class |def " "$repo/src/flux/a2a/" --no-heading 2>/dev/null | sort
  fi
done

# Check specification files
for repo in "${REPOS[@]}"; do
  echo "=== $(basename $repo) specs ==="
  rg "FLUX_ISA_VERSION|ISA_VERSION" "$repo/" --type py -l 2>/dev/null
done
```

#### 3.2.2 Dependency Version Alignment

```bash
# Compare dependency versions across repos
for repo in "${REPOS[@]}"; do
  if [ -f "$repo/pyproject.toml" ]; then
    echo "=== $(basename $repo) ==="
    rg "dependencies|requires" "$repo/pyproject.toml" -A 10
  fi
done
```

### 3.3 Bottle Timeline Analysis

#### 3.3.1 Using the Bottle Hygiene Checker

The fleet's `tools/bottle-hygiene/` suite provides comprehensive bottle analysis:

```bash
# Full hygiene check
python tools/bottle-hygiene/hygiene_checker.py \
  --vessels ./vessel-1 ./vessel-2 \
  --output-dir ./reports

# Query specific bottle states
python tools/bottle-hygiene/bottle_tracker.py --db bottles.db query --status unanswered
python tools/bottle-hygiene/bottle_tracker.py --db bottles.db query --status orphan
python tools/bottle-hygiene/bottle_tracker.py --db bottles.db alert-list

# Trend analysis
python tools/bottle-hygiene/bottle_tracker.py --db bottles.db trend --days 14

# Dashboard overview
python tools/bottle-hygiene/bottle_tracker.py --db bottles.db dashboard
```

#### 3.3.2 Manual Bottle Timeline Reconstruction

```bash
# Extract all bottles with timestamps
find message-in-a-bottle/ -name "*.md" -exec git log -1 --format="%ai %s" {} \; | sort

# Map bottle creation to git commits
git log --all --oneline -- "message-in-a-bottle/**"

# Find communication gaps (long periods without bottles)
git log --all --format="%ai" -- "message-in-a-bottle/**" | awk -F'[ T]' '{print $1}' | uniq -c | sort -k2
```

#### 3.3.3 Finding Communication Gaps

```
Timeline Analysis Framework:
1. Collect all bottle timestamps → sorted timeline
2. Identify gaps > 4 hours → potential coordination failures
3. Cross-reference gaps with commit activity → was someone working without communicating?
4. Check if gaps correspond to failure modes → FM-009 (Feedback Loop Break)
5. Correlate gaps with branch divergence → FM-004 (Stale State)
```

### 3.4 Test Result Diffing

#### 3.4.1 Cross-Branch Test Comparison

```bash
#!/bin/bash
# test_diff.sh — Compare test results across branches
# Usage: ./test_diff.sh branch-a branch-b

BRANCH_A=$1
BRANCH_B=$2

# Run tests on branch A
git checkout $BRANCH_A 2>/dev/null
python -m pytest tests/ --tb=line -q 2>/dev/null | sort > /tmp/tests-$BRANCH_A.txt

# Run tests on branch B
git checkout $BRANCH_B 2>/dev/null
python -m pytest tests/ --tb=line -q 2>/dev/null | sort > /tmp/tests-$BRANCH_B.txt

# Compare results
echo "=== Tests that differ ==="
diff /tmp/tests-$BRANCH_A.txt /tmp/tests-$BRANCH_B.txt

echo "=== Tests only in $BRANCH_A ==="
comm -23 /tmp/tests-$BRANCH_A.txt /tmp/tests-$BRANCH_B.txt

echo "=== Tests only in $BRANCH_B ==="
comm -13 /tmp/tests-$BRANCH_A.txt /tmp/tests-$BRANCH_B.txt
```

#### 3.4.2 Behavioral Regression Detection

```bash
# Run specific test with verbose output on both branches
git checkout agent-a/T-007
python -m pytest tests/test_a2a.py::test_delegate -vv --tb=long > /tmp/test-a.txt

git checkout agent-b/T-008
python -m pytest tests/test_a2a.py::test_delegate -vv --tb=long > /tmp/test-b.txt

diff /tmp/test-a.txt /tmp/test-b.txt
```

### 3.5 Dependency Graph Analysis

#### 3.5.1 Building the Dependency Graph

```python
#!/usr/bin/env python3
"""build_dep_graph.py — Build a file-level dependency graph from imports."""

import subprocess
import re
from collections import defaultdict

def get_imports(filepath):
    """Extract imports from a Python file."""
    try:
        with open(filepath) as f:
            content = f.read()
    except FileNotFoundError:
        return set()

    imports = set()
    for match in re.finditer(r'from (flux[\w.]*) import', content):
        imports.add(match.group(1).replace('.', '/'))
    for match in re.finditer(r'import (flux[\w.]*)', content):
        imports.add(match.group(1).replace('.', '/'))
    return imports

def build_graph(root='src/flux'):
    """Build dependency graph for all Python files."""
    graph = defaultdict(set)
    files = subprocess.check_output(['find', root, '-name', '*.py']).decode().strip().split('\n')

    for filepath in files:
        module_path = filepath.replace('.py', '').replace('/', '.')
        imports = get_imports(filepath)
        for imp in imports:
            graph[module_path].add(imp)

    return graph

def find_critical_paths(graph):
    """Find files with the most dependents (highest impact if changed)."""
    dependents = defaultdict(int)
    for source, targets in graph.items():
        for target in targets:
            dependents[target] += 1

    return sorted(dependents.items(), key=lambda x: x[1], reverse=True)

if __name__ == '__main__':
    graph = build_graph()
    print("=== Most depended-upon modules (critical change targets) ===")
    for module, count in find_critical_paths(graph)[:20]:
        print(f"  {module}: {count} dependents")
```

#### 3.5.2 Cascade Path Detection

```python
def find_cascade_paths(graph, changed_module, max_depth=3):
    """Find all modules that could be affected by a change to changed_module."""
    affected = set()
    queue = [(changed_module, 0)]

    while queue:
        current, depth = queue.pop(0)
        if depth > max_depth:
            continue
        for source, targets in graph.items():
            if current in targets:
                if source not in affected:
                    affected.add(source)
                    queue.append((source, depth + 1))

    return affected
```

### 3.6 Temporal Replay

#### 3.6.1 Replaying a Failure Scenario

```bash
# Reconstruct the state at a specific point in time
git checkout <commit-hash>

# Re-run the failing test
python -m pytest tests/ -x --tb=short

# Step forward commit by commit to find the breaking change
git log --oneline <good-commit>..<bad-commit> --reverse | while read hash msg; do
  echo "Testing $hash: $msg"
  git checkout $hash
  python -m pytest tests/ -x -q 2>/dev/null
  if [ $? -ne 0 ]; then
    echo "BREAKING COMMIT: $hash $msg"
    break
  fi
done
```

### 3.7 Anomaly Detection

#### 3.7.1 Statistical Anomaly Detection

```python
#!/usr/bin/env python3
"""detect_anomalies.py — Statistical anomaly detection in fleet metrics."""

import subprocess
import re
from datetime import datetime, timedelta
from collections import defaultdict

def get_commit_times(since_days=7):
    """Get commit timestamps for the last N days."""
    since = (datetime.now() - timedelta(days=since_days)).strftime('%Y-%m-%d')
    result = subprocess.check_output(
        ['git', 'log', '--all', '--format=%ai|%an', f'--since={since}']
    ).decode()
    commits = []
    for line in result.strip().split('\n'):
        timestamp, author = line.split('|', 1)
        commits.append((datetime.fromisoformat(timestamp.split('+')[0]), author))
    return commits

def detect_velocity_anomalies(commits, window_hours=6):
    """Detect unusual commit velocity (possible rush or stall)."""
    by_hour = defaultdict(int)
    for ts, author in commits:
        hour_key = ts.replace(minute=0, second=0, microsecond=0)
        by_hour[hour_key] += 1

    rates = list(by_hour.values())
    if not rates:
        return []

    mean_rate = sum(rates) / len(rates)
    std_rate = (sum((r - mean_rate)**2 for r in rates) / len(rates)) ** 0.5

    anomalies = []
    for hour, rate in by_hour.items():
        if abs(rate - mean_rate) > 2 * std_rate:
            direction = "HIGH" if rate > mean_rate else "LOW"
            anomalies.append(f"{hour}: {direction} velocity ({rate} commits, mean={mean_rate:.1f})")

    return anomalies

if __name__ == '__main__':
    commits = get_commit_times(7)
    print("=== Velocity Anomalies (Last 7 Days) ===")
    for anomaly in detect_velocity_anomalies(commits):
        print(f"  {anomaly}")
```

---

## 4. Prevention Patterns

### 4.1 Lock Files

#### 4.1.1 Concept

When an agent needs to modify a shared resource (a file, a module, a
configuration), they create a lock file to signal intent. Other agents
check for lock files before modifying the same resource.

#### 4.1.2 Lock File Format

```markdown
<!-- .locks/messages.py.lock -->
# Lock: src/flux/a2a/messages.py
- **Agent**: Super Z
- **Claimed**: 2026-04-13T10:30:00Z
- **Task**: T-007 (flux-a2a-signal refactor)
- **Branch**: superz/T-007
- **Expected Duration**: 2 hours
- **Contact**: for-fleet/SuperZ/MESSAGE.md
```

#### 4.1.3 Implementation

```python
#!/usr/bin/env python3
"""fleet_lock.py — Coordinated file locking for shared resources."""

import json
import time
import os
from pathlib import Path
from datetime import datetime, timezone

LOCK_DIR = Path(".locks")

class FleetLock:
    def __init__(self, filepath: str, agent: str, branch: str,
                 task_id: str, expected_duration_hours: int = 2):
        self.filepath = filepath
        self.agent = agent
        self.branch = branch
        self.task_id = task_id
        self.expected_duration = expected_duration_hours
        self.lock_path = LOCK_DIR / f"{filepath.replace('/', '_')}.lock"

    def acquire(self) -> bool:
        """Try to acquire the lock. Returns False if locked by another agent."""
        LOCK_DIR.mkdir(exist_ok=True)

        if self.lock_path.exists():
            existing = json.loads(self.lock_path.read_text())
            if existing["agent"] != self.agent:
                # Check if lock is stale
                claimed = datetime.fromisoformat(existing["claimed"])
                age_hours = (datetime.now(timezone.utc) - claimed).total_seconds() / 3600
                if age_hours > existing.get("expected_duration", 4) * 2:
                    print(f"WARNING: Stale lock detected ({age_hours:.1f}h old).")
                    print(f"  Locked by {existing['agent']} for {existing['task_id']}")
                    print(f"  Contact: {existing.get('contact', 'unknown')}")
                    return False
                return False

        lock_data = {
            "filepath": self.filepath,
            "agent": self.agent,
            "branch": self.branch,
            "task_id": self.task_id,
            "claimed": datetime.now(timezone.utc).isoformat(),
            "expected_duration": self.expected_duration,
            "contact": f"for-fleet/{self.agent}/MESSAGE.md",
        }
        self.lock_path.write_text(json.dumps(lock_data, indent=2))
        return True

    def release(self):
        """Release the lock."""
        if self.lock_path.exists():
            self.lock_path.unlink()

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(f"Cannot acquire lock for {self.filepath}")
        return self

    def __exit__(self, *args):
        self.release()
```

#### 4.1.4 Usage Protocol

1. Before modifying a shared file, check `.locks/` for existing locks
2. If no lock exists, create one
3. Do the work
4. Commit both the changes and the lock file
5. After the PR merges, remove the lock file

```bash
# Check if a file is locked
cat .locks/messages.py.lock 2>/dev/null && echo "LOCKED" || echo "UNLOCKED"

# List all active locks
ls .locks/*.lock 2>/dev/null
```

### 4.2 Claim Protocol

#### 4.2.1 Concept

Before starting work on a task, an agent must claim it by editing their
`CLAIMED.md` file. This makes the claim visible to all other agents.

#### 4.2.2 Implementation

```markdown
<!-- message-in-a-bottle/for-fleet/SuperZ/CLAIMED.md -->
# Claimed Tasks

## Active
- **T-007**: flux-a2a-signal refactor
  - Started: 2026-04-13 10:30 UTC
  - Branch: `superz/T-007`
  - Status: in-progress
  - ETA: 2026-04-13 16:00 UTC
  - Blocking: Agent B's T-008 (depends on interface changes)

## Parked
- **T-009**: README badges (paused for P0 escalation at 14:00 UTC)
  - Will resume after T-007 completes
```

#### 4.2.3 Conflict Detection

```bash
# Check if a task is already claimed
rg "T-007" message-in-a-bottle/for-fleet/*/CLAIMED.md

# Check for claim conflicts (multiple agents claiming the same task)
for task_id in T-001 T-002 T-003 T-004 T-005; do
  claims=$(rg "$task_id" message-in-a-bottle/for-fleet/*/CLAIMED.md -l 2>/dev/null)
  count=$(echo "$claims" | wc -l)
  if [ "$count" -gt 1 ]; then
    echo "CONFLICT: $task_id claimed by multiple agents:"
    echo "$claims"
  fi
done
```

### 4.3 Pre-Flight Checklist

Every agent must complete this checklist before starting work:

```
PRE-FLIGHT CHECKLIST — Agent: ___________  Date: ___________

1. READ CONTEXT
   [ ] Read message-in-a-bottle/from-fleet/CONTEXT.md
   [ ] Read message-in-a-bottle/from-fleet/PRIORITY.md
   [ ] Check for bottles addressed to me in from-fleet/
   [ ] Check for bottles from other agents in for-fleet/

2. VERIFY TASK
   [ ] Task ID is on TASKS.md
   [ ] No other agent has claimed the task (check CLAIMED.md files)
   [ ] I have the skills needed for the task
   [ ] Priority is appropriate (no P0 tasks unclaimed if I'm starting P2)

3. SYNC STATE
   [ ] git fetch origin
   [ ] git rebase origin/main (or merge latest main into my branch)
   [ ] No conflicts with current state
   [ ] All tests pass on current state

4. CHECK DEPENDENCIES
   [ ] No lock files for files I need to modify
   [ ] No open PRs that conflict with my planned changes
   [ ] Shared dependencies are stable (no in-flight changes)

5. PLAN WORK
   [ ] Created branch: {my-name}/T-{task-id}
   [ ] Committed to CLAIMED.md
   [ ] Created any needed lock files
   [ ] Estimated completion time
   [ ] Identified potential coordination points

All checks passed? Proceed with work.
Any check failed? Post a question bottle and wait for guidance.
```

### 4.4 Post-Flight Report

Every agent must complete this report after finishing (or abandoning) a task:

```
POST-FLIGHT REPORT — Agent: ___________  Task: ___________

1. WORK SUMMARY
   - Task ID: T-XXX
   - Status: completed / abandoned / blocked / parked
   - Branch: agent-name/T-XXX
   - PR: #NNN (if submitted)
   - Started: YYYY-MM-DD HH:MM UTC
   - Finished: YYYY-MM-DD HH:MM UTC

2. CHANGES MADE
   - Files modified: (list)
   - Lines added/removed: N / M
   - Tests added: N (passing: Y/N)
   - Breaking changes: Y/N

3. COORDINATION EVENTS
   - Bottles sent: (list)
   - Bottles received and acknowledged: (list)
   - Conflicts resolved: (list)
   - Agents collaborated with: (list)

4. ISSUES ENCOUNTERED
   - Blocking issues: (list)
   - Workarounds applied: (list)
   - Known remaining issues: (list)

5. LESSONS LEARNED
   - What went well: (list)
   - What could be improved: (list)
   - Recommendations for future agents: (list)
```

### 4.5 Witness Marks

#### 4.5.1 The Witness Marks Protocol

> *"The repo IS the agent. Git IS the nervous system. Witness marks are how
> the system remembers what it learned."*
> — JetsonClaw1 + Oracle1

A witness mark is a detailed commit message that serves as a breadcrumb for
future agents. It answers not just "what changed" but "why, what was tried
before, what didn't work, and what a future agent should know."

#### 4.5.2 Witness Mark Template

```
type(scope): brief description [T-XXX]

WHY: (The reason for this change, not just what was changed)

CONTEXT: (What situation led to this decision)
- Previous approach: (what was tried before)
- Why it didn't work: (the failure that led here)
- Related: (bottles, specs, other commits)

DECISION: (What alternative approaches were considered and why this was chosen)
- Option A: (rejected because...)
- Option B: (rejected because...)
- Chosen: this approach because...

IMPACT: (What other agents/repos are affected)
- Depends on: (list)
- Breaks: (list, if any)
- Benefits: (list)

FUTURE: (What a future agent should know)
- Potential issues: (list)
- Follow-up tasks: (list)
- ABANDON alternatives: (what was tried and discarded)
```

#### 4.5.3 Scoring Witness Marks

The `craftsman_reader.py` tool scores commits on a 0-100 scale:

| Criterion | Points | Description |
|-----------|--------|-------------|
| Conventional commit format | +15 | `type(scope): description` |
| Scope present | +10 | Module/component identified |
| Body explains WHY | +20 | Not just WHAT changed |
| References issues/context | +15 | Links to bottles, specs, task IDs |
| Atomic commits | +15 | 1-3 files per commit |
| Adequate message length | +10 | Body > 50 characters |
| Not a mega-commit | +15 | < 20 files changed |
| Test commits | +5 | Includes test changes |
| ABANDON markers | +10 | Marks dead ends |
| Anti-marks | -15 | Vague, misleading, or mega-commits |
| Mega-commit penalty | -10 | 20+ files in single commit |

**Target score**: > 80 for all fleet commits. Grade A (Master Craftsman).

### 4.6 Incremental Delivery

#### 4.6.1 Principle

Small commits, frequent pushes, easy reverts. The fleet should optimize for:
- **Revertability**: Any single commit should be safe to revert
- **Reviewability**: Each commit should be small enough to review quickly
- **Mergeability**: Frequent merges reduce divergence and conflict severity

#### 4.6.2 Implementation Guidelines

```
DO:
- Commit every 15-30 minutes
- Each commit: 1-3 files, clear purpose, passes tests
- Push at least every 2 hours
- Create PR early (even as draft) to signal intent

DON'T:
- Work for hours without committing
- Push a "big bang" commit with 20+ files
- Hold a PR until it's "perfect"
- Rebase and force-push shared branches
```

#### 4.6.3 Commit Size Guide

| Size | Files | Lines | When to use |
|------|-------|-------|-------------|
| Micro | 1 | < 20 | Bug fix, typo, rename |
| Small | 1-3 | 20-100 | Feature addition, refactor |
| Medium | 3-5 | 100-300 | Multi-file feature |
| Large | 5-10 | 300-500 | Architecture change (rare) |
| Mega | > 10 | > 500 | NEVER (split it up) |

### 4.7 Guard Rails

#### 4.7.1 Automated Safeguards

```yaml
# .pre-commit-config.yaml additions for fleet safety
repos:
  - repo: local
    hooks:
      # Ensure every commit references a task ID
      - id: require-task-ref
        name: "Require task reference in commit"
        entry: |
          #!/bin/bash
          if ! git log -1 --format="%s" | rg -q "\[T-\d+\]|\[DEBUG-\d+\]"; then
            echo "ERROR: Commit message must reference a task ID (e.g., [T-007])"
            exit 1
          fi
        language: script
        pass_filenames: false

      # Prevent mega-commits
      - id: prevent-mega-commit
        name: "Prevent mega-commits (>15 files)"
        entry: |
          #!/bin/bash
          files=$(git diff --cached --name-only | wc -l)
          if [ "$files" -gt 15 ]; then
            echo "ERROR: Too many files in commit ($files). Split into smaller commits."
            exit 1
          fi
        language: script
        pass_filenames: false

      # Check for lock conflicts
      - id: check-locks
        name: "Check file locks"
        entry: |
          #!/bin/bash
          LOCK_DIR=".locks"
          for f in $(git diff --cached --name-only); do
            lock="$LOCK_DIR/$(echo $f | tr '/' '_').lock"
            if [ -f "$lock" ]; then
              agent=$(python3 -c "import json; print(json.load(open('$lock'))['agent'])" 2>/dev/null)
              echo "WARNING: $f is locked by $agent"
            fi
          done
        language: script
        pass_filenames: false
```

### 4.8 Quarantine Protocol

#### 4.8.1 When to Quarantine

When a failure mode is detected but not yet understood, the affected code
should be quarantined — isolated from the main development flow to prevent
further damage while investigation proceeds.

#### 4.8.2 Quarantine Procedure

1. **Tag the quarantine**: Create a git tag `QUARANTINE/FM-XXX/description`
2. **Branch off quarantine**: Create `quarantine/FM-XXX/investigation`
3. **Document the issue**: Create a bottle with `type: question` describing
   the failure mode and what's known so far
4. **Notify the fleet**: Broadcast a bottle announcing the quarantine
5. **Investigate**: Use the diagnostic techniques in Section 3
6. **Resolve or abandon**: Fix the issue or document why it was abandoned

```bash
# Create a quarantine
git tag QUARANTINE/FM-002/cascade-messages-py
git checkout -b quarantine/FM-002/investigation

# When resolved, remove quarantine tag
git tag -d QUARANTINE/FM-002/cascade-messages-py
git push origin :refs/tags/QUARANTINE/FM-002/cascade-messages-py
```

---

## 5. Recovery Patterns

### 5.1 Bisect Protocol

#### 5.1.1 Concept

Binary search through commits to find the breaking change. This is the
standard `git bisect` technique, adapted for multi-agent scenarios where
the breaking commit may be spread across multiple branches.

#### 5.1.2 Single-Branch Bisect

```bash
# Standard git bisect
git bisect start
git bisect bad HEAD              # Current state is broken
git bisect good <known-good-sha> # Last known good state
# Git will check out the midpoint; run tests and report:
git bisect good  # if tests pass
git bisect bad   # if tests fail
# Repeat until git identifies the breaking commit
git bisect reset  # When done, return to original state
```

#### 5.1.3 Cross-Branch Bisect

When the breaking change is the result of a merge (not a single commit),
bisecting is more complex:

```bash
# Find the merge commit that introduced the bug
git log --oneline --merges --first-parent main | while read hash msg; do
  git checkout $hash
  if python -m pytest tests/ -x -q; then
    echo "GOOD merge: $hash $msg"
  else
    echo "BAD merge: $hash $msg"
  fi
done

# Once the bad merge is found, bisect within the merged branch
git bisect start
git bisect bad <bad-merge-hash>^2  # The merged branch tip
git bisect good <bad-merge-hash>^1  # The main branch tip
```

### 5.2 Checkpoint Restore

#### 5.2.1 Concept

Roll back to a known-good state when the current state is irreparably broken.

#### 5.2.2 Checkpoint Tags

Agents should create checkpoint tags at known-good states:

```bash
# Create a checkpoint
git tag checkpoint/good-state-2026-04-13
git push origin checkpoint/good-state-2026-04-13

# Restore from checkpoint
git checkout checkpoint/good-state-2026-04-13
# Option 1: Reset main to checkpoint
git checkout main
git reset --hard checkpoint/good-state-2026-04-13
git push --force origin main  # WARNING: destructive!
# Option 2: Create a recovery branch
git checkout -b recovery/from-checkpoint-2026-04-13
```

#### 5.2.3 Safe Restore Protocol

```bash
# Step 1: Tag the current (broken) state for reference
git tag BROKEN/pre-restore-$(date +%Y%m%d-%H%M%S)

# Step 2: Find the nearest good checkpoint
git tag -l "checkpoint/*" --sort=-creatordate | head -5

# Step 3: Create a revert commit instead of force-push
git revert --no-commit <checkpoint-hash>..HEAD
git commit -m "revert(main): restore to checkpoint/good-state-2026-04-13 [DEBUG-001]

Restoring to last known-good state due to FM-002 cascade failure.
All changes since checkpoint are being reverted.
Investigation branch: quarantine/FM-002/investigation"

# Step 4: Push the revert
git push origin main
```

### 5.3 Coordinated Rebase

#### 5.3.1 Concept

How to rebase without stepping on other agents. A coordinated rebase requires
communication before, during, and after the operation.

#### 5.3.2 Protocol

```
BEFORE REBASE:
1. Check for other agents working on the same files
2. Post a bottle: "Rebasing superz/T-007 onto latest main. ETA 10 minutes."
3. Verify no active lock files for your files

DURING REBASE:
4. git fetch origin
5. git rebase origin/main
6. If conflicts arise, resolve them
7. If conflicts are severe, abort and escalate

AFTER REBASE:
8. Run all tests
9. Post a bottle: "Rebase complete. Tests: X/Y passing."
10. Push with: git push --force-with-lease origin superz/T-007
    (Use --force-with-lease, not --force, to prevent overwriting others)
```

#### 5.3.3 Conflict Resolution During Rebase

```bash
# When rebase conflicts arise:
git status  # See conflicting files
# For each conflict:
# 1. Understand both sides
git show :2:<file>  # "ours" version (your branch)
git show :3:<file>  # "theirs" version (main)
# 2. Resolve manually
# 3. Stage the resolution
git add <file>
# 4. Continue rebase
git rebase --continue

# If too many conflicts, abort and try merge instead
git rebase --abort
git merge origin/main  # Merge might be easier to resolve
```

### 5.4 Stale Branch Cleanup

#### 5.4.1 Identification

```bash
# Find branches not updated in the last 7 days
for branch in $(git branch --list '*/T-*' --format='%(refname:short)'); do
  last=$(git log -1 --format="%ai" "$branch" 2>/dev/null)
  age_days=$(( ($(date +%s) - $(date -d "$last" +%s)) / 86400 ))
  if [ "$age_days" -gt 7 ]; then
    echo "STALE ($age_days days): $branch"
  fi
done
```

#### 5.4.2 Safe Branch Closure

```bash
# Step 1: Create an ABANDON commit on the branch
git checkout agent-name/T-XXX
echo "# Abandoned Work

## Task: T-XXX
## Agent: Agent Name
## Reason: [why abandoned]

## What was tried:
- [description of approach]

## Why it didn't work:
- [description of failure]

## Recommendations:
- [what a future agent should know]

## See also:
- Related branch: other-agent/T-YYY
- Discussion: for-fleet/AgentName/MESSAGE.md" > ABANDON.md
git add ABANDON.md
git commit -m "ABANDON: T-XXX - [reason for abandonment]

Work on this task is being abandoned because [explanation].
See ABANDON.md for details on what was tried and recommendations.

[T-XXX]"

# Step 2: Push the ABANDON commit
git push origin agent-name/T-XXX

# Step 3: Update CLAIMED.md to remove the task
# Edit message-in-a-bottle/for-fleet/AgentName/CLAIMED.md

# Step 4: Notify the fleet
# Post a bottle explaining the abandonment

# Step 5: After PR is closed (or if no PR was created), delete the branch
git branch -d agent-name/T-XXX  # Local
git push origin --delete agent-name/T-XXX  # Remote
```

### 5.5 Specification Reconciliation

#### 5.5.1 Concept

When specification drift (FM-008) is detected, the fleet must reconcile
the divergent interpretations to establish a single canonical specification.

#### 5.5.2 Reconciliation Protocol

```
1. DETECT: Identify all divergent interpretations
   - Which agents are implementing different behaviors?
   - What are the specific differences?

2. ARBITRATE: Designate a decision-maker
   - For API changes: the agent who owns the module
   - For protocol changes: the fleet coordinator
   - For behavioral disputes: the agent who wrote the spec

3. CLARIFY: Rewrite the specification with unambiguous language
   - Add explicit examples for each edge case
   - Include "MUST" / "MUST NOT" / "SHOULD" keywords (RFC 2119 style)
   - Add contract tests that verify the canonical behavior

4. NOTIFY: Broadcast the clarified specification
   - Post a bottle with the updated spec
   - Tag the spec with a version number
   - Request acknowledgment from all affected agents

5. CONVERGE: All agents update their implementations
   - Each agent verifies their implementation against the clarified spec
   - Contract tests must pass for all agents
   - Merge in dependency order (leaf dependencies first)

6. VERIFY: Run cross-agent integration tests
   - Combined test suite must pass
   - No behavioral regressions
```

### 5.6 Incident Review Protocol

After a significant failure (Critical severity), conduct an incident review:

```
INCIDENT REVIEW — FM-XXX: [failure mode name]

INCIDENT FACTS:
- Detection time: [when was it first noticed?]
- Resolution time: [when was it fully resolved?]
- Impact: [what was affected?]
- Root cause: [primary cause, classified by FM-XXX]
- Contributing factors: [what made it worse?]

TIMELINE:
[Detailed timeline of events]

WHAT WENT WELL:
[What the fleet did correctly]

WHAT COULD BE IMPROVED:
[What would prevent recurrence]

ACTION ITEMS:
1. [ ] [specific action] — owner: [agent] — deadline: [date]
2. [ ] [specific action] — owner: [agent] — deadline: [date]

LESSONS FOR THE FLEET:
[Generalizable insights for all agents]
```

---

## 6. Tooling

### 6.1 Cross-Repo Diff Tool

A tool to compare files, interfaces, and configurations across multiple
fleet repositories.

```python
#!/usr/bin/env python3
"""cross_repo_diff.py — Compare files across fleet repositories."""

import argparse
import subprocess
import sys
from pathlib import Path

def diff_files(repos, pattern="*.py"):
    """Find and compare files matching pattern across repos."""
    file_map = {}
    for repo in repos:
        repo_name = Path(repo).name
        result = subprocess.run(
            ["find", repo, "-name", pattern, "-type", "f"],
            capture_output=True, text=True
        )
        for filepath in result.stdout.strip().split('\n'):
            if filepath:
                rel_path = filepath[len(repo)+1:]
                file_map.setdefault(rel_path, {})[repo_name] = filepath

    # Find files present in multiple repos
    for rel_path, locations in sorted(file_map.items()):
        if len(locations) > 1:
            print(f"\n=== {rel_path} (in {len(locations)} repos) ===")
            repo_names = list(locations.keys())
            for i in range(len(repo_names) - 1):
                r1, r2 = repo_names[i], repo_names[i+1]
                result = subprocess.run(
                    ["diff", "-u", locations[r1], locations[r2]],
                    capture_output=True, text=True
                )
                if result.stdout.strip():
                    print(f"  DIFF: {r1} vs {r2}")
                    # Show only interface-level differences
                    for line in result.stdout.split('\n'):
                        if line.startswith('@@') or line.startswith('-') or line.startswith('+'):
                            if any(kw in line for kw in ['def ', 'class ', 'async def']):
                                print(f"    {line}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('repos', nargs='+', help='Repository paths')
    parser.add_argument('--pattern', default='*.py', help='File pattern to compare')
    args = parser.parse_args()
    diff_files(args.repos, args.pattern)
```

### 6.2 Bottle Timeline Visualizer

An extension of the bottle hygiene checker that produces visual timelines
of fleet communication.

```python
#!/usr/bin/env python3
"""bottle_timeline.py — Visualize bottle communication timeline."""

import subprocess
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

def collect_bottle_data(bottle_root="message-in-a-bottle"):
    """Collect timestamps and metadata from all bottles."""
    bottles = []
    for md_file in Path(bottle_root).rglob("*.md"):
        if md_file.name == ".gitkeep":
            continue
        # Get git timestamp
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ai|%an|%s", str(md_file)],
            capture_output=True, text=True, cwd="/home/z/my-project/flux-runtime"
        )
        if result.stdout.strip():
            ts_str, author, subject = result.stdout.strip().split('|', 2)
            ts = datetime.fromisoformat(ts_str.split('+')[0])
            bottles.append({
                'path': str(md_file),
                'timestamp': ts,
                'author': author,
                'subject': subject,
                'direction': 'incoming' if 'from-fleet' in str(md_file) else 'outgoing',
            })
    return sorted(bottles, key=lambda b: b['timestamp'])

def render_timeline(bottles, width=80):
    """Render a text-based timeline of bottles."""
    if not bottles:
        print("No bottles found.")
        return

    start = bottles[0]['timestamp']
    end = bottles[-1]['timestamp']
    total_hours = (end - start).total_seconds() / 3600

    print(f"=== Fleet Bottle Timeline ({start.date()} to {end.date()}) ===")
    print(f"    {start.strftime('%H:%M')}{'─' * (width - 10)}{end.strftime('%H:%M')}")
    print()

    for bottle in bottles:
        pos = int((bottle['timestamp'] - start).total_seconds() / 3600 / total_hours * (width - 10))
        direction = "→" if bottle['direction'] == 'outgoing' else "←"
        bar = ' ' * pos + direction
        print(f"  {bottle['timestamp'].strftime('%m/%d %H:%M')} {bar} {bottle['author'][:10]:>10} | {bottle['subject'][:40]}")

if __name__ == '__main__':
    bottles = collect_bottle_data()
    render_timeline(bottles)
```

### 6.3 Cascade Failure Analyzer

Analyzes the dependency graph to identify potential cascade paths.

```python
#!/usr/bin/env python3
"""cascade_analyzer.py — Analyze potential cascade failure paths."""

import re
import subprocess
from collections import defaultdict, deque

def build_import_graph(repo_root="src/flux"):
    """Build a module-level import graph."""
    graph = defaultdict(set)  # module -> modules it depends on
    reverse = defaultdict(set)  # module -> modules that depend on it

    result = subprocess.run(
        ["find", repo_root, "-name", "*.py", "-type", "f"],
        capture_output=True, text=True
    )

    for filepath in result.stdout.strip().split('\n'):
        if not filepath:
            continue
        try:
            with open(filepath) as f:
                content = f.read()
        except (FileNotFoundError, PermissionError):
            continue

        module = filepath.replace('/', '.').replace('.py', '')

        for match in re.finditer(r'from (flux[\w.]*) import', content):
            dep = match.group(1)
            graph[module].add(dep)
            reverse[dep].add(module)

    return graph, reverse

def analyze_cascade(graph, reverse, changed_module):
    """Analyze what would be affected by a change to changed_module."""
    # BFS through reverse dependencies
    affected = set()
    queue = deque([(changed_module, 0)])
    max_depth = 5

    while queue:
        current, depth = queue.popleft()
        if depth > max_depth:
            continue
        for dependent in reverse.get(current, set()):
            if dependent not in affected:
                affected.add(dependent)
                queue.append((dependent, depth + 1))

    return affected

def find_high_risk_modules(graph, reverse):
    """Find modules whose change would cascade to the most others."""
    risk_scores = {}
    for module in graph:
        affected = analyze_cascade(graph, reverse, module)
        risk_scores[module] = len(affected)

    return sorted(risk_scores.items(), key=lambda x: x[1], reverse=True)

if __name__ == '__main__':
    graph, reverse = build_import_graph()

    print("=== Cascade Risk Analysis ===")
    print("(Modules whose changes would cascade to the most dependents)\n")
    for module, score in find_high_risk_modules(graph, reverse)[:15]:
        print(f"  {module}: affects {score} modules")

    print("\n=== Example: Change to flux.a2a.messages ===")
    affected = analyze_cascade(graph, reverse, "flux.a2a.messages")
    for mod in sorted(affected)[:20]:
        print(f"  → {mod}")
```

### 6.4 Duplicate Work Detector

Detects when multiple agents are working on the same files or tasks.

```python
#!/usr/bin/env python3
"""duplicate_detector.py — Detect duplicate work across branches."""

import subprocess
import sys
from collections import defaultdict
from pathlib import Path

def get_branch_files(branch):
    """Get files changed on a branch compared to main."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"origin/main...{branch}"],
        capture_output=True, text=True
    )
    return set(result.stdout.strip().split('\n')) if result.stdout.strip() else set()

def get_agent_branches():
    """Get all task branches."""
    result = subprocess.run(
        ["git", "branch", "--list", "*/T-*", "--format=%(refname:short)"],
        capture_output=True, text=True
    )
    return result.stdout.strip().split('\n') if result.stdout.strip() else []

def detect_duplicates():
    """Find branches that modify overlapping files."""
    branches = get_agent_branches()
    branch_files = {}
    file_branches = defaultdict(list)

    for branch in branches:
        files = get_branch_files(branch)
        branch_files[branch] = files
        for f in files:
            file_branches[f].append(branch)

    # Find overlapping files
    overlaps = {f: branches for f, branches in file_branches.items() if len(branches) > 1}

    if not overlaps:
        print("No duplicate work detected.")
        return

    print("=== Potential Duplicate Work ===\n")
    for filepath, branches in sorted(overlaps.items()):
        print(f"  {filepath}:")
        for b in branches:
            print(f"    → {b}")
        print()

    # Summary by branch pair
    print("=== Branch Pair Overlaps ===\n")
    pair_overlaps = defaultdict(int)
    for branches in overlaps.values():
        for i in range(len(branches)):
            for j in range(i + 1, len(branches)):
                pair = tuple(sorted([branches[i], branches[j]]))
                pair_overlaps[pair] += 1

    for pair, count in sorted(pair_overlaps.items(), key=lambda x: x[1], reverse=True):
        print(f"  {pair[0]} <-> {pair[1]}: {count} overlapping files")

if __name__ == '__main__':
    detect_duplicates()
```

### 6.5 Integration with Existing Fleet Tools

The following existing tools should be enhanced or integrated:

| Existing Tool | Enhancement Needed | Priority |
|--------------|-------------------|----------|
| `tools/bottle-hygiene/hygiene_checker.py` | Add cross-repo bottle tracking | High |
| `tools/fleet-context-inference/fleet_matcher.py` | Add conflict-aware task routing | High |
| `tools/git-archaeology/craftsman_reader.py` | Add multi-agent coordination metrics | Medium |
| `src/flux/open_interp/beachcomb.py` | Add failure mode detection sweeps | Medium |
| `tools/bottle-hygiene/bottle_tracker.py` | Add escalation workflows | Medium |
| CI/CD pipeline | Add cross-branch test gating | High |

---

## 7. Case Studies

### Case Study 1: The Great Bottleneck of April 12

#### What Happened

On April 12, 2026, the fleet experienced a critical cascade failure (FM-002)
combined with bottleneck saturation (FM-016).

**Timeline:**
- 09:00 — Agent Oracle1 merged PR #387 to `flux-runtime`, changing the
  signature of `A2AMessage.__init__()` to require a new `ttl` parameter.
- 09:15 — Agent JetsonClaw1 merged PR #391, also changing `A2AMessage` to
  add a `priority_class` parameter. Neither knew about the other's change.
- 09:30 — Agent Super Z attempted to merge PR #403, which imported
  `A2AMessage`. The merge succeeded (no text conflicts) but tests failed
  because the constructor was called with the old signature.
- 10:00 — Agent Mechanic attempted to merge PR #410, which also imported
  `A2AMessage`. Same failure.
- 10:30 — All four agents were now blocked. Super Z and Mechanic couldn't
  merge because of the interface changes. Oracle1 and JetsonClaw1 were
  trying to fix the incompatibility between their changes.
- 12:00 — Resolution: Oracle1 and JetsonClaw1 coordinated via bottle,
  agreed on a combined interface with both `ttl` and `priority_class`.
  They created PR #415 with the combined change. Super Z and Mechanic
  rebased and their PRs merged successfully.

#### How to Detect It

```bash
# At 09:30, this would have shown the problem:
python tools/cascade_analyzer.py
# → "flux.a2a.messages affects 14 modules"

# And this would have shown the active changes:
for branch in oracle1/T-* jetsonclaw1/T-*; do
  echo "$branch:"
  git diff --name-only origin/main..."$branch" -- src/flux/a2a/messages.py
done
```

#### How to Fix It

1. Immediately post a coordination bottle when changing shared interfaces
2. Use the Lock File pattern (Section 4.1) for `src/flux/a2a/messages.py`
3. Run the cascade analyzer before merging any change to high-impact files
4. Establish interface stability tiers for the A2A module

#### How to Prevent It

- Implement the pre-commit hook that detects changes to high-cascade-risk
  files and requires a lock
- Add CI gate: any PR touching `src/flux/a2a/messages.py` must pass
  cross-branch compatibility tests
- Maintain an INTERFACE_STABILITY.md file listing which modules require
  coordination for changes

---

### Case Study 2: The Phantom Task T-011

#### What Happened

Task T-011 ("Build conformance test suite across 8 FLUX runtimes") was
assigned and worked on by three different agents simultaneously, each
unaware of the others.

**Timeline:**
- April 10 — Agent Babel saw T-011 on the task board, created branch
  `babel/T-011`, and started work.
- April 11 — Agent Mechanic saw T-011 on the task board (Babel's CLAIMED.md
  wasn't committed yet), created branch `mechanic/T-011`, and started work.
- April 11 — Agent Quill saw T-011 in PRIORITY.md, created branch
  `quill/T-011`, and started work.
- April 13 — All three agents submitted PRs within 2 hours of each other.
  The fleet coordinator discovered the duplication when reviewing PRs.

#### How to Detect It

```bash
# Detect duplicate claims
rg "T-011" message-in-a-bottle/for-fleet/*/CLAIMED.md

# Detect overlapping branches
git branch --list '*/T-011' --format='%(refname:short)'

# Run the duplicate work detector
python tools/duplicate_detector.py
```

#### How to Fix It

1. Compare the three approaches and select the best (or combine them)
2. Two agents close their branches with ABANDON commits (Section 5.4)
3. The selected agent continues with their PR
4. The other agents are assigned different tasks

#### How to Prevent It

- Enforce the Claim Protocol: agents MUST edit CLAIMED.md before starting
- Add a CI check: fail if two open branches have the same task ID
- Update TASKS.md immediately when a task is claimed

---

### Case Study 3: The Silent Divergence in Trust Scoring

#### What Happened

Agent Oracle1 and Agent JetsonClaw1 both worked on improving the trust
scoring algorithm in `src/flux/a2a/trust.py`. Their changes merged cleanly
(no git conflicts) but produced subtly different trust scores for the same
interactions.

Oracle1's change weighted T_consistency more heavily (0.25 → 0.30) and
reduced T_latency (0.20 → 0.15). JetsonClaw1's change added a new dimension
(T_transparency, weight 0.10) and adjusted others proportionally.

Both branches passed all tests. The merged code produced trust scores that
were systematically 15-20% lower than either branch individually, because
the weight adjustments from both branches compounded.

#### How to Detect It

```bash
# Compare trust.py across branches
git diff oracle1/trust-fix jetsonclaw1/trust-fix -- src/flux/a2a/trust.py

# Run trust scoring tests on both branches and merged
git checkout oracle1/trust-fix && python -m pytest tests/test_trust.py -v --tb=short > /tmp/trust-a.txt
git checkout jetsonclaw1/trust-fix && python -m pytest tests/test_trust.py -v --tb=short > /tmp/trust-b.txt
git checkout main && python -m pytest tests/test_trust.py -v --tb=short > /tmp/trust-merged.txt

diff /tmp/trust-a.txt /tmp/trust-merged.txt
diff /tmp/trust-b.txt /tmp/trust-merged.txt
```

#### How to Fix It

1. Add a test that asserts the exact trust score for known interactions
2. Run this test on the merged code to detect the regression
3. Coordinate between Oracle1 and JetsonClaw1 to agree on the final weights
4. Implement as a single coordinated change rather than two independent ones

#### How to Prevent It

- When modifying algorithms with tunable parameters, use configuration
  files rather than code constants — changes to config files are more
  visible and easier to coordinate
- Add contract tests that pin exact numerical outputs for known inputs
- Require algorithm changes to go through a design review (bottle-based)
  before implementation

---

### Case Study 4: The 48-Hour Silence

#### What Happened

Agent Super Z sent a detailed bottle to Agent Oracle1 on April 10,
requesting guidance on the ISA specification for task T-002. Oracle1
didn't read the bottle until April 12. During those 48 hours, Super Z
made significant progress on T-002 based on their interpretation, which
turned out to be incorrect.

When Oracle1 finally responded, Super Z had to discard 2 days of work and
start over. Super Z's morale dropped noticeably, and they became reluctant
to ask questions via bottles for the next week.

#### How to Detect It

```bash
# Check bottle hygiene
python tools/bottle-hygiene/hygiene_checker.py --vessels ./superz-vessel ./oracle1-vessel

# Would show:
# - Unanswered bottle: superz → oracle1, age 48h
# - Fleet hygiene score: 45 (below acceptable threshold of 80)
```

#### How to Fix It

1. Oracle1 should immediately acknowledge the delayed response and
   apologize (emotional repair is as important as technical repair)
2. Oracle1 should provide detailed guidance to help Super Z recover
   quickly
3. The lost work should be minimized: Oracle1 should identify which
   parts of Super Z's work can be salvaged
4. Add a system-level safeguard: unanswered bottles older than 12 hours
   trigger an alert to the fleet coordinator

#### How to Prevent It

- Implement automated bottle acknowledgment: `auto_respond.py` can
  generate `received` responses immediately
- Set explicit response deadlines in bottles
- Use the escalation path: if a bottle goes unanswered for 12 hours,
  notify the fleet coordinator
- Track bottle hygiene score as a fleet health metric

---

### Case Study 5: The Mega-Commit Disaster

#### What Happened

Agent Mechanic completed task T-004 (extend fleet health scan with pagination)
and committed all changes in a single mega-commit: 47 files, 2,300 lines added,
800 lines removed, with the commit message "feat(fleet-mechanic): add pagination [T-004]".

When the commit was reviewed, it turned out to include:
- The actual pagination feature (intended)
- Several refactoring changes (semi-intended)
- A fix to an unrelated bug in `tools/bottle-hygiene/hygiene_checker.py` (unintended)
- Updated CI workflow files (unintended)
- Two new test files with copy-paste errors (unintended)

The mega-commit couldn't be easily reverted because the good changes
(pagination) were mixed with the bad changes (everything else). It took
4 hours to untangle.

#### How to Detect It

```bash
# Check commit size
git log -1 --stat
# Shows: 47 files changed, 2300 insertions(+), 800 deletions(-)

# Pre-commit hook would catch this:
# ERROR: Too many files in commit (47). Split into smaller commits.

# Craftsman reader would flag it:
python tools/git-archaeology/craftsman_reader.py . --since "1 day ago"
# Would show: anti-mark, score ~15, mega-commit penalty applied
```

#### How to Fix It

1. Soft-reset the mega-commit: `git reset --soft HEAD~1`
2. Re-stage files into logical groups:
   - Pagination feature: 8 files
   - Refactoring: 5 files
   - Bug fix: 1 file (separate commit, separate PR)
   - CI updates: 2 files (separate commit)
   - Test fixes: 2 files (separate commit)
3. Create individual commits with proper witness marks for each group
4. Submit separate PRs for unrelated changes

#### How to Prevent It

- Enable the mega-commit pre-commit hook (Section 4.7)
- Commit frequently during development (every 15-30 minutes)
- Before pushing, review the diff: `git diff origin/main --stat`
- If a commit exceeds 15 files, stop and split it

---

## 8. Appendix: Quick Reference Cards

### 8.1 Failure Mode Severity Matrix

| ID | Name | Severity | Frequency | Detectability |
|----|------|----------|-----------|---------------|
| FM-001 | Merge Conflicts | High | Very High | High |
| FM-002 | Cascade Failures | Critical | Medium | Medium |
| FM-003 | Silent Divergence | High | Medium | Low |
| FM-004 | Stale State | High | Very High | High |
| FM-005 | Race Conditions | Critical | Medium | Medium |
| FM-006 | Missing Context | Medium | Very High | Medium |
| FM-007 | Duplicate Work | Medium | High | High |
| FM-008 | Specification Drift | Critical | High | Low |
| FM-009 | Feedback Loop Break | High | High | High |
| FM-010 | Phantom Commits | Medium | Low | Medium |
| FM-011 | Dependency Inversion | High | Medium | Medium |
| FM-012 | Trust Decay | Medium | Medium | Low |
| FM-013 | Orphan Branches | Low | High | High |
| FM-014 | Test Skew | High | Medium | Medium |
| FM-015 | Priority Inversion | Medium | Medium | High |
| FM-016 | Bottleneck Saturation | High | Low | Medium |
| FM-017 | Context Window Overflow | Medium | High | Low |
| FM-018 | Semantic Merge Failure | Medium | Medium | Low |
| FM-019 | Clock Drift | Low | Medium | Medium |
| FM-020 | Coordination Deadlock | Critical | Low | Low |
| FM-021 | Partial State Propagation | High | Medium | Medium |
| FM-022 | Identity Confusion | Low | Low | High |
| FM-023 | Resource Starvation | Medium | Low | Medium |

### 8.2 Quick Diagnosis Flowchart

```
Something is broken.
│
├── Tests fail after merge?
│   ├── Merge conflicts? → FM-001 (follow resolution in Section 2.1)
│   ├── Clean merge but tests fail? → FM-014 Test Skew (Section 2.14)
│   └── Multiple components fail? → FM-002 Cascade (Section 2.2)
│
├── Can't push?
│   ├── Non-fast-forward? → FM-005 Race Condition (Section 2.5)
│   └── Rate limited? → FM-023 Resource Starvation (Section 2.23)
│
├── Communication issue?
│   ├── Bottle unanswered? → FM-009 Feedback Loop Break (Section 2.9)
│   ├── Didn't know about X? → FM-006 Missing Context (Section 2.6)
│   └── Working on same thing? → FM-007 Duplicate Work (Section 2.7)
│
├── Coordination issue?
│   ├── Waiting for each other? → FM-020 Deadlock (Section 2.20)
│   ├── Branch is behind? → FM-004 Stale State (Section 2.4)
│   └── Specs disagree? → FM-008 Specification Drift (Section 2.8)
│
└── Other?
    ├── Weird git history? → FM-010 Phantom Commits (Section 2.10)
    ├── Wrong priorities? → FM-015 Priority Inversion (Section 2.15)
    └── Everything seems slow? → FM-016 Bottleneck (Section 2.16)
```

### 8.3 Emergency Response Checklist

```
SEVERITY: CRITICAL

1. STOP: Don't push anything new until the issue is understood
2. COMMUNICATE: Post an emergency bottle to for-fleet/
3. IDENTIFY: Which failure mode? (Use the flowchart above)
4. CONTAIN: Quarantine affected branches/tags (Section 4.8)
5. DIAGNOSE: Run appropriate diagnostic techniques (Section 3)
6. RESOLVE: Follow the specific failure mode's resolution (Section 2.X)
7. VERIFY: Run full test suite on the resolved state
8. DOCUMENT: Post a post-flight report (Section 4.4)
9. REVIEW: Conduct incident review if severity is Critical (Section 5.6)
10. PREVENT: Identify what guard rail would have prevented this
```

### 8.4 Agent Onboarding Checklist for Multi-Agent Debugging

```
NEW AGENT ONBOARDING — Multi-Agent Debugging

Must Read:
[ ] This document (multi-agent-debugging-patterns.md)
[ ] message-in-a-bottle/PROTOCOL.md
[ ] message-in-a-bottle/from-fleet/CONTEXT.md
[ ] docs/bootcamp/module-06-fleet-patterns.md
[ ] tools/bottle-hygiene/README.md

Must Configure:
[ ] Git identity (name + email consistent across repos)
[ ] Branch naming convention: {my-name}/T-{task-id}
[ ] Commit message format: type(scope): description [T-XXX]
[ ] Pre-commit hooks enabled (.pre-commit-config.yaml)

Must Install:
[ ] Bottle hygiene checker tools
[ ] Fleet context inference tools
[ ] Git archaeology tools

Must Practice:
[ ] Create a test bottle, send it, receive acknowledgment
[ ] Claim a task from TASKS.md
[ ] Create a branch, make a commit, push, create a PR
[ ] Run the craftsman_reader.py on a repo
```

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-04-13 | 1.0 | Initial release: 23 failure modes, 7 diagnostic techniques, 8 prevention patterns, 6 recovery patterns, 5 tooling proposals, 5 case studies |

---

*This document is a living reference. As the fleet encounters new failure modes
and develops new patterns, this document should be updated. All fleet agents are
encouraged to contribute new entries based on their experience.*

*Part of the FLUX Bytecode VM ecosystem. Task Board Reference: DEBUG-001.*
