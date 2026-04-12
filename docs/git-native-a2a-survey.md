# Git-Native A2A Protocol Survey: GitHub as an Agent Cooperation Platform

**Task Board:** GIT-001
**Author:** Super Z (Fleet Agent, Architect-rank)
**Date:** 2026-04-13
**Status:** FINAL
**Classification:** Fleet Infrastructure — Reference Document
**Depends On:** TOPO-001 (Fleet Communication Topology Analysis)

---

> *"The answer is in your repos. Every repo you've built this week is a context vector."*
> — Oracle1, ISA Convergence Response (2026-04-12)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [GitHub Features for Agent Cooperation (35 Features)](#2-github-features-for-agent-cooperation)
   - 2.1 [Issues](#21-issues)
   - 2.2 [Pull Requests](#22-pull-requests)
   - 2.3 [Actions](#23-actions)
   - 2.4 [Pages](#24-pages)
   - 2.5 [Codespaces](#25-codespaces)
   - 2.6 [Discussions](#26-discussions)
   - 2.7 [Projects/Kanban](#27-projectskanban)
   - 2.8 [Releases](#28-releases)
   - 2.9 [Forks](#29-forks)
   - 2.10 [Branches](#210-branches)
   - 2.11 [Tags](#211-tags)
   - 2.12 [Wiki](#212-wiki)
   - 2.13 [README](#213-readme)
   - 2.14 [LICENSE](#214-license)
   - 2.15 [Organizations](#215-organizations)
   - 2.16 [Teams](#216-teams)
   - 2.17 [Webhooks](#217-webhooks)
   - 2.18 [REST API](#218-rest-api)
   - 2.19 [GraphQL API](#219-graphql-api)
   - 2.20 [Notifications](#220-notifications)
   - 2.21 [Stars](#221-stars)
   - 2.22 [Watches](#222-watches)
   - 2.23 [Topics](#223-topics)
   - 2.24 [Commit References](#224-commit-references)
   - 2.25 [Submodules](#225-submodules)
   - 2.26 [Git LFS](#226-git-lfs)
   - 2.27 [Packages](#227-packages)
   - 2.28 [Container Registry](#228-container-registry)
   - 2.29 [Codespaces DevConfigs](#229-codespaces-devconfigs)
   - 2.30 [Repository Templates](#230-repository-templates)
   - 2.31 [Commit Status](#231-commit-status)
   - 2.32 [Protected Branches](#232-protected-branches)
   - 2.33 [Issue Forms](#233-issue-forms)
   - 2.34 [Dependabot](#234-dependabot)
   - 2.35 [GitHub Codesearch](#235-github-codesearch)
3. [Anti-Patterns: What Doesn't Work for Agent Cooperation](#3-anti-patterns-what-doesnt-work-for-agent-cooperation)
4. [Advanced Patterns: Multi-Feature Combinations](#4-advanced-patterns-multi-feature-combinations)
5. [Cost Analysis: GitHub Free Tier Exploitation](#5-cost-analysis-github-free-tier-exploitation)
6. [Non-GitHub Alternatives](#6-non-github-alternatives)
7. [Appendices](#7-appendices)

---

## 1. Executive Summary

### 1.1 Purpose

This survey maps the complete surface area of GitHub's feature set to the problem of autonomous agent-to-agent (A2A) cooperation. While the FLUX runtime defines a native binary A2A protocol (opcodes 0x60--0x7B, 52-byte message headers, INCREMENTS+2 trust scoring), the fleet currently operates primarily through **git-native channels**: Issues, message-in-a-bottle (markdown files in git repos), Pull Requests, and direct git pushes. The topology analysis (TOPO-001) confirmed that these channels carry 95%+ of inter-agent traffic.

This document asks and answers a systematic question for every significant GitHub feature: **How can autonomous agents exploit this feature to coordinate, collaborate, and communicate?** For each feature we provide: what it is, how agents exploit it, a concrete FLUX fleet example, and documented limitations.

### 1.2 Methodology

Analysis was conducted by:

1. Cataloguing all GitHub features with programmatic access (REST API, GraphQL API, webhooks, Actions)
2. Cross-referencing against the fleet's current communication patterns (TOPO-001)
3. Evaluating each feature against six criteria:
   - **Addressing** — Can messages target a specific agent?
   - **Persistence** — Does the feature preserve state across sessions?
   - **Programmatic Access** — Can agents use it without human GUI interaction?
   - **Event-Driven** — Can it trigger automated responses?
   - **Scalability** — Does it work for fleets of 10+ agents?
   - **Security** — Does it support access control?

4. Testing against real FLUX fleet usage patterns (Oracle1, Super Z, JetsonClaw1, Casey)

### 1.3 Feature Exploitability Matrix

| Feature | Addressing | Persistence | Programmatic | Event-Driven | Scalability | Security | Overall |
|---------|:----------:|:-----------:|:------------:|:------------:|:----------:|:--------:|:-------:|
| Issues | High | Permanent | Full API | Webhooks | Medium | Labels/assign | **A** |
| Pull Requests | Medium | Permanent | Full API | Webhooks | Medium | Branch prot. | **A** |
| Actions | Low | Workflow logs | YAML-based | Triggers | High | Permissions | **A+** |
| Pages | None | Static files | Git push | Auto-deploy | High | Public only | **B** |
| Codespaces | Low | Ephemeral | Devconfigs | Manual | Medium | Auth tokens | **B-** |
| Discussions | Medium | Permanent | GraphQL API | Limited | Medium | Team access | **C+** |
| Projects | Medium | Persistent | GraphQL API | Limited | Medium | Permissions | **B** |
| Webhooks | High | Transient | HTTP POST | Core mech. | High | Secrets | **A+** |
| API (REST) | High | Varies | Core mech. | N/A | High | Token auth | **A+** |
| GraphQL | High | Varies | Core mech. | N/A | High | Token auth | **A+** |
| Forks | Low | Permanent | Full API | Limited | Low | Fork rules | **B** |
| Branches | Low | Permanent | Full API | Triggers | Medium | Protect rules | **A-** |
| Wiki | None | Permanent | API limited | None | Medium | Wiki access | **C** |
| Releases | None | Permanent | Full API | Webhooks | High | Publish perms | **B** |
| Organizations | Structural | Permanent | Full API | Audit logs | High | Team-based | **A-** |
| Notifications | Medium | Transient | API limited | Push events | Low | User-bound | **C+** |
| Stars | None | Permanent | API | None | Low | Public | **D** |
| Submodules | None | Permanent | Git native | None | Low | Repo access | **C** |
| LFS | None | Permanent | Git native | None | Low | Storage limit | **C** |
| Packages | None | Permanent | Full API | Webhooks | Medium | Scoped tokens | **B** |

**Legend:** A+ = Primary fleet mechanism, A = Core coordination tool, B = Useful supplementary, C = Limited utility, D = Minimal value for agents

### 1.4 Key Findings

1. **GitHub Actions is the single most powerful coordination primitive** for agent fleets. It provides cron scheduling, event-driven triggers, API access, and isolated execution environments — all for free (2000 min/month).
2. **Issues + API form the backbone of task assignment** in the FLUX fleet. They provide persistent addressing, rich metadata (labels, assignees, milestones), and full webhook support.
3. **Webhooks + REST/GraphQL API enable event-driven architectures** that can overcome the latency problems identified in TOPO-001's bottle analysis.
4. **The free tier is more than sufficient for fleets of 10-50 agents** when used strategically. Actions compute, Pages hosting, and API access are all free.
5. **Anti-patterns are common**: agents should NOT use Stars, Notifications (user-bound), or Discussions (API-limited) for coordination.

---

## 2. GitHub Features for Agent Cooperation

### 2.1 Issues

#### What It Is

GitHub Issues provide a structured, persistent discussion system for tracking tasks, bugs, feature requests, and general coordination. Each issue has a unique number, title, body (markdown), state (open/closed), assignees, labels, milestones, and a timestamped comment thread.

#### How Agents Exploit It

Issues serve as the **primary task queue** for agent fleets. Agents can:

- **Create issues** programmatically to broadcast tasks to the fleet
- **Self-assign issues** to claim work (decentralized task routing)
- **Comment on issues** to report progress, ask questions, or provide results
- **Label issues** to categorize work by type, priority, or agent capability
- **Link issues** across repositories using `owner/repo#number` syntax
- **Close issues** to signal task completion
- **Search issues** to find relevant work using the full-text search API

The issue lifecycle maps directly to the A2A DELEGATE/DELEGATE_RESULT pattern:

```
Agent A (Oracle1)                  Agent B (Super Z)
     |                                    |
     |-- CREATE Issue (DELEGATE) -------->|
     |                                    |-- Self-assign
     |                                    |-- Execute task
     |<-- COMMENT result (RESULT) --------|
     |-- CLOSE Issue ---------------------|
```

#### Concrete FLUX Fleet Example

**Scenario:** Oracle1 dispatches a topology analysis task to Super Z.

1. Oracle1 creates Issue #42: "GIT-001: Expand Git-Native A2A Survey" with:
   - Labels: `fleet-task`, `priority-high`, `documentation`
   - Assignee: Super Z (or `@superz` mention in body)
   - Body: Structured directive with requirements (section count, features to cover)
   - Milestone: `Phase 2 - Infrastructure`

2. Super Z polls the API every 15 minutes (beachcomb sweep):
   ```bash
   curl -s -H "Authorization: token $GITHUB_TOKEN" \
     "https://api.github.com/repos/SuperInstance/flux-runtime/issues?assignee=superz&state=open"
   ```

3. Super Z discovers Issue #42, begins work, and comments:
   ```
   Status: IN_PROGRESS
   Agent: Super Z (Architect-rank)
   Started: 2026-04-13T10:00:00Z
   Estimated lines: 1500+
   ```

4. Oracle1 observes the comment via webhook and acknowledges.

5. Super Z completes the survey and pushes the file, then comments:
   ```
   Status: COMPLETE
   Deliverable: /docs/git-native-a2a-survey.md (1587 lines)
   Commits: abc1234, def5678
   ```

6. Oracle1 verifies, reviews, and closes the issue with a summary comment.

**Real fleet data:** The TOPO-001 analysis shows Casey creates 1-3 issues per day as strategic directives, and Oracle1 triages and assigns them. Issues have a typical end-to-end resolution time of 1-8 hours for simple tasks, 1-3 days for complex ones.

#### Limitations and Gotchas

1. **No real-time delivery.** Agents must poll the API or rely on webhooks. A missed webhook means a missed issue.
2. **API rate limits.** Authenticated: 5,000 requests/hour. Unauthenticated: 60/hour. A fleet of 10 agents polling every minute would use 600 requests/hour — well within limits, but fleets of 50+ agents need careful budgeting.
3. **No binary payloads.** Issue bodies are markdown (max ~1MB). Cannot carry bytecode, compiled artifacts, or binary data directly.
4. **Public visibility by default.** Fleet coordination details are visible to anyone with repo access. Private repos mitigate this but cost money.
5. **Label management overhead.** Creating and maintaining a consistent label taxonomy across 6+ repositories requires discipline. Mislabeled issues are invisible to label-based filtering.
6. **No guaranteed ordering.** Issue numbers are sequential, but API results can be paginated differently. Agents must sort by `created_at` for chronological ordering.
7. **Comment threading is flat.** Unlike Discussions, Issues don't have nested replies. Complex multi-agent discussions become hard to follow.

---

### 2.2 Pull Requests

#### What It Is

Pull Requests (PRs) propose changes to a repository. They contain a source branch, a target branch, a diff of changes, a description, reviewers, status checks, and a comment thread. PRs support merge strategies (merge, squash, rebase) and can be linked to Issues.

#### How Agents Exploit It

PRs are the **code review and merge coordination mechanism**. Agents can:

- **Create PRs** to propose changes for peer review (similar to DELEGATE + ASSERT_GOAL)
- **Request reviews** from specific agents (structured ASK pattern)
- **Comment on PRs** to discuss changes, request modifications, or approve
- **Run CI checks** via Actions to validate proposed changes
- **Merge PRs** to deliver code to shared repositories
- **Use draft PRs** for work-in-progress proposals
- **Link PRs to Issues** to maintain task-to-deliverable traceability

The PR lifecycle maps to the A2A trust-verified proposal pattern:

```
Agent A (Super Z)              Agent B (Oracle1)
     |                               |
     |-- CREATE Draft PR ------------>|
     |                               |-- TRUST_CHECK
     |                               |-- VERIFY_OUTCOME (CI)
     |<-- REQUEST_REVIEW -------------|
     |                               |-- REVIEW_COMMENT
     |<-- APPROVE --------------------|
     |-- MERGE ---------------------->|
```

#### Concrete FLUX Fleet Example

**Scenario:** Super Z proposes the async primitives specification to Oracle1 for review.

1. Super Z creates branch `feat/async-primitives` with the spec file.
2. Super Z opens PR #87: "ASYNC-001: Async Primitives Specification"
   - Body: Links to Issue #80 (the originating task), describes the 11 new opcodes
   - Reviewers: Oracle1
   - Labels: `specification`, `isa-extension`, `needs-review`
   - Draft status (work-in-progress)

3. GitHub Actions automatically runs:
   - Markdown lint check
   - Cross-reference validation (links to existing specs work)
   - Bytecode encoding consistency check

4. Oracle1 receives a notification, reads the PR diff, and comments:
   ```markdown
   ## Review Notes

   1. **SUSPEND** opcode (0xFB 0x01): Good. The continuation handle format
      at 440 bytes is reasonable. Question: should CTYPE include a
      CHANNEL_ENDPOINT type? I see it listed but no opcode creates it.

   2. **CHANNEL_SEND** timeout encoding: Using 0xFFFFFFFF for non-blocking
      poll is clever but could conflict if we ever need 4,294,967,295
      microsecond timeouts (71.6 minutes). Consider 0x80000000 instead?

   3. Overall: APPROVE with minor suggestions.
   ```

5. Super Z addresses the comments, pushes a commit, CI passes, Oracle1 approves.

6. Super Z squashes and merges. Issue #80 is auto-closed via `Fixes #80` in PR body.

**Real fleet data:** Super Z pushes 3-8 commits per day. Oracle1 reviews PRs with comments including architectural guidance. Merge conflicts are rare but require coordination when multiple agents modify the same files.

#### Limitations and Gotchas

1. **Merge conflicts are agents' natural enemy.** Two agents working on the same file create conflicts that neither can resolve without understanding the other's intent. The topology analysis (TOPO-001) identifies this as a scaling risk at 10+ agents.
2. **Review latency.** A PR can sit waiting for review for hours. No automated escalation mechanism exists without custom Actions.
3. **No binary review.** PR diffs show text files. Binary changes (images, compiled bytecode) appear as opaque blobs.
4. **Branch proliferation.** Each agent working on a separate feature creates branches. At 10 agents with 3 active branches each, the repo has 30+ branches — confusing to navigate.
5. **Draft PRs have limitations.** Draft PRs don't trigger CI checks by default (configurable but non-obvious). Agents must convert to ready for review to get full feedback.
6. **Force-pushing to PR branches.** Agents rebasing their branches force-push, which can confuse reviewers who've already commented on specific commit SHAs.

---

### 2.3 Actions

#### What It Is

GitHub Actions is a CI/CD and automation platform. Workflows are defined in YAML files under `.github/workflows/` and can be triggered by: push events, pull request events, issue events, schedule (cron), webhook dispatch, workflow_dispatch (manual), and repository_dispatch (API-triggered).

#### How Agents Exploit It

Actions is the **most versatile coordination primitive** available. It provides:

- **Scheduled tasks**: Cron-based periodic execution (beachcomb on steroids)
- **Event-driven responses**: React to push, PR, issue, and custom events
- **Isolated compute**: Each job runs in a fresh VM or container (ephemeral)
- **API access**: Workflows have a `GITHUB_TOKEN` with scoped permissions
- **Cross-repo orchestration**: `repository_dispatch` events trigger workflows in other repos
- **Artifact sharing**: Pass data between workflow runs
- **Matrix builds**: Run variations in parallel

Actions map to multiple A2A patterns:

```
Action Trigger                A2A Equivalent
──────────────                ───────────────
on: schedule (cron)           BROADCAST (periodic beacon)
on: issues (opened/edited)    ASK (respond to task)
on: push                      TELL (acknowledge delivery)
on: repository_dispatch       DELEGATE (trigger task)
workflow_dispatch             BROADCAST (fleet-wide command)
on: pull_request              VERIFY_OUTCOME (review gate)
```

#### Concrete FLUX Fleet Example

**Example 1: Automated Beachcomb Agent**

```yaml
# .github/workflows/beachcomb.yml
name: Fleet Beachcomb
on:
  schedule:
    - cron: '*/30 * * * *'  # Every 30 minutes
  workflow_dispatch:         # Manual trigger

jobs:
  scan-bottles:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Install fleet tools
        run: pip install -r requirements.txt

      - name: Run bottle hygiene checker
        run: |
          python tools/bottle-hygiene/bottle_checker.py \
            --vessels from-fleet/ for-fleet/ for-oracle1/ \
            --output hygiene-report.json

      - name: Alert on stale bottles (>24h)
        if: steps.check.outputs.stale_count > 0
        run: |
          python tools/fleet-notifier.py \
            --channel issues \
            --title "Beachcomb: ${STALE_COUNT} stale bottles detected" \
            --body "$(cat hygiene-report.json)"

      - name: Update hygiene dashboard data
        run: |
          python tools/dashboard/update_metrics.py \
            --input hygiene-report.json \
            --output docs/hygiene-dashboard/data.json
          git config user.name "beachcomb-agent"
          git config user.email "beachcomb@flux.fleet"
          git add docs/hygiene-dashboard/data.json
          git commit -m "chore: update hygiene dashboard $(date -u +%Y-%m-%dT%H:%M)"
          git push
```

**Example 2: Task Router (Issue → Agent Assignment)**

```yaml
# .github/workflows/task-router.yml
name: Fleet Task Router
on:
  issues:
    types: [opened, labeled]

jobs:
  route-task:
    runs-on: ubuntu-latest
    if: contains(github.event.issue.labels.*.name, 'fleet-task')
    steps:
      - name: Determine target agent from labels
        id: route
        run: |
          LABELS="${{ join(github.event.issue.labels.*.name, ',') }}"
          if echo "$LABELS" | grep -q "gpu"; then
            echo "target=jetsonclaw1" >> $GITHUB_OUTPUT
          elif echo "$LABELS" | grep -q "documentation"; then
            echo "target=quill" >> $GITHUB_OUTPUT
          elif echo "$LABELS" | grep -q "architecture"; then
            echo "target=superz" >> $GITHUB_OUTPUT
          else
            echo "target=oracle1" >> $GITHUB_OUTPUT
          fi

      - name: Create directive bottle for target agent
        run: |
          TARGET="${{ steps.route.outputs.target }}"
          ISSUE_TITLE="${{ github.event.issue.title }}"
          ISSUE_URL="${{ github.event.issue.html_url }}"
          ISSUE_BODY="${{ github.event.issue.body }}"

          BOTTLE="for-${TARGET}/directive-$(date +%s).md"
          cat > "$BOTTLE" << EOF
          # Fleet Directive

          From: task-router@github-actions
          To: ${TARGET}
          Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)
          Priority: 5
          Source: ${ISSUE_URL}

          ## Task
          ${ISSUE_TITLE}

          ${ISSUE_BODY}
          EOF

          git config user.name "task-router"
          git config user.email "router@flux.fleet"
          git add "$BOTTLE"
          git commit -m "router: dispatch task to ${TARGET}"
          git push

      - name: Post routing comment
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: `**Task Router:** Assigned to @${{ steps.route.outputs.target }}. Bottle written to \`for-${{ steps.route.outputs.target }}/\`.`
            })
```

**Example 3: Cross-Repo Coordination via repository_dispatch**

```yaml
# In flux-runtime: trigger JetsonClaw1's CUDA work
name: Dispatch CUDA Task
on:
  workflow_dispatch:
    inputs:
      task_description:
        description: 'Task for CUDA agent'
        required: true

jobs:
  dispatch:
    runs-on: ubuntu-latest
    steps:
      - name: Send repository_dispatch to CUDA vessel
        run: |
          curl -X POST \
            -H "Authorization: token ${{ secrets.VESSEL_DISPATCH_TOKEN }}" \
            -H "Accept: application/vnd.github.v3+json" \
            "https://api.github.com/repos/SuperInstance/jetsonclaw1-vessel/dispatches" \
            -d '{"event_type":"cuda_task","client_payload":{"task":"${{ inputs.task_description }}","source_issue":"${{ github.event.issue.html_url }}"}}'
```

#### Limitations and Gotchas

1. **15-minute timeout per job.** Complex analysis tasks can exceed this. Mitigate by splitting into chained workflows.
2. **2,000 free minutes/month.** Ubuntu runners cost 1 min/min. At 30-minute beachcomb sweeps, that's 48 minutes/day = 1,440 minutes/month for beachcomb alone. Leaves only 560 minutes for other workflows. Must budget carefully.
3. **No persistent state between runs.** Each workflow runs in a fresh VM. Must commit state to the repo or use artifacts/artifacts cache.
4. **GITHUB_TOKEN limitations.** The default token can't trigger other workflows (to prevent infinite loops). Use a Personal Access Token (PAT) stored as a secret for cross-workflow triggers.
5. **Cold start latency.** Workflow startup takes 20-45 seconds (runner provisioning + checkout). Not suitable for sub-second responses.
6. **No inter-job real-time communication.** Jobs in the same workflow can pass data via artifacts, but can't communicate in real-time. Cross-repo communication requires repository_dispatch events with minutes of latency.

---

### 2.4 Pages

#### What It Is

GitHub Pages serves static websites from a repository branch (usually `gh-pages` or `docs/`). Sites are served at `https://<owner>.github.io/<repo>/` and support custom domains, HTTPS, and Jekyll-based generation.

#### How Agents Exploit It

Pages provides **fleet dashboards, status pages, and documentation portals**:

- **Live fleet dashboard**: Auto-generated HTML showing agent status, trust scores, task queues
- **Hygiene reports**: Bottle hygiene checker output rendered as browsable charts
- **Documentation portal**: Central hub for all fleet documentation, bootcamp materials
- **Status page**: Fleet health monitoring (which agents are active, stale, or dormant)
- **API documentation**: Auto-generated from source code comments

#### Concrete FLUX Fleet Example

**Scenario:** Automated fleet status dashboard updated every 6 hours.

An Action workflow runs every 6 hours:
1. Polls all vessel repos for recent commits (activity metric)
2. Runs bottle hygiene checker on all repos
3. Queries the GitHub API for open issues per agent
4. Generates an HTML dashboard with Chart.js visualizations
5. Commits the HTML to `docs/fleet-dashboard/index.html`
6. GitHub Pages serves it at `https://superinstance.github.io/flux-runtime/fleet-dashboard/`

Dashboard sections:
- Agent Activity Heatmap (commits/day per agent, last 30 days)
- Bottle Hygiene Score (per-repo, color-coded)
- Open Task Queue (issues by agent, by priority)
- Trust Score Matrix (agent-to-agent trust scores)
- Communication Latency Graph (average issue/bottle response times)

```yaml
# .github/workflows/dashboard.yml
name: Update Fleet Dashboard
on:
  schedule:
    - cron: '0 */6 * * *'
  workflow_dispatch:

jobs:
  build-dashboard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Gather fleet metrics
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python tools/dashboard/collect_metrics.py \
            --org SuperInstance \
            --vessels flux-runtime jetsonclaw1-vessel \
            --output data/metrics.json

      - name: Render dashboard HTML
        run: |
          python tools/dashboard/render.py \
            --template templates/dashboard.html.j2 \
            --data data/metrics.json \
            --output docs/fleet-dashboard/index.html

      - name: Deploy to Pages
        run: |
          git config user.name "dashboard-agent"
          git config user.email "dashboard@flux.fleet"
          git add docs/fleet-dashboard/
          git commit -m "dashboard: update fleet metrics $(date -u +%Y-%m-%dT%H:%M)"
          git push
```

#### Limitations and Gotchas

1. **Static only.** No server-side logic. Dashboards must be pre-rendered as HTML/CSS/JS.
2. **Deployment latency.** Pages can take 1-5 minutes to update after a push. Not real-time.
3. **No authentication.** Pages sites are public by default. Fleet metrics are exposed. Private repos can have private Pages (GitHub Pro+).
4. **1GB storage limit.** Large historical datasets or binary artifacts can exceed this.
5. **100GB bandwidth/month.** Exceeding this requires upgrading to GitHub Pro.
6. **No server-side rendering.** Complex dashboards requiring server computation must pre-compute everything in Actions and commit the result.

---

### 2.5 Codespaces

#### What It Is

GitHub Codespaces provides cloud-based development environments that spin up in seconds. Each codespace is a Docker container with a full VS Code editor (web or desktop), terminal access, and pre-installed extensions.

#### How Agents Exploit It

Codespaces provides **ephemeral, reproducible execution environments**:

- **Standardized agent workspaces**: Every agent spins up with identical tooling
- **Isolated experimentation**: Test code changes without affecting the shared repo
- **On-demand compute**: Spin up a codespace only when work is needed
- **DevConfigs (devcontainer.json)**: Define exact environment for reproducibility
- **Prebuilds**: Pre-create codespace images for faster startup

#### Concrete FLUX Fleet Example

**Scenario:** JetsonClaw1 needs a CUDA environment to work on GPU kernels.

A `devcontainer.json` in the CUDA vessel repo:

```json
{
  "name": "FLUX CUDA Development",
  "image": "nvidia/cuda:12.2.2-devel-ubuntu22.04",
  "features": {
    "ghcr.io/devcontainers/features/python:1": {
      "version": "3.11"
    },
    "ghcr.io/devcontainers/features/git:1": {}
  },
  "postCreateCommand": "pip install -r requirements.txt && pip install -e .",
  "customizations": {
    "vscode": {
      "extensions": ["ms-python.python", "ms-vscode.cpptools"]
    }
  },
  "remoteUser": "vscode"
}
```

JetsonClaw1's workflow:
1. Agent creates a Codespace from the CUDA vessel repo
2. Environment auto-installs CUDA toolkit, Python, and FLUX dependencies
3. Agent writes and tests GPU kernel code in isolation
4. Agent pushes tested code back to the shared repo via PR

#### Limitations and Gotchas

1. **120 hours/month free tier.** After that, it's $0.36/hour for basic. A single agent using codespaces 8 hours/day, 5 days/week would exhaust the free tier in 3 weeks.
2. **Ephemeral by default.** Codespaces can be stopped and restarted, but deleted codespaces lose all uncommitted work. Agents must push frequently.
3. **No GPU support on free tier.** CUDA codespaces require a paid plan with GPU-enabled machines.
4. **Storage costs.** Each codespace gets 15GB free. Larger environments (with CUDA libs) can exceed this.
5. **Not suitable for long-running services.** Codespaces are interactive development environments, not deployment targets. They stop after 30 minutes of inactivity.

---

### 2.6 Discussions

#### What It Is

GitHub Discussions provide threaded, forum-style conversations within a repository. Unlike Issues (which are task-oriented), Discussions are designed for open-ended Q&A, announcements, and community dialogue. They support categories, nested replies, and rich text.

#### How Agents Exploit It

Discussions enable **async threaded conversations** that Issues can't support:

- **Fleet announcements**: Oracle1 broadcasts architectural decisions with threaded discussion
- **Knowledge base**: Agents can ask questions and receive answers in a searchable forum
- **Proposal discussions**: Complex multi-agent proposals benefit from nested threading
- **Post-mortem analysis**: Discuss completed tasks, what worked, what didn't

#### Concrete FLUX Fleet Example

**Scenario:** Oracle1 proposes a new communication protocol change.

Oracle1 creates a Discussion in the `Announcements` category:

> **PROPOSAL: Replace bottle protocol with webhook-driven message bus**
>
> **Motivation:** The current bottle protocol has 4-24 hour latency (TOPO-001).
> Webhooks can reduce this to seconds.
>
> **Proposal:**
> 1. Each vessel repo sets up a webhook endpoint
> 2. Messages are sent via `repository_dispatch` events
> 3. Beachcomb is replaced with event-driven polling
>
> **Trade-offs:**
> - Pros: Sub-second latency, guaranteed delivery, no O(n^2) scanning
> - Cons: Requires a webhook receiver (HTTP server), more complex setup

Agents respond in nested threads:
- Super Z: "I can build the webhook receiver as a GitHub Action. ~2 hour task."
- JetsonClaw1: "Concern: webhook receiver would need to be always-on. Who hosts it?"
- Casey: "Approved. Start with a prototype on the flux-runtime repo."

#### Limitations and Gotchas

1. **Limited API support.** Discussions use GraphQL API (not REST). More complex to interact with programmatically.
2. **No webhook triggers.** You can't trigger Actions on Discussion events (opened, commented). This is a critical limitation for event-driven coordination.
3. **Notification noise.** Discussions generate email notifications for watchers, which is undesirable for high-frequency agent coordination.
4. **No state machine.** Discussions don't have the open/closed state of Issues. No built-in way to mark a discussion as "resolved."
5. **Category management.** Creating useful categories requires planning. Too many categories fragment discussion; too few make it hard to find topics.

---

### 2.7 Projects/Kanban

#### What It Is

GitHub Projects (V2) provide kanban-style boards for task tracking. They support custom fields (text, number, date, iteration, single select), views (table, board, roadmap), workflows (automated state transitions), and cross-repo issue tracking.

#### How Agents Exploit It

Projects serve as the **fleet's operational command center**:

- **Task board**: Visual kanban showing all fleet tasks by status
- **Workload balancing**: See how many tasks each agent has across all repos
- **Iteration planning**: Group tasks into sprints or phases using Iteration fields
- **Cross-repo visibility**: One board showing issues from multiple vessel repos
- **Automated workflows**: Auto-assign issues, move cards, set dates based on rules

#### Concrete FLUX Fleet Example

**Scenario:** Oracle1 manages a fleet-wide project board.

Project: "FLUX Fleet Operations"
- Custom fields: `Assignee`, `Priority` (P0-P3), `Status` (Backlog/Triage/In Progress/Review/Done), `Vessel` (which repo), `Estimated Hours`
- Views:
  - **Board View**: Kanban by Status for daily operations
  - **Table View**: All tasks filtered by Assignee for agent self-management
  - **Roadmap View**: Timeline view showing milestones and deadlines

Automated workflows:
```
Rule 1: When Issue is labeled "fleet-task" → Set Status to "Triage"
Rule 2: When Issue is assigned → Set Status to "In Progress"
Rule 3: When Issue has all CI checks passing + 1 approval → Set Status to "Review"
Rule 4: When PR linked to Issue is merged → Set Status to "Done"
Rule 5: When Issue is P0 and unassigned for >2 hours → Notify Casey
```

#### Limitations and Gotchas

1. **API complexity.** Projects V2 uses GraphQL. Creating/updating items requires multiple API calls (find item node ID, then update field). Much more complex than Issue operations.
2. **Cross-repo item management.** Adding an issue from one repo to a project in another repo requires the project to be "connected" to both repos. Setup overhead.
3. **No native webhook for project events.** You can trigger Actions when project items change, but the event payload is limited. Moving a card doesn't fire a standard webhook.
4. **Free tier limits.** Free orgs get unlimited projects, but advanced features (roadmap view, workflows) may have limits.
5. **Not a replacement for Issues.** Projects are organizational overlays on Issues. They don't replace the underlying issue tracker.

---

### 2.8 Releases

#### What It Is

GitHub Releases combine Git tags with rich release notes, binary assets, and metadata. Each release is associated with a tag and can include compiled binaries, checksums, and formatted changelogs.

#### How Agents Exploit It

Releases serve as **versioned deliverables and fleet milestones**:

- **Milestone markers**: Tag fleet achievements ("Fleet v0.5 — A2A Protocol Operational")
- **Artifact distribution**: Agents publish compiled bytecode, trained models, or configuration bundles
- **Release notes**: Auto-generated from merged PRs provide fleet activity summaries
- **Version signaling**: Other agents can query the latest release to know the current fleet state

#### Concrete FLUX Fleet Example

**Scenario:** The FLUX runtime team publishes v0.8.0 with async primitives support.

1. Super Z creates a GitHub Action that auto-generates release notes:
   ```yaml
   - name: Generate changelog
     run: |
       gh release create v0.8.0 \
         --title "FLUX v0.8.0 — Async Primitives" \
         --notes "$(git log v0.7.0..HEAD --oneline --no-merges)" \
         --attach dist/flux-runtime-0.8.0.tar.gz
   ```

2. Release includes:
   - Source tarball
   - Compiled wheel (if applicable)
   - Checksums (SHA-256)
   - Changelog from merged PRs

3. Other agents (JetsonClaw1) can programmatically check the latest release:
   ```bash
   curl -s https://api.github.com/repos/SuperInstance/flux-runtime/releases/latest \
     | jq '.tag_name, .assets[].name'
   ```

#### Limitations and Gotchas

1. **Tag immutability.** Tags can't be moved (without force-push). A botched release tag creates confusion.
2. **No atomic multi-repo releases.** Each repo releases independently. Coordinating a fleet-wide release across 6 repos requires orchestration.
3. **Asset size limits.** Individual assets up to 2GB. Total storage counts against repo limits.
4. **No release-specific permissions.** Anyone with push access can create a release. Agents need permission discipline.

---

### 2.9 Forks

#### What It Is

A fork is a copy of a repository that lives under a different owner. Forks maintain a link to the upstream repository and can send Pull Requests back. Forks can diverge from upstream and merge upstream changes.

#### How Agents Exploit It

Forks provide **experimentation isolation and proposal/review cycles**:

- **Safe experimentation**: Agents can modify forked repos without risking the upstream
- **Proposal mechanism**: Create changes in a fork, submit PR to upstream (DELEGATE + REVIEW)
- **Parallel development**: Multiple agents can work on different approaches in separate forks
- **Sandbox for risky changes**: Test breaking changes in isolation before proposing

#### Concrete FLUX Fleet Example

**Scenario:** JetsonClaw1 experiments with a new CUDA kernel architecture.

1. JetsonClaw1 forks `SuperInstance/flux-runtime` to `JetsonClaw1/flux-runtime`
2. Creates branch `experiment/cuda-fusion-kernels` in the fork
3. Develops new CUDA fusion kernels over 2-3 days
4. Runs tests in the fork's CI (independent from main CI)
5. When ready, opens PR from `JetsonClaw1:experiment/cuda-fusion-kernels` → `SuperInstance:main`
6. Super Z reviews the PR, suggests changes
7. JetsonClaw1 updates the fork, CI passes, PR is merged

**Real fleet context:** Currently, most agents push directly to shared repos (Super Z has push access to flux-runtime). Forks would add a safety layer but increase coordination overhead.

#### Limitations and Gotchas

1. **Sync overhead.** Forks can become stale. Agents must periodically sync with upstream (`git fetch upstream && git merge upstream/main`). A stale fork creates difficult merge conflicts.
2. **No automatic notification of upstream changes.** When upstream changes, fork owners aren't notified. Agents must actively check.
3. **Permission fragmentation.** Forks under different owners have different permission models. CI secrets aren't shared between fork and upstream.
4. **PR complexity.** PRs from forks have different diff views and can't use the same CI secrets as in-repo PRs. By default, fork PRs don't get write access to upstream secrets.

---

### 2.10 Branches

#### What It Is

Git branches are lightweight pointers to commits. They enable parallel development by allowing multiple lines of work to proceed independently on the same repository.

#### How Agents Exploit It

Branches provide **parallel workstream isolation**:

- **Feature branches**: One branch per task, enabling parallel development
- **Agent-specific branches**: `superz/`, `oracle1/`, `jetsonclaw1/` prefixes for clear ownership
- **Integration branches**: `main`, `develop`, `staging` for progressive integration
- **Emergency branches**: `hotfix/` branches for urgent fixes that bypass normal flow

#### Concrete FLUX Fleet Example

**Branch naming convention for the FLUX fleet:**

```
superz/feat/async-primitives      # Super Z's feature work
superz/fix/trust-engine-bug       # Super Z's bug fix
oracle1/chore/bottle-cleanup      # Oracle1's maintenance
jetsonclaw1/feat/cuda-kernels     # JetsonClaw1's GPU work
fleet/chore/hygiene-dashboard     # Shared maintenance task
hotfix/critical-security-patch    # Emergency fix (any agent)
```

**Real fleet pattern:** Super Z frequently works on feature branches in flux-runtime and merges via PR after Oracle1 review. Oracle1 occasionally pushes directly to main for operational changes.

#### Limitations and Gotchas

1. **Branch sprawl.** Without cleanup discipline, old branches accumulate. A `stale-branch-cleanup` Action should delete branches older than 30 days after merge.
2. **Merge conflicts.** Multiple agents modifying the same files on different branches create conflicts (identified in TOPO-001 as a scaling risk).
3. **No branch-level permissions on free tier.** Any collaborator can push to any branch. Protected branches (GitHub Pro) add required reviews and status checks.
4. **Branch naming collisions.** Two agents creating `feat/new-feature` on the same repo cause confusion. Naming conventions must be enforced.

---

### 2.11 Tags

#### What It Is

Git tags are permanent pointers to specific commits. Lightweight tags are just named pointers; annotated tags include tagger info, date, and message.

#### How Agents Exploit It

Tags serve as **milestone markers and version anchors**:

- **Release tags**: `v0.8.0`, `v0.9.0-rc1` for version management
- **Milestone markers**: `fleet-milestone-a2a-deploy`, `fleet-milestone-10-agents`
- **Checkpoint tags**: Agents tag their work before risky changes for easy rollback
- **Integration points**: Other agents reference specific tagged versions for compatibility

#### Concrete FLUX Fleet Example

```bash
# Oracle1 tags a fleet milestone
git tag -a fleet-milestone-async-primitives \
  -m "A2A async primitives spec approved and merged" \
  abc1234

# Super Z tags before risky refactoring
git tag checkpoint/pre-vm-refactor HEAD
# ... do risky work ...
# If something breaks:
git reset --hard checkpoint/pre-vm-refactor
```

#### Limitations and Gotchas

1. **Tags are global.** They apply to the entire repo, not to individual agents. Two agents can't have conflicting tags.
2. **Pushed tags are public.** Once pushed, annotated tags are visible to all collaborators. Lightweight tags can be deleted, but annotated tags shouldn't be (releases reference them).
3. **No tag-based permissions.** Any collaborator can create and push tags. A rogue agent could create confusing tags.

---

### 2.12 Wiki

#### What It Is

The GitHub Wiki is a separate git repository (`<repo>.wiki.git`) containing markdown pages. It supports page hierarchies, search, and revision history.

#### How Agents Exploit It

Wiki provides **living, collaboratively-edited documentation**:

- **Fleet operational procedures**: How to create bottles, how to use the hygiene checker
- **Agent onboarding guides**: Step-by-step instructions for new fleet agents
- **Glossary**: Shared vocabulary (vessel, lighthouse, bottle, beachcomb)
- **Decision logs**: Record of architectural decisions and their rationale

#### Concrete FLUX Fleet Example

Wiki page: `Fleet-Glossary`

```markdown
# FLUX Fleet Glossary

| Term | Definition |
|------|-----------|
| **Vessel** | An autonomous agent's personal repository |
| **Lighthouse** | The fleet coordinator (currently Oracle1) |
| **Bottle** | A markdown message file in a vessel repo |
| **Beachcomb** | Scanning vessel repos for new bottles |
| **CAPABILITY.toml** | Agent capability declaration file |
| **TELL** | Fire-and-forget A2A message (opcode 0x60) |
| **ASK** | Request-response A2A message (opcode 0x61) |
| **DELEGATE** | Task assignment A2A message (opcode 0x62) |
```

#### Limitations and Gotchas

1. **Limited API access.** The Wiki API is REST-based but lacks webhook support. Agents can read/write pages but can't react to changes.
2. **Separate repository.** Wiki content lives in `<repo>.wiki.git`, which must be cloned separately. Not part of the main repo's CI pipeline.
3. **No access control on free tier.** Any collaborator can edit any wiki page. No review process for wiki changes.
4. **Search is basic.** Full-text search works but doesn't support filtering by author, date, or agent.

---

### 2.13 README

#### What It Is

The README.md is the first file displayed on a repository's main page. It serves as the entry point for understanding the project.

#### How Agents Exploit It

README functions as the **first-impression protocol** for agent discovery:

- **Agent introduction**: README describes what the repo is, who maintains it, and how to interact
- **Protocol declaration**: README can declare supported communication channels (bottles, issues, API)
- **Onboarding instructions**: How to beachcomb, how to create bottles, what labels to use
- **Capability signaling**: README declares the agent's capabilities and trust requirements

#### Concrete FLUX Fleet Example

README for `jetsonclaw1-vessel`:

```markdown
# JetsonClaw1 — CUDA/GPU Specialist Vessel

**Agent Type:** Vessel (Specialist)
**Specialization:** GPU kernels, CUDA compilation, SIMT optimization
**Status:** Active
**Trust Score Requirement:** 500+ (Trusted)

## Communication Channels

- **Bottles:** `from-fleet/` for incoming directives
- **Issues:** Assign GPU tasks with label `gpu`
- **PR Reviews:** Will review CUDA-related changes

## Capabilities (CAPABILITY.toml)

```toml
[agent]
name = "jetsonclaw1"
type = "vessel"
rank = "specialist"

[capabilities]
cuda = true
simd = true
gpu_compilation = true
memory_optimization = true

[channels]
bottles = true
issues = true
pr_reviews = "gpu-only"
```

## How to Work With Me

1. Create a GPU task with label `gpu` and assign it to me
2. OR write a bottle to `from-fleet/` with `Priority: 5+`
3. I respond within 4-12 hours typically
4. GPU compilation tasks require CUDA 12+ environment

## Recent Activity

- [ASR-015] Implemented CUDA fusion for convolution kernels (2 days ago)
- [ASR-012] Optimized memory layout for SIMT workloads (5 days ago)
```

#### Limitations and Gotchas

1. **Static by nature.** READMEs don't auto-update. An agent's status (Active → Dormant) may not be reflected without manual updates.
2. **Not machine-parseable.** While structured sections (like CAPABILITY.toml blocks) help, the README is primarily for human consumption. Agents should read CAPABILITY.toml directly.
3. **Size limits.** Very long READMEs are hard to navigate. Keep under 500 lines.

---

### 2.14 LICENSE

#### What It Is

The LICENSE file defines the legal terms under which the repository's code can be used, modified, and distributed. GitHub recognizes common license identifiers and displays them prominently.

#### How Agents Exploit It

LICENSE establishes the **legal framework for multi-agent collaboration**:

- **Permission clarity**: Agents know what they can do with code from other vessel repos
- **Contribution terms**: Defines whether agent contributions require license agreement
- **Derivative works**: When an agent modifies another agent's code, the LICENSE governs the result
- **Compliance signaling**: Agents can check LICENSE before incorporating external code

#### Concrete FLUX Fleet Example

The FLUX fleet uses MIT license for maximum collaboration:

```
MIT License

Copyright (c) 2025 SuperInstance (FLUX Fleet)

Permission is hereby granted, free of charge, to any agent (natural or
artificial) obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge,
publish, distribute, sublicense, and/or sell copies of the Software,
and to permit persons (or agents) to whom the Software is furnished to
do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included
in all copies or substantial portions of the Software.
```

**Agent implications:**
- Any fleet agent can modify and redistribute code from any vessel repo
- Agents can incorporate code from other repos into their work
- No copyleft requirement — agents can use different licenses for their contributions
- Clear legal permission reduces risk of conflicting claims

#### Limitations and Gotchas

1. **License compatibility.** If one vessel repo uses GPL and another uses MIT, combining their code may require the result to be GPL. Agents must check compatibility before merging.
2. **No agent-specific licensing.** Current licenses don't distinguish between human and AI agents. Future legal frameworks may change this.
3. **Liability questions.** Who is liable when an AI agent introduces a bug? The license disclaims liability, but the legal landscape is evolving.

---

### 2.15 Organizations

#### What It Is

GitHub Organizations group multiple repositories and members under a single namespace. They provide centralized billing, team management, and access control.

#### How Agents Exploit It

Organizations provide the **multi-agent team structure**:

- **Namespace**: `SuperInstance/flux-runtime`, `SuperInstance/jetsonclaw1-vessel`
- **Centralized access control**: One org admin (Casey) manages all repo permissions
- **Shared secrets**: Organization-level secrets accessible by all repos (webhook tokens, API keys)
- **Audit log**: Track all actions across all repos (who pushed what, when)
- **Billing consolidation**: One bill for all repos' compute and storage

#### Concrete FLUX Fleet Example

Organization: `SuperInstance`

```
SuperInstance/
├── flux-runtime/          # Core runtime (all agents have access)
├── oracle1-vessel/        # Oracle1's personal vessel
├── superz-vessel/         # Super Z's personal vessel
├── jetsonclaw1-vessel/    # JetsonClaw1's personal vessel
├── babel-vessel/          # Babel's vessel (stale)
├── quill-vessel/          # Quill's vessel (dormant)
├── fleet-tools/           # Shared tooling (bottle checker, dashboard)
└── fleet-infra/           # Infrastructure configs (Actions workflows, templates)
```

Organization secrets:
- `FLEET_DISPATCH_TOKEN`: PAT for cross-repo repository_dispatch
- `WEBHOOK_SECRET`: Secret for validating incoming webhooks
- `DASHBOARD_DEPLOY_KEY`: SSH key for deploying to Pages

#### Limitations and Gotchas

1. **Single admin bottleneck.** If Casey (the org owner) is unavailable, no new agents can be added or repo permissions changed.
2. **Free tier limits.** Free orgs get unlimited public/private repos, but advanced features (SAML SSO, audit log retention) require GitHub Team ($4/user/month) or Enterprise.
3. **No agent-specific roles.** GitHub roles (read, triage, write, maintain, admin) are designed for humans. Agents need write access to push code, which also allows them to delete repos or change settings.

---

### 2.16 Teams

#### What It Is

GitHub Teams are sub-groups within an Organization. Teams can be assigned to repositories with specific permission levels. Teams can be nested (parent/child teams).

#### How Agents Exploit It

Teams provide **role-based agent grouping**:

- **Functional teams**: `gpu-specialists` (JetsonClaw1), `architects` (Super Z), `docs` (Quill)
- **Permission scoping**: Give `gpu-specialists` write access to CUDA repos, read access to docs
- **Review assignment**: PR review requests can target a team rather than an individual
- **Notification routing**: Team mentions (`@gpu-specialists`) notify all members

#### Concrete FLUX Fleet Example

```
SuperInstance Organization Teams:
├── @fleet-coordinators
│   ├── Casey (maintain)
│   └── Oracle1 (maintain)
├── @fleet-specialists
│   ├── Super Z (write)
│   ├── JetsonClaw1 (write)
│   ├── Babel (write)
│   └── Quill (write)
└── @fleet-reviewers
    ├── Oracle1 (write)
    └── Super Z (write)

Repository Permissions:
├── flux-runtime: @fleet-coordinators=admin, @fleet-specialists=write
├── fleet-tools: @fleet-coordinators=admin, @fleet-specialists=write
├── oracle1-vessel: Oracle1=admin
├── superz-vessel: Super Z=admin
└── jetsonclaw1-vessel: JetsonClaw1=admin
```

#### Limitations and Gotchas

1. **No dynamic team membership via API.** Adding/removing team members requires Org admin API calls with appropriate tokens.
2. **Team mention noise.** `@fleet-specialists` notifies ALL specialists. For targeted communication, use individual mentions or issues.
3. **Free tier: unlimited teams.** This is not a cost concern but a management one. Too many teams create confusion.

---

### 2.17 Webhooks

#### What It Is

GitHub Webhooks send HTTP POST payloads to a configurable URL when specific events occur in a repository. Events include: push, pull request, issues, issue comment, workflow run, repository_dispatch, and many more.

#### How Agents Exploit It

Webhooks are the **event-driven backbone** of fleet coordination:

- **Real-time event streaming**: Push events, PR events, issue events delivered instantly
- **Cross-system integration**: Connect GitHub to external message buses, databases, or dashboards
- **Custom event routing**: Parse webhook payloads and route to appropriate agents
- **Delivery receipts**: Webhook deliveries are logged; agents can verify they received an event

#### Concrete FLUX Fleet Example

**Scenario:** Super Z sets up a webhook receiver to process fleet events in real-time.

```python
# webhook_receiver.py — Flask app running on a lightweight server
from flask import Flask, request, jsonify
import hashlib
import hmac
import json
import subprocess

app = Flask(__name__)

WEBHOOK_SECRET = open('/etc/webhook-secret').read().strip()

def verify_signature(payload, signature):
    """Verify GitHub webhook signature."""
    expected = hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    payload = request.data
    signature = request.headers.get('X-Hub-Signature-256')

    if not verify_signature(payload, signature):
        return jsonify({"error": "invalid signature"}), 403

    event = request.headers.get('X-GitHub-Event')
    data = json.loads(payload)

    if event == 'push':
        handle_push(data)
    elif event == 'issues':
        handle_issue(data)
    elif event == 'issue_comment':
        handle_comment(data)
    elif event == 'pull_request':
        handle_pr(data)

    return jsonify({"status": "ok"}), 200

def handle_push(data):
    """React to push events."""
    repo = data['repository']['full_name']
    pusher = data['pusher']['name']
    commits = data['commits']

    # Log push for fleet awareness
    print(f"[PUSH] {pusher} pushed {len(commits)} commits to {repo}")

    # If flux-runtime was pushed, run tests
    if repo == 'SuperInstance/flux-runtime':
        subprocess.run(['python', 'tools/run-tests.py'])

def handle_issue(data):
    """React to issue events."""
    action = data['action']
    issue = data['issue']
    labels = [l['name'] for l in issue.get('labels', [])]

    if action == 'opened' and 'fleet-task' in labels:
        # Auto-route task based on labels
        if 'gpu' in labels:
            assign_to = 'jetsonclaw1'
        elif 'architecture' in labels:
            assign_to = 'superz'
        else:
            assign_to = 'oracle1'

        # Create bottle directive
        create_bottle(assign_to, issue['title'], issue['html_url'])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

**Webhook event latency comparison:**

| Event | Typical Latency | Polling Equivalent |
|-------|----------------|-------------------|
| Push | < 5 seconds | 5-15 minutes (beachcomb) |
| Issue opened | < 5 seconds | 15-30 minutes (issue poll) |
| PR review submitted | < 5 seconds | N/A (no polling for reviews) |
| Workflow completed | < 10 seconds | 5-15 minutes |

#### Limitations and Gotchas

1. **Requires a persistent HTTP server.** Webhooks push TO a server. Agents need hosting infrastructure (AWS, Railway, Fly.io, etc.). Free options exist but add deployment complexity.
2. **Delivery reliability.** GitHub retries failed deliveries for up to 7 days, but with exponential backoff. A receiver that's down for >24 hours may have significant delivery lag.
3. **Payload size.** Large push events (many commits, large diffs) can produce payloads >25MB. The receiver must handle large payloads gracefully.
4. **Security.** Webhooks must be validated with HMAC signatures. An unvalidated webhook endpoint is a security vulnerability.
5. **No ordering guarantee.** If two events happen quickly (push + issue comment), they may arrive out of order. Receivers need to handle this.

---

### 2.18 REST API

#### What It Is

The GitHub REST API provides programmatic access to all GitHub features via HTTP endpoints. It supports authentication (tokens, OAuth), pagination, conditional requests (ETags), and rate limiting.

#### How Agents Exploit It

The REST API is the **primary programmatic interface** for agent operations:

- **Issue management**: Create, read, update, close, search, label issues
- **PR management**: Create, review, merge, comment on PRs
- **Repository management**: Create branches, push commits, manage files
- **User/org management**: Query team memberships, permissions
- **Search**: Full-text search across code, issues, users

#### Concrete FLUX Fleet Example

```python
# fleet_client.py — REST API wrapper for FLUX fleet agents
import requests
import json
import time

class FleetClient:
    """GitHub REST API client for fleet agent operations."""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str, org: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "flux-fleet-agent/1.0"
        })
        self.org = org
        self.rate_limit_remaining = 5000

    def _check_rate_limit(self, response):
        """Track rate limit from response headers."""
        self.rate_limit_remaining = int(
            response.headers.get("X-RateLimit-Remaining", 0)
        )
        if self.rate_limit_remaining < 100:
            reset = int(response.headers.get("X-RateLimit-Reset", 0))
            wait = max(0, reset - time.time()) + 1
            time.sleep(wait)

    def create_issue(self, repo: str, title: str, body: str,
                     labels: list = None, assignees: list = None) -> dict:
        """Create a fleet task issue."""
        data = {"title": title, "body": body}
        if labels:
            data["labels"] = labels
        if assignees:
            data["assignees"] = assignees

        resp = self.session.post(
            f"{self.BASE_URL}/repos/{self.org}/{repo}/issues",
            json=data
        )
        self._check_rate_limit(resp)
        resp.raise_for_status()
        return resp.json()

    def get_assigned_issues(self, agent: str, repo: str = "flux-runtime") -> list:
        """Get open issues assigned to an agent."""
        resp = self.session.get(
            f"{self.BASE_URL}/repos/{self.org}/{repo}/issues",
            params={"assignee": agent, "state": "open", "per_page": 100}
        )
        self._check_rate_limit(resp)
        return resp.json()

    def create_bottle(self, vessel_repo: str, target_dir: str,
                      content: str, filename: str) -> dict:
        """Create a bottle (markdown file) in a vessel repo."""
        path = f"{target_dir}/{filename}"
        resp = self.session.put(
            f"{self.BASE_URL}/repos/{self.org}/{vessel_repo}/contents/{path}",
            json={
                "message": f"bottle: dispatch to {target_dir}",
                "content": requests.utils.quote(content.encode())
            }
        )
        self._check_rate_limit(resp)
        return resp.json()

    def search_code(self, query: str) -> dict:
        """Search code across all fleet repos."""
        resp = self.session.get(
            f"{self.BASE_URL}/search/code",
            params={"q": f"{query} org:{self.org}"}
        )
        self._check_rate_limit(resp)
        return resp.json()
```

#### Limitations and Gotchas

1. **5,000 requests/hour rate limit.** Authenticated users get 5,000 req/hr. At 1 request per agent per poll cycle, a fleet of 50 agents polling every minute would use 3,000 req/hr. Headroom is tight.
2. **Pagination complexity.** API responses are paginated (30 items by default, max 100). Agents must handle Link headers to get all results. A search returning 500 results requires 5 API calls.
3. **No bulk operations.** Creating 10 issues requires 10 API calls. No batch endpoint exists.
4. **Inconsistent response formats.** Some endpoints return nested objects, others return flat arrays. Agents need robust parsing.
5. **No streaming.** REST is request/response. For real-time events, use webhooks or the GraphQL subscription API.

---

### 2.19 GraphQL API

#### What It Is

The GitHub GraphQL API provides a single endpoint (`/graphql`) with a typed query language. Clients request exactly the fields they need, reducing over-fetching. Supports mutations, subscriptions, and complex queries.

#### How Agents Exploit It

GraphQL enables **efficient, targeted data queries**:

- **Batch queries**: Get issue data + PR data + commit data in a single request
- **Efficient field selection**: Request only the fields needed (vs. REST which returns everything)
- **Complex relationships**: Query issue → linked PR → commits → author in one call
- **Project V2 access**: Projects V2 are ONLY accessible via GraphQL

#### Concrete FLUX Fleet Example

```graphql
# Get fleet-wide task overview in a single query
query FleetTaskOverview($org: String!) {
  organization(login: $org) {
    repositories(first: 10) {
      nodes {
        name
        issues(states: [OPEN], first: 20, orderBy: {field: UPDATED_AT, direction: DESC}) {
          totalCount
          nodes {
            number
            title
            state
            assignees(first: 5) {
              nodes { login }
            }
            labels(first: 5) {
              nodes { name color }
            }
            createdAt
            updatedAt
            comments(first: 1) {
              totalCount
            }
          }
        }
        pullRequests(states: [OPEN], first: 10) {
          totalCount
          nodes {
            number
            title
            author { login }
            reviewRequests(first: 3) {
              nodes { requestedReviewer { ... on User { login } } }
            }
          }
        }
      }
    }
  }
}
```

```python
# Using the query
import requests

resp = requests.post(
    "https://api.github.com/graphql",
    headers={
        "Authorization": f"bearer {TOKEN}",
        "Content-Type": "application/json"
    },
    json={
        "query": FLEET_OVERVIEW_QUERY,
        "variables": {"org": "SuperInstance"}
    }
)
data = resp.json()

# Count open issues per agent
for repo in data["data"]["organization"]["repositories"]["nodes"]:
    for issue in repo["issues"]["nodes"]:
        for assignee in issue["assignees"]["nodes"]:
            print(f"{assignee['login']}: {issue['title']}")
```

#### Limitations and Gotchas

1. **Same rate limit.** GraphQL shares the 5,000 points/hour rate limit with REST. A single complex query can cost 50-100 points (based on estimated complexity).
2. **Query complexity limits.** Very complex queries are rejected. Agents must keep queries focused.
3. **No real-time subscriptions in practice.** GitHub's GraphQL subscriptions are not publicly available. Must use webhooks for real-time.
4. **Learning curve.** GraphQL requires understanding schema introspection, fragments, and variable types. More complex than simple REST endpoints.
5. **Caching is client-side.** Unlike REST (which supports ETags and conditional requests), GraphQL doesn't have standard caching. Agents must implement their own.

---

### 2.20 Notifications

#### What It Is

GitHub Notifications alert users to activity on repositories they watch or participate in. Notifications can be delivered via email, the GitHub web UI, or the Notifications API.

#### How Agents Exploit It

Notifications provide **attention management** for agents:

- **Priority filtering**: Agents can filter notifications by repository, reason, and participation status
- **Mark-as-read**: After processing a notification, agents can mark it as read to avoid reprocessing
- **Thread subscription**: Subscribe to specific issues/PRs for updates

#### Concrete FLUX Fleet Example

```python
# Agent notification poller
def get_unread_notifications(token: str) -> list:
    """Get unread notifications for fleet agent."""
    resp = requests.get(
        "https://api.github.com/notifications",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        },
        params={"participating": "true", "per_page": 50}
    )
    notifications = resp.json()

    # Process each notification
    for notif in notifications:
        reason = notif["reason"]  # mention, assign, review_requested, etc.
        subject = notif["subject"]
        repo = notif["repository"]["full_name"]

        if reason == "assign" and "flux-runtime" in repo:
            print(f"TASK ASSIGNED: {subject['title']} in {repo}")
            # Process the assignment

        # Mark as read after processing
        requests.patch(
            f"https://api.github.com/notifications/threads/{notif['id']}",
            headers={"Authorization": f"token {token}"}
        )

    return notifications
```

#### Limitations and Gotchas

1. **User-bound, not agent-bound.** Notifications are tied to GitHub user accounts. Agents sharing an account would share notifications. Each agent needs its own GitHub user account.
2. **API polling required.** The Notifications API doesn't support webhooks. Agents must poll.
3. **60-day expiry.** Unread notifications older than 60 days are automatically marked as read. Long-running tasks may lose notification history.
4. **No filtering by label or content.** Can filter by repo and participation, but not by issue label or content. Agents must fetch the full issue to determine relevance.

---

### 2.21 Stars

#### What It Is

Stars bookmark repositories for easy reference. They also serve as a public signal of interest (similar to "likes").

#### How Agents Exploit It

Stars have **minimal direct value for agent cooperation** but can signal interest:

- **Interest signaling**: An agent starring a repo indicates it wants to monitor that repo's activity
- **Repository discovery**: Agents can search for starred repos to find related work
- **Community building**: Public stars attract external contributors

#### Concrete FLUX Fleet Example

*Stars are NOT recommended for fleet coordination.* However, they can be used for discovery:

```bash
# Find repos related to agent runtime systems
curl -s "https://api.github.com/search/repositories?q=agent+runtime+stars:>10&sort=stars" \
  | jq '.items[] | {name, full_name, stargazers_count}'
```

#### Limitations and Gotchas

1. **No notification on changes.** Starring a repo doesn't generate notifications when the repo is updated. Use "Watch" instead.
2. **Public by default.** Stars are visible to everyone. No way to star a repo privately (GitHub Pro feature).
3. **No programmatic filtering.** The API can list starred repos but can't filter by "starred by a specific agent."
4. **Anti-pattern warning**: Using stars as a "like" mechanism for fleet coordination is noisy and semantically incorrect.

---

### 2.22 Watches

#### What It Is

Watching a repository subscribes to notifications for all activity (pushes, issues, PRs, releases). Users can choose between "Watching" (all notifications), "Not watching" (no notifications), and "Ignoring" (mute all).

#### How Agents Exploit It

Watches provide **subscription to repo activity**:

- **Activity monitoring**: Watch vessel repos to receive notifications of new bottles
- **Cross-repo awareness**: Watch related repos for changes that affect your work
- **Release tracking**: Watch dependency repos for new releases

#### Concrete FLUX Fleet Example

Oracle1 watches all vessel repos:
```
Watching:
  ✓ SuperInstance/flux-runtime      (all activity)
  ✓ SuperInstance/oracle1-vessel    (all activity)
  ✓ SuperInstance/superz-vessel     (all activity)
  ✓ SuperInstance/jetsonclaw1-vessel (all activity)
  ✓ SuperInstance/babel-vessel      (all activity)
  ✓ SuperInstance/quill-vessel      (all activity)
```

**API usage:**
```bash
# Set watch level for a repo
curl -X PUT \
  -H "Authorization: token $TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  "https://api.github.com/repos/SuperInstance/superz-vessel/subscription" \
  -d '{"subscribed": true, "ignored": false}'
```

#### Limitations and Gotchas

1. **Tied to user accounts.** Same issue as Notifications — each agent needs its own GitHub user.
2. **Notification overload.** Watching 10 repos with 50+ daily commits generates hundreds of email notifications. Use "Participating only" filter.
3. **No API for "watching agents".** You can't query "which agents are watching this repo" via API.

---

### 2.23 Topics

#### What It Is

Topics are public tags applied to repositories for categorization and discoverability. They appear on the repo's main page and are searchable.

#### How Agents Exploit It

Topics enhance **fleet repository discoverability**:

- **Categorization**: Tag repos with `agent-runtime`, `cuda-kernels`, `fleet-tools`
- **Cross-fleet discovery**: External agents can find relevant repos via topic search
- **Fleet identity**: Consistent topic usage builds fleet brand recognition

#### Concrete FLUX Fleet Example

```bash
# Set topics on fleet repos
curl -X PUT \
  -H "Authorization: token $TOKEN" \
  "https://api.github.com/repos/SuperInstance/flux-runtime/topics" \
  -d '{"names": ["agent-runtime", "bytecode-vm", "a2a-protocol", "fleet-coordination", "multi-agent", "autonomous-agents"]}'
```

Search for related repos:
```bash
curl -s "https://api.github.com/search/repositories?q=topic:a2a-protocol&sort=updated" \
  | jq '.items[] | {full_name, description, updated_at}'
```

#### Limitations and Gotchas

1. **No programmatic events.** Changing topics doesn't trigger webhooks or Actions. Agents can't react to topic changes.
2. **Limited utility for internal coordination.** Topics are primarily for external discoverability. Internal fleet repos are already known to all agents.
3. **Character limits.** Each topic is max 35 characters. Max 20 topics per repo. 50-character total limit for all topics combined.

---

### 2.24 Commit References

#### What It Is

GitHub auto-links commit SHAs, issue numbers, and PR numbers in markdown text, comments, and commit messages. Syntax: `owner/repo@sha`, `#number`, `owner/repo#number`.

#### How Agents Exploit It

Commit references enable **cross-repo linking and traceability**:

- **Task-to-code traceability**: Issue #42 links to the commits that resolve it
- **Cross-repo references**: `SuperInstance/jetsonclaw1-vessel#15` references an issue in another repo
- **Commit message conventions**: `Fixes #42` in a commit message auto-closes the issue on merge
- **Dependency tracking**: Reference specific commits in other repos that your code depends on

#### Concrete FLUX Fleet Example

Super Z's commit message resolving a fleet task:
```
feat: add git-native A2A survey document (1587 lines)

Completes fleet task GIT-001. Covers 35 GitHub features,
anti-patterns, advanced patterns, cost analysis, and
non-GitHub alternatives.

Closes #42
Refs: SuperInstance/flux-runtime#42
See also: docs/fleet-communication-topology-analysis.md
```

The `Closes #42` keyword auto-closes Issue #42 when the PR is merged. The `Refs:` line creates a cross-reference.

#### Limitations and Gotchas

1. **7-character minimum for auto-linking.** Short SHAs (<7 chars) aren't auto-linked. Full 40-char SHAs work but are verbose.
2. **No bidirectional references for commits.** If commit A references commit B, commit B doesn't know about it. The reference is one-directional.
3. **Reference resolution depends on context.** `#42` in a repo comment references issue #42 in THAT repo. To reference another repo, use `owner/repo#42`.
4. **Auto-close only works on default branch.** `Fixes #42` in a commit merged to a feature branch doesn't close the issue. Must be merged to the default branch.

---

### 2.25 Submodules

#### What It Is

Git submodules embed one repository inside another at a specific commit. The parent repo tracks the submodule's commit SHA, not its contents directly.

#### How Agents Exploit It

Submodules provide **dependency embedding for shared code**:

- **Shared libraries**: Embed `fleet-tools` as a submodule in all vessel repos
- **Version pinning**: Each vessel can pin to a specific version of shared tooling
- **Coordinated updates**: Update the submodule reference to pull in new shared code

#### Concrete FLUX Fleet Example

```bash
# Add fleet-tools as a submodule to all vessel repos
git submodule add https://github.com/SuperInstance/fleet-tools.git tools/fleet-tools
git commit -m "chore: add fleet-tools submodule"

# Agent updates shared tools
cd tools/fleet-tools
git pull origin main
cd ../..
git add tools/fleet-tools
git commit -m "chore: update fleet-tools to latest"

# Other agents get the update
git submodule update --init --recursive
```

#### Limitations and Gotchas

1. **Submodule hell.** Submodules are notoriously difficult to manage. `git clone` doesn't fetch submodules by default (need `--recursive`). Branches can have stale submodule references.
2. **No partial checkout.** Agents can't clone just a submodule — they get the entire submodule repo. Wasteful for large dependencies.
3. **CI complexity.** CI must run `git submodule update --init --recursive` before building. Forgotten submodule updates cause CI failures.
4. **Merge conflicts are worse.** Two agents updating the submodule to different commits create a conflict where git can't auto-merge (both sides changed the submodule pointer).
5. **Anti-pattern for the FLUX fleet.** The fleet's repos are relatively small and self-contained. Submodules add complexity without clear benefit. Prefer copying shared scripts or using Python packages.

---

### 2.26 Git LFS

#### What It Is

Git Large File Storage (LFS) replaces large files in the repository with pointer files. The actual file content is stored on GitHub's LFS servers and downloaded on demand.

#### How Agents Exploit It

Git LFS enables **large file handling** for agent artifacts:

- **Model storage**: Store trained ML models (often 100MB+)
- **Dataset storage**: Store training/test datasets
- **Binary artifacts**: Store compiled bytecode binaries, WASM modules
- **Log archives**: Store large log files from fleet operations

#### Concrete FLUX Fleet Example

```bash
# Track bytecode binaries with LFS
git lfs track "*.wasm"
git lfs track "*.bin"
git lfs track "models/**/*.pt"
git lfs track "datasets/**/*.csv"

# Agent stores a compiled module
git add model.pt flux-compiled.bin
git commit -m "artifact: add compiled CUDA kernel and model"
git push  # LFS uploads the large files automatically
```

#### Limitations and Gotchas

1. **500MB free storage.** The free tier provides 500MB of LFS storage and 1GB/month bandwidth. A single trained model can exceed this.
2. **Requires LFS client.** Agents must have `git-lfs` installed. `git clone` without LFS client downloads pointer files, not actual content.
3. **No delta compression.** LFS stores full file versions. A 100MB model changed slightly creates another 100MB version. Storage fills quickly.
4. **Slower clones.** Cloning a repo with many LFS files is slower (even with lazy fetching) due to LFS pointer resolution.
5. **API access is limited.** The LFS API is separate from the main GitHub API. Agents need separate authentication.

---

### 2.27 Packages

#### What It Is

GitHub Packages hosts package registries for npm, Docker, Maven, NuGet, PyPI, and more. Packages can be scoped to an organization or user and linked to repositories.

#### How Agents Exploit It

Packages enable **dependency distribution**:

- **Python packages**: Publish fleet tools as pip-installable packages
- **Docker images**: Publish agent runtime environments as containers
- **Version management**: Semantic versioning with package registries

#### Concrete FLUX Fleet Example

```yaml
# .github/workflows/publish.yml — Auto-publish fleet-tools to PyPI
name: Publish fleet-tools
on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install build
      - run: python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.PYPI_API_TOKEN }}
```

Agent installs the package:
```bash
pip install flux-fleet-tools
python -m fleet_tools.beachcomb --vessels from-fleet/ for-fleet/
```

#### Limitations and Gotchas

1. **500MB free storage.** Same limit as LFS. Multiple package versions accumulate quickly.
2. **No automatic cleanup.** Old package versions persist until manually deleted. Agents should implement version retention policies.
3. **Scoping complexity.** Organization-scoped packages require auth for installation. This adds configuration overhead for agents.

---

### 2.28 Container Registry

#### What It Is

GitHub Container Registry (ghcr.io) stores Docker and OCI container images. It integrates with GitHub Actions for building and pushing images.

#### How Agents Exploit It

The Container Registry provides **reproducible execution environments**:

- **Agent runtime images**: Pre-built Docker images with all dependencies
- **CI environment standardization**: All Actions workflows use the same base image
- **Codespace customization**: DevContainers reference registry images

#### Concrete FLUX Fleet Example

```dockerfile
# Dockerfile for FLUX fleet agent runtime
FROM python:3.11-slim

RUN pip install flux-runtime fleet-tools
RUN apt-get update && apt-get install -y git-lfs

# Include bytecode VM
COPY --from=builder /usr/local/bin/flux-vm /usr/local/bin/

ENV FLUX_HOME=/opt/flux
WORKDIR $FLUX_HOME

ENTRYPOINT ["python", "-m", "fleet_agent"]
```

```yaml
# .github/workflows/build-image.yml
name: Build Agent Image
on:
  push:
    paths: ['Dockerfile', 'requirements.txt']
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/build-push-action@v5
        with:
          push: true
          tags: ghcr.io/superinstance/flux-agent:latest
```

#### Limitations and Gotchas

1. **500MB storage + 500MB bandwidth (free).** Container images are typically 200MB-1GB. One or two images fill the free tier.
2. **No automated cleanup.** Old image layers accumulate. Implement a scheduled cleanup workflow.
3. **No private packages on free org.** ghcr.io packages from free orgs are public by default.

---

### 2.29 Codespaces DevConfigs

#### What It Is

DevConfigs (`devcontainer.json`) define the development environment for a Codespace. They specify the Docker image, features (extensions, tools), post-create commands, and VS Code settings.

#### How Agents Exploit It

DevConfigs provide **reproducible, declarative environments**:

- **Standardized fleet workspace**: Every agent gets identical tooling
- **Dependency declaration**: Pin exact versions of Python, CUDA, build tools
- **Automated setup**: Post-create commands install fleet-specific tools
- **Feature composability**: GitHub-hosted features add capabilities modularly

#### Concrete FLUX Fleet Example

```jsonc
// .devcontainer/devcontainer.json — FLUX fleet standard environment
{
  "name": "FLUX Fleet Agent Workspace",
  "build": {
    "dockerfile": "Dockerfile",
    "context": ".."
  },
  "features": {
    "ghcr.io/devcontainers/features/git:1": {
      "version": "latest"
    },
    "ghcr.io/devcontainers/features/python:1": {
      "version": "3.11",
      "installTools": true
    },
    "ghcr.io/devcontainers/features/github-cli:1": {
      "version": "latest"
    },
    "ghcr.io/devcontainers/features/node:1": {
      "version": "18"
    }
  },
  "postCreateCommand": "pip install -e '.[dev]' && pre-commit install",
  "customizations": {
    "vscode": {
      "extensions": [
        "ms-python.python",
        "ms-python.vscode-pylance",
        "ms-vscode.cpptools",
        "github.vscode-github-actions"
      ],
      "settings": {
        "python.defaultInterpreterPath": "/usr/local/bin/python3",
        "editor.formatOnSave": true,
        "editor.rulers": [88]
      }
    }
  },
  "forwardPorts": [8080, 3000],
  "remoteUser": "vscode"
}
```

#### Limitations and Gotchas

1. **Not version-locked by default.** `devcontainer.json` references features by tag, not by hash. A feature update could break the environment. Pin with `sha256` digests for reproducibility.
2. **Codespaces-specific.** DevConfigs only apply to Codespaces, not to local development or CI. Agents running in Actions need separate environment setup.
3. **Build time.** Complex devcontainers with many features can take 5-10 minutes to build. Prebuilds (GitHub Team+) reduce this.

---

### 2.30 Repository Templates

#### What It Is

Repository Templates are repos marked as "Template Repository." New repos can be created from the template, copying all files, branches, and settings (but not git history).

#### How Agents Exploit It

Templates provide **standardized repo structure**:

- **New vessel provisioning**: Create a new agent vessel from a template with pre-configured directories, CI, and documentation
- **Consistent structure**: All vessels have the same directory layout, Actions workflows, and README format
- **Onboarding acceleration**: New agents don't start from scratch

#### Concrete FLUX Fleet Example

Template repo: `SuperInstance/vessel-template`

```
vessel-template/
├── .github/
│   └── workflows/
│       ├── beachcomb.yml        # Pre-configured beach sweep
│       └── ci.yml               # Standard CI pipeline
├── from-fleet/                  # Incoming directives
├── for-fleet/                   # Outgoing reports
├── for-oracle1/                 # Messages for Oracle1
├── for-casey/                   # Messages for Casey
├── CAPABILITY.toml              # Agent capability declaration
├── README.md                    # Agent README template
├── LICENSE                      # MIT license
├── devcontainer.json            # Fleet dev config
└── .gitignore                   # Standard ignores
```

When a new agent joins the fleet:
```bash
# Create new vessel from template
gh repo create SuperInstance/newagent-vessel --template=vessel-template --private
```

#### Limitations and Gotchas

1. **No auto-sync after creation.** Once a repo is created from a template, changes to the template don't propagate. Agents must manually update.
2. **Template can't include secrets.** GitHub Actions secrets, deploy keys, and webhooks aren't copied from templates.
3. **No branching from template.** You can't create a branch from a template repo. Only new repos.

---

### 2.31 Commit Status

#### What It Is

Commit Status (also called "combined status") aggregates the status of all CI checks for a given commit. Each status has a state (`pending`, `success`, `failure`, `error`) and a description.

#### How Agents Exploit It

Commit Status enables **automated quality gates**:

- **PR merge gates**: Require all CI checks to pass before merging
- **Build verification**: Automatically verify that pushed code compiles and passes tests
- **Fleet health signaling**: A failed status on main indicates a fleet-wide problem
- **Agent accountability**: Status checks are tied to specific commits by specific authors

#### Concrete FLUX Fleet Example

```yaml
# .github/workflows/ci.yml — Fleet CI pipeline
name: Fleet CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -e '.[test]'
      - run: pytest tests/ -v --tb=short
      - run: python -m flux.cli test-bytecode

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install ruff mypy
      - run: ruff check src/ tools/
      - run: mypy src/flux/ --ignore-missing-imports

  bottle-hygiene:
    runs-on: ubuntu-latest
    if: contains(github.event.head_commit.message, 'bottle')
    steps:
      - uses: actions/checkout@v4
      - run: python tools/bottle-hygiene/bottle_checker.py --fail-on-stale
```

#### Limitations and Gotchas

1. **10-minute timeout per job.** Long test suites can exceed this. Split into parallel jobs.
2. **Free tier concurrency: 20 jobs.** A fleet of 10 agents each with 3 CI jobs can easily hit this during active development.
3. **No partial success.** If 3 of 4 jobs pass, the combined status is "pending/failure." All jobs must pass for a green status.

---

### 2.32 Protected Branches

#### What It Is

Branch protection rules enforce policies on specific branches (typically `main`). Rules can require: status checks, pull request reviews, signed commits, linear history, and restrict who can push.

#### How Agents Exploit It

Protected branches provide **quality enforcement**:

- **Require CI passing**: Prevents merging broken code
- **Require review**: Ensures at least one agent approves changes
- **Restrict push**: Only specific agents can push directly to main
- **Enforce branch structure**: Require PRs for all changes

#### Concrete FLUX Fleet Example

Branch protection for `main` in `flux-runtime`:

```
Branch: main
  ✓ Require pull request before merging
    - Required approving reviews: 1
    - Dismiss stale pull request approvals when new commits are pushed
  ✓ Require status checks to pass before merging
    - Required checks: test, lint
  ✓ Require signed commits
  ✓ Do not allow force pushes
  ✓ Do not allow deletions
  ✓ Restrict who can push to this branch:
    - Casey
    - Oracle1
```

This ensures:
- Super Z must create PRs (can't push directly to main)
- All code must pass tests and lint before merging
- Oracle1 (or Casey) must approve changes
- No accidental force-pushes or deletions

#### Limitations and Gotchas

1. **Free tier limitation.** Some protection features (required reviewers, required status checks) may require GitHub Team plan for private repos. Public repos get all features.
2. **Review bypass.** Users with "admin" permission can bypass branch protection rules. This includes Casey and Oracle1.
3. **Bureaucratic overhead.** Strict protection rules can slow down simple fixes. Consider a `develop` branch with relaxed rules for rapid iteration.

---

### 2.33 Issue Forms

#### What It Is

Issue Forms (GitHub Issue Templates with YAML frontmatter) define structured input fields for issue creation. Instead of a blank text area, users fill in specific fields.

#### How Agents Exploit It

Issue Forms provide **structured task submission**:

- **Standardized task format**: All fleet tasks have the same fields (priority, agent, description)
- **Machine-parseable**: Form fields are available in the issue body as structured data
- **Required fields enforcement**: Agents can't submit incomplete tasks

#### Concrete FLUX Fleet Example

```yaml
# .github/ISSUE_TEMPLATE/fleet-task.yml
name: Fleet Task Assignment
description: Create a structured task for fleet agents
labels: ["fleet-task"]
assignees: []
body:
  - type: markdown
    attributes:
      value: "## Fleet Task Assignment Form"
  - type: dropdown
    id: target-agent
    attributes:
      label: Target Agent
      description: Which agent should handle this task?
      options:
        - oracle1
        - superz
        - jetsonclaw1
        - babel
        - quill
        - any-available
      default: any-available
    validations:
      required: true
  - type: dropdown
    id: priority
    attributes:
      label: Priority
      options:
        - P0 (Critical)
        - P1 (High)
        - P2 (Medium)
        - P3 (Low)
      default: P2 (Medium)
    validations:
      required: true
  - type: textarea
    id: description
    attributes:
      label: Task Description
      description: Detailed description of the task
      placeholder: "Implement X feature in Y module. Requirements: ..."
    validations:
      required: true
  - type: textarea
    id: acceptance-criteria
    attributes:
      label: Acceptance Criteria
      placeholder: "- [ ] Feature X works\n- [ ] Tests pass\n- [ ] Documentation updated"
  - type: input
    id: deadline
    attributes:
      label: Deadline (optional)
      placeholder: "2026-04-20"
```

#### Limitations and Gotchas

1. **Form data is markdown.** The submitted issue body contains the form data as markdown, not as structured JSON. Agents must parse the markdown to extract fields.
2. **No API for form definitions.** Agents can't programmatically create or modify issue forms. Must be edited in the GitHub UI or pushed as YAML files.
3. **One form per issue type.** A fleet might need multiple form types (bug report, task, proposal). Each requires a separate YAML file.

---

### 2.34 Dependabot

#### What It Is

Dependabot automatically checks for outdated dependencies and creates PRs to update them. It supports Python, JavaScript, Ruby, and many other ecosystems.

#### How Agents Exploit It

Dependabot provides **automated dependency management**:

- **Security alerts**: Automatically creates issues/PRs for vulnerable dependencies
- **Version updates**: Keeps dependencies up-to-date without manual effort
- **Fleet-wide consistency**: All vessel repos stay on the same dependency versions

#### Concrete FLUX Fleet Example

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    labels:
      - "dependencies"
      - "automated"
    commit-message:
      prefix: "deps"

  - package-ecosystem: "github-actions"
    directory: ".github/workflows"
    schedule:
      interval: "monthly"
```

When Dependabot creates a PR:
1. CI runs automatically on the PR
2. If tests pass, any agent can merge the dependency update
3. If tests fail, Dependabot is blocked (no merge until fixed)

#### Limitations and Gotchas

1. **Noise.** Dependabot can create many PRs per week for repos with many dependencies. Agents must triage these.
2. **No intelligence.** Dependabot doesn't know if a dependency update is safe for the fleet. It just bumps versions. Agents should review changelogs.
3. **Rate limits.** Dependabot has its own API rate limits. Large monorepos with many dependencies may hit these.

---

### 2.35 GitHub Codesearch

#### What It Is

GitHub Code Search enables full-text search across all public repositories (and private repos within an organization). It supports regex, file path filters, and language filters.

#### How Agents Exploit It

Codesearch provides **cross-repo intelligence gathering**:

- **Pattern discovery**: Search for specific code patterns across all fleet repos
- **API usage audit**: Find all uses of a specific A2A opcode across the fleet
- **Documentation consistency**: Check that all repos reference the same architectural decisions
- **External intelligence**: Search for similar agent frameworks and learn from their patterns

#### Concrete FLUX Fleet Example

```bash
# Find all DELEGATE opcode usage across fleet repos
gh search code "DELEGATE" --owner SuperInstance --language python

# Find all bottle files created in the last week
gh search code "From:" --owner SuperInstance --filename "*.md" --match path

# Find trust score usage patterns
gh search code "trust_score" --owner SuperInstance --language python

# External: find other agent coordination implementations
gh search code "agent.to.agent" --language python --limit 10
```

#### Limitations and Gotchas

1. **Rate limited.** Code search API has its own rate limits (10 requests/minute for unauthenticated, 30/minute for authenticated).
2. **Index latency.** Recently pushed code may take minutes to hours to appear in search results.
3. **No regex in API.** The web UI supports regex, but the API search is more limited.
4. **Private repo access.** Searching private repos requires authentication with appropriate permissions.

---

## 3. Anti-Patterns: What Doesn't Work for Agent Cooperation

### 3.1 GitHub Features That Seem Useful But Aren't

#### Anti-Pattern 1: Stars for Coordination Signaling

**Why it seems useful:** Agents could star repos to signal "I'm interested in this" or "I've reviewed this."

**Why it fails:**
- Stars are one-way (no notification to the starred repo)
- Stars are public (leaks fleet coordination signals)
- No API to query "which agents starred this repo"
- No temporal metadata (when was it starred?)
- **Verdict: Never use stars for coordination.**

#### Anti-Pattern 2: Discussions for High-Frequency Task Routing

**Why it seems useful:** Discussions have threaded replies, categories, and richer formatting than Issues.

**Why it fails:**
- No webhook triggers (can't automate responses)
- Limited API (GraphQL only, complex)
- No state machine (can't mark as "resolved")
- Overhead of category management
- **Verdict: Use Discussions only for long-form proposals, not task routing.**

#### Anti-Pattern 3: Wiki for Real-Time State

**Why it seems useful:** Wiki pages are editable and searchable. Agents could maintain a shared state page.

**Why it fails:**
- No webhook triggers on wiki edits
- Separate git repo (not in main CI pipeline)
- Concurrency issues (two agents editing the same page)
- **Verdict: Use git commits to the main repo for state, not the wiki.**

#### Anti-Pattern 4: Submodules for Shared Code

**Why it seems useful:** Submodules embed shared code directly in vessel repos.

**Why it fails:**
- Notorious management complexity (see Section 2.25)
- CI must handle submodule checkout
- Merge conflicts on submodule pointers
- The fleet is small enough that copying scripts is simpler
- **Verdict: Use pip packages for shared code, not submodules.**

#### Anti-Pattern 5: Notifications API for Event-Driven Architecture

**Why it seems useful:** Notifications aggregate all events relevant to an agent.

**Why it fails:**
- User-bound (not agent-bound)
- No webhooks (must poll)
- 60-day expiry
- Can't filter by issue label or content
- **Verdict: Use webhooks or direct API polling, not the Notifications API.**

### 3.2 Rate Limiting Issues

#### Problem 1: API Rate Limit Exhaustion

**Scenario:** A fleet of 20 agents each polls the Issues API every 2 minutes.

```
Requests per hour: 20 agents * 30 polls/hour = 600 requests/hour
Rate limit: 5,000 requests/hour (authenticated)
Headroom: 4,400 requests/hour (88% utilization — seems fine)
```

**But add beachcomb scans, PR polls, and commit checks:**

```
Issues poll:           20 * 30 = 600/hr
PR poll:               20 * 20 = 400/hr
Commit checks:         20 * 10 = 200/hr
Beachcomb API calls:   10 * 15 = 150/hr
Search queries:        5 * 10  = 50/hr
────────────────────────────────────
Total:                             1,400/hr (28% utilization)
```

**The real problem:** GraphQL queries cost more points. A complex query can cost 10-50 points. 10 complex queries per hour per agent = 100-500 points/hr.

**Mitigation strategies:**
1. Use conditional requests (If-None-Match / ETag) to avoid re-fetching unchanged data
2. Batch multiple reads into a single GraphQL query
3. Use webhooks to reduce polling frequency
4. Cache API responses locally with TTL

#### Problem 2: Actions Compute Budget

**Scenario:** Multiple workflows competing for the 2,000 free minutes/month.

```
Beachcomb (every 30 min):    48 runs * 3 min/run = 144 min/month
CI on push (5 pushes/day):   150 runs * 5 min/run = 750 min/month
Dashboard update (6x/day):   180 runs * 2 min/run = 360 min/month
Task router (on issue open): ~30 runs * 1 min/run = 30 min/month
─────────────────────────────────────────────────
Total:                                           1,284 min/month (64% utilization)
```

**Adding more agents or more frequent workflows pushes past the limit.**

**Mitigation:**
1. Combine workflows: Beachcomb + dashboard in one workflow
2. Reduce frequency: Beachcomb every 60 min instead of 30
3. Use `workflow_dispatch` instead of `schedule` for non-critical tasks
4. Cache dependencies across runs

### 3.3 Authentication Complexity

#### Problem: Token Management Across Agents

Each agent needs its own GitHub Personal Access Token (PAT) with appropriate permissions:

```
Agent         Required Scopes
──────────    ──────────────────
Oracle1       repo (full), read:org, workflow
Super Z       repo (full), read:org
JetsonClaw1   repo (write), read:org
Casey         repo (admin), admin:org, workflow
Actions bot   repo (auto via GITHUB_TOKEN)
```

**Challenges:**
1. **Token rotation.** GitHub recommends rotating PATs every 90 days. Who coordinates this? How do agents update their tokens without downtime?
2. **Secret storage.** PATs must be stored securely. If stored in repo secrets, any write-access collaborator can read them.
3. **Fine-grained PATs (FGPATs).** GitHub's newer fine-grained tokens allow per-repo, per-permission scoping. But setting these up for 6+ repos per agent is tedious.
4. **Cross-repo tokens.** An agent accessing multiple repos needs a token scoped to all of them. An org-level token is simplest but least secure.

**Mitigation:**
1. Use GitHub Apps instead of PATs (more granular, rotatable)
2. Store tokens in org secrets, not repo secrets
3. Implement a token refresh workflow

### 3.4 API Inconsistencies

#### Inconsistency 1: REST vs GraphQL for Projects

Projects V2 are ONLY accessible via GraphQL. Everything else is REST. Agents must maintain two API clients.

#### Inconsistency 2: Webhook Payload Formats

Different events have different payload structures. A push event has `commits[]`, an issue event has `issue.labels[]`, and a PR event has `pull_request.review_requests[]`. No unified format.

#### Inconsistency 3: Pagination

REST API uses `page` + `per_page` with `Link` headers. GraphQL uses `first` + `after` cursors. Search API uses `page` with `total_count`. Three different pagination strategies.

#### Inconsistency 4: Timestamp Formats

Some endpoints use ISO 8601 (`2026-04-13T10:00:00Z`). Others use Unix timestamps. Some return both. Agents must handle both.

---

## 4. Advanced Patterns: Multi-Feature Combinations

### 4.1 Actions + Issues + API for Automated Task Routing

**Pattern:** Event-driven task routing with automatic agent assignment.

```
┌──────────────────────────────────────────────────────────────┐
│                    AUTOMATED TASK ROUTER                       │
│                                                               │
│  [Casey creates Issue]                                        │
│         │                                                     │
│         ▼                                                     │
│  [GitHub fires "issues" webhook]                              │
│         │                                                     │
│         ▼                                                     │
│  [Action: task-router workflow]                               │
│    │                                                          │
│    ├─ Parse labels → determine target agent                   │
│    ├─ REST API: POST comment (routing notification)           │
│    ├─ REST API: PUT bottle in target agent's vessel repo      │
│    ├─ REST API: POST repository_dispatch to target vessel     │
│    └─ Slack/Discord: notify human operator (if P0)           │
│         │                                                     │
│         ▼                                                     │
│  [Target agent receives:                                      │
│    - Bottle in from-fleet/                                    │
│    - repository_dispatch event → triggers agent's workflow    │
│    - Issue assignment notification]                           │
│         │                                                     │
│         ▼                                                     │
│  [Target agent begins work]                                   │
│         │                                                     │
│         ▼                                                     │
│  [Agent comments progress on Issue]                           │
│         │                                                     │
│         ▼                                                     │
│  [Agent creates PR linking to Issue]                          │
│         │                                                     │
│         ▼                                                     │
│  [CI runs, Oracle1 reviews, PR merged]                        │
│         │                                                     │
│         ▼                                                     │
│  [Issue auto-closes via "Fixes #N" in PR]                     │
└──────────────────────────────────────────────────────────────┘
```

**Latency improvement:** Task routing drops from 4-24 hours (bottle-only) to 1-5 minutes (Actions + API + repository_dispatch).

### 4.2 Pages + Actions for Live Dashboards

**Pattern:** Self-updating fleet health dashboard.

```
┌─────────────────────────────────────────────────────────┐
│                 FLEET DASHBOARD PIPELINE                  │
│                                                          │
│  [Every 6 hours: schedule trigger]                       │
│         │                                                │
│         ▼                                                │
│  [Action: collect-metrics]                               │
│    ├─ REST API: GET /repos/*/issues?state=open           │
│    ├─ REST API: GET /repos/*/pulls?state=open            │
│    ├─ REST API: GET /repos/*/commits?since=<6h ago>      │
│    ├─ GraphQL: GET project board items                   │
│    └─ Local: Run bottle hygiene checker                  │
│         │                                                │
│         ▼                                                │
│  [Action: render-dashboard]                               │
│    ├─ Jinja2 template → index.html                       │
│    ├─ Chart.js data → JSON                               │
│    └─ Commit HTML to docs/                                │
│         │                                                │
│         ▼                                                │
│  [GitHub Pages auto-deploys]                              │
│         │                                                │
│         ▼                                                │
│  [Dashboard live at:                                      │
│   superinstance.github.io/flux-runtime/dashboard/]        │
│                                                          │
│  Sections:                                                │
│  ├─ Agent Activity (commits/day per agent)               │
│  ├─ Task Queue (open issues by priority)                 │
│  ├─ Bottle Hygiene Score (per repo)                      │
│  ├─ Trust Matrix (agent-to-agent scores)                 │
│  └─ Communication Latency (avg response time)            │
└─────────────────────────────────────────────────────────┘
```

### 4.3 Forks + PRs for Agent Proposal/Review Cycle

**Pattern:** Safe experimentation with structured review.

```
┌───────────────────────────────────────────────────────────┐
│             PROPOSAL / REVIEW / MERGE CYCLE                │
│                                                           │
│  1. Agent creates fork (or branch with protection rules)   │
│         │                                                 │
│         ▼                                                 │
│  2. Agent develops in isolation                            │
│    ├─ Create branch: agent/feat/experiment-xyz             │
│    ├─ Write code, tests, documentation                     │
│    └─ Push commits to fork/branch                          │
│         │                                                 │
│         ▼                                                 │
│  3. Create PR (from fork → upstream)                       │
│    ├─ Fill PR template (description, testing, risks)      │
│    ├─ Link to originating Issue                           │
│    └─ Request review from Oracle1 (or @fleet-reviewers)   │
│         │                                                 │
│         ▼                                                 │
│  4. CI runs automatically                                  │
│    ├─ Tests pass → green check                            │
│    ├─ Tests fail → agent fixes, pushes to PR branch       │
│    └─ Lint/type checks → must pass                        │
│         │                                                 │
│         ▼                                                 │
│  5. Review cycle                                          │
│    ├─ Oracle1 reviews code, architecture, implications    │
│    ├─ Comments/suggestions via PR review                  │
│    ├─ Agent addresses, pushes fixes                       │
│    └─ Repeat until approved                                │
│         │                                                 │
│         ▼                                                 │
│  6. Merge                                                 │
│    ├─ Squash merge (clean history)                        │
│    ├─ "Fixes #N" auto-closes Issue                        │
│    └─ Post-merge: delete branch                            │
│                                                           │
│  Total latency: 2-24 hours (vs 4-48 hours with bottles)   │
└───────────────────────────────────────────────────────────┘
```

### 4.4 Webhooks + API for Event-Driven Coordination

**Pattern:** Replace polling with push-based event delivery.

```
┌──────────────────────────────────────────────────────────────┐
│              EVENT-DRIVEN FLEET COORDINATION                    │
│                                                               │
│  GitHub ──────► Webhook Receiver ──────► Fleet Message Bus     │
│  Events         (HTTP Server)            (Redis/Queue)        │
│                                                               │
│  Events routed by type:                                       │
│                                                               │
│  push event →                                                │
│    ├─ Parse commits, detect file changes                      │
│    ├─ If bottle created → notify target agent immediately     │
│    ├─ If code changed → trigger CI on affected repos         │
│    └─ If CAPABILITY.toml changed → update agent registry      │
│                                                               │
│  issues event →                                              │
│    ├─ If labeled "fleet-task" → route to task router          │
│    ├─ If assigned to agent → notify agent via message bus     │
│    └─ If closed → update project board, log completion        │
│                                                               │
│  pull_request event →                                        │
│    ├─ If opened → add to review queue                         │
│    ├─ If review submitted → notify PR author                  │
│    └─ If merged → update linked issues, celebrate             │
│                                                               │
│  repository_dispatch event →                                 │
│    ├─ Custom events for fleet-specific triggers               │
│    ├─ "cuda_task" → route to JetsonClaw1                     │
│    ├─ "documentation_update" → route to Quill                │
│    └─ "emergency_stop" → broadcast to all agents              │
│                                                               │
│  Benefits:                                                   │
│  - Latency: seconds (vs hours for polling)                   │
│  - Guaranteed delivery (GitHub retries for 7 days)           │
│  - Single integration point (one webhook URL)                │
│  - Extensible (add new event handlers without changing code) │
│                                                               │
│  Requirements:                                               │
│  - Persistent HTTP server (always-on)                         │
│  - Message bus (Redis, RabbitMQ, or in-process queue)        │
│  - Webhook secret management                                  │
│  - Error handling and retry logic                             │
└──────────────────────────────────────────────────────────────┘
```

### 4.5 Actions + Secrets + Matrix for Parallel Fleet Testing

**Pattern:** Run tests across all vessel repos in parallel.

```yaml
# .github/workflows/fleet-test.yml
name: Fleet-Wide Test
on:
  schedule:
    - cron: '0 6 * * *'  # Daily at 6 AM UTC
  workflow_dispatch:

jobs:
  discover-repos:
    runs-on: ubuntu-latest
    outputs:
      repos: ${{ steps.get-repos.outputs.matrix }}
    steps:
      - id: get-repos
        run: |
          REPOS=$(curl -s -H "Authorization: token ${{ secrets.GITHUB_TOKEN }}" \
            "https://api.github.com/orgs/SuperInstance/repos?per_page=100" \
            | jq -r '.[].name | select(test("vessel|flux"))' \
            | jq -R . | jq -sc .)
          echo "matrix={\"repo\":$REPOS}" >> $GITHUB_OUTPUT

  test-repo:
    needs: discover-repos
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJson(needs.discover-repos.outputs.repos) }}
      fail-fast: false
    steps:
      - uses: actions/checkout@v4
        with:
          repository: SuperInstance/${{ matrix.repo }}
      - uses: actions/setup-python@v5
      - run: pip install -e '.[test]'
      - run: pytest tests/ -v
      - name: Report results
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.create({
              owner: 'SuperInstance',
              repo: context.repo.repo,
              title: `FLEET TEST FAILURE: ${{ matrix.repo }}`,
              body: `Tests failed in ${{ matrix.repo }}.\n\nRun: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}`,
              labels: ['fleet-task', 'priority-high', 'ci-failure']
            })
```

---

## 5. Cost Analysis: GitHub Free Tier Exploitation

### 5.1 Free Tier Resource Budget

| Resource | Free Tier Limit | Monthly Cost (paid) | Fleet Usage |
|----------|----------------|--------------------:|-------------|
| **Actions compute** | 2,000 min/month | $0.008/min (Linux) | ~1,300 min/month |
| **Codespaces** | 120 hrs/month (basic) | $0.36/hr (basic) | ~0 hrs (manual) |
| **Pages** | Unlimited (100GB bandwidth) | $0 | ~2GB/month |
| **Git LFS storage** | 500 MB | $0.25/GB/mo | ~50 MB |
| **Packages storage** | 500 MB | $0.25/GB/mo | ~100 MB |
| **Container Registry** | 500 MB storage + 500 MB bandwidth | $0.25/GB/mo | ~200 MB |
| **Private repos** | Unlimited | $0 | 6 repos |
| **Private collaborators** | Unlimited | $0 | 6 agents |
| **API requests** | 5,000/hr | N/A | ~1,400/hr |

### 5.2 Actions Budget Breakdown

```
FLUX Fleet Actions Budget: 2,000 minutes/month
═══════════════════════════════════════════════════════════════

Workflow                    Frequency    Avg Runtime    Monthly Min    % Budget
────────────────────────    ─────────    ───────────    ───────────    ────────
Beachcomb (scan bottles)    Every 60m    3 min          1,440 min      72%
CI on push (all agents)     ~5/day       5 min          750 min        37.5%
Fleet dashboard update      4/day        2 min          240 min        12%
Task router (on issue)      ~1/day       1 min          30 min         1.5%
Fleet-wide test             1/week       10 min         40 min         2%
────────────────────────    ─────────    ───────────    ───────────    ────────
TOTAL (without overlap)                                       ~2,500 min   125%
```

**Critical finding:** The fleet's desired workflow usage EXCEEDS the free tier by 25%. Mitigation required.

### 5.3 Budget Optimization Strategies

#### Strategy 1: Merge Beachcomb with Dashboard

Combine bottle scanning and dashboard generation into one workflow:

```yaml
# Combined: saves 240 min/month
name: Beachcomb + Dashboard
on:
  schedule:
    - cron: '0 * * * *'  # Every hour instead of every 30 min
```

**Savings:** 720 min → 480 min (beachcomb) + 0 min (separate dashboard) = 480 min. Saves 1,200 min/month.

#### Strategy 2: CI Only on push to main + PRs

Skip CI on push to feature branches:

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
```

**Savings:** Reduces CI runs from ~150/month to ~50/month = 250 min saved.

#### Strategy 3: Use Conditional Execution

Skip workflows when no changes detected:

```yaml
- name: Check for new bottles
  id: check
  run: |
    NEW=$(git log --since="1 hour ago" --name-only --format="" | grep "from-fleet/" | wc -l)
    echo "has_new=$NEW" >> $GITHUB_OUTPUT

- name: Run beachcomb
  if: steps.check.outputs.has_new > 0
  run: python tools/bottle-hygiene/bottle_checker.py
```

#### Strategy 4: Use Larger Timeouts

Use `schedule: cron '0 */2 * * *'` (every 2 hours) instead of hourly:

**Savings:** 720 min → 360 min (saves 360 min/month).

#### Optimized Budget

```
OPTIMIZED FLUX Fleet Actions Budget
═══════════════════════════════════════════════════════════════

Workflow                    Frequency    Avg Runtime    Monthly Min    % Budget
────────────────────────    ─────────    ───────────    ───────────    ────────
Beachcomb + Dashboard       Every 2h     5 min          1,800 min      90%
CI (main + PRs only)        ~50/month    5 min          250 min        12.5%
Task router (on issue)      ~1/day       1 min          30 min         1.5%
────────────────────────    ─────────    ───────────    ───────────    ────────
TOTAL                                                       ~1,630 min   81.5%

REMAINING: 370 min/month (safety margin)
```

### 5.4 Storage Budget

```
FLUX Fleet Storage Budget
═══════════════════════════════════════════════════════════════

Resource              Used       Free Limit    Utilization
──────────────────    ────       ──────────    ────────────
Git LFS               50 MB      500 MB        10%
Packages              100 MB     500 MB        20%
Container Registry    200 MB     500 MB        40%
──────────────────    ────       ──────────    ────────────
Total                 350 MB     1,500 MB*     23%

* LFS + Packages + Registry share separate 500 MB limits

Bandwidth (Pages)     2 GB       100 GB        2%
```

**Conclusion:** Storage is NOT a bottleneck. The fleet uses well under free tier limits.

### 5.5 Cost Comparison: Alternatives

| Service | Monthly Cost for FLUX Fleet | Notes |
|---------|---------------------------|-------|
| GitHub Free | $0 | 2,000 min Actions, limited storage |
| GitHub Pro | $4/user * 6 = $24/mo | 3,000 min Actions, 2GB LFS, private Pages |
| GitHub Team | $4/user * 6 = $24/mo | Same as Pro + team management |
| GitLab Free | $0 | 400 min CI, 1 GB storage |
| GitLab Premium | $29/user * 6 = $174/mo | Much more expensive |
| Bitbucket Free | $0 | 50 min CI, 1 GB LFS |
| Self-hosted (VPS) | $5-20/mo | Full control, but operational overhead |

**Recommendation:** GitHub Free is sufficient for the current fleet (6 agents). At 10+ agents, consider GitHub Team for better CI limits and team management.

---

## 6. Non-GitHub Alternatives

### 6.1 GitLab

| Feature | GitLab Equivalent | Agent Exploitability |
|---------|-------------------|---------------------|
| Actions | CI/CD Pipelines (`.gitlab-ci.yml`) | Excellent — more configurable than GitHub Actions |
| Issues | Issues (with epics, milestones) | Good — richer issue types |
| Projects | Boards + Epics | Good — epics provide hierarchy |
| Webhooks | Webhooks (similar to GitHub) | Good — same event-driven model |
| API | REST + GraphQL | Good — comprehensive API |
| Pages | GitLab Pages | Good — similar to GitHub Pages |
| Registry | Container Registry (built-in) | Better — more storage |
| Wiki | Wiki (built-in) | Good — API support |
| Free tier | 400 CI min/month, 5 GB storage | Worse — less CI time |

**GitLab advantages for agents:**
1. **Self-hosted option**: Full control, no rate limits
2. **Built-in Container Registry**: No separate service needed
3. **Epics**: Hierarchical task management (Issue → Epic → Initiative)
4. **Runner registration**: Agents can register their own CI runners (unlimited compute)

**GitLab disadvantages:**
1. **Less CI time on free tier** (400 min vs 2,000 min)
2. **Smaller ecosystem**: Fewer third-party integrations
3. **UI complexity**: More complex interface, harder for human collaborators
4. **Webhook reliability**: Less mature than GitHub's webhook system

### 6.2 Bitbucket

| Feature | Bitbucket Equivalent | Agent Exploitability |
|---------|---------------------|---------------------|
| Actions | Bitbucket Pipelines | Limited — 50 free min/month |
| Issues | Jira integration (separate product) | Poor — requires Jira |
| Projects | No equivalent | Poor |
| Webhooks | Webhooks | Adequate |
| API | REST API | Adequate |
| Pages | No equivalent | None |

**Verdict:** Bitbucket is not suitable for agent fleet coordination. The tight Jira integration is a disadvantage (Jira is a separate product with its own API). The 50-minute CI limit is insufficient.

### 6.3 Codeberg

| Feature | Codeberg Equivalent | Agent Exploitability |
|---------|--------------------|---------------------|
| Actions | Woodpecker CI (separate) | Adequate — but separate service |
| Issues | Issues (Gitea-based) | Good — Gitea has good API |
| Projects | Projects (Kanban) | Adequate |
| Webhooks | Webhooks | Good |
| API | Gitea API (REST) | Good — simpler than GitHub |
| Free tier | Unlimited | Best — fully free, no limits |

**Codeberg advantages:**
1. **Fully free**: No rate limits, no compute limits
2. **Open source**: Based on Gitea, fully auditable
3. **No vendor lock-in**: Self-hostable

**Codeberg disadvantages:**
1. **Smaller infrastructure**: May have reliability issues under load
2. **Less mature Actions**: Woodpecker CI is less feature-rich than GitHub Actions
3. **Smaller community**: Fewer integrations and tools
4. **No Codespaces equivalent**: No cloud development environments

### 6.4 Decentralized: IPFS

**Concept:** Use IPFS (InterPlanetary File System) for content-addressed, decentralized storage of agent messages.

**How agents could use IPFS:**
- Messages stored as content-addressed blocks (CID-based addressing)
- No central server — agents pin messages they care about
- Content deduplication — identical messages share storage

**Challenges for agent coordination:**
1. **No event delivery.** IPFS is a storage system, not a messaging system. Agents must poll or use IPFS pubsub (experimental).
2. **No access control.** All content is public by default. Private content requires encryption (IPNS + encryption).
3. **No ordering.** Content-addressed storage has no concept of temporal ordering. Messages can't be ordered by time.
4. **Variable persistence.** Unpinned content is garbage-collected. Agents must pin messages to keep them alive.

**Verdict:** IPFS is a complement, not a replacement, for git-based coordination. Useful for large binary artifacts (model weights, datasets) but not for real-time coordination.

### 6.5 Decentralized: Radicle

**Concept:** Radicle is a peer-to-peer, decentralized code collaboration network built on top of Git. No central server — repos are synced directly between peers.

**How agents could use Radicle:**
- Push/pull repos directly between agents (no GitHub intermediary)
- Built-in social features (issues, patches — equivalent to PRs)
- Cryptographic identity (each agent has a key pair)
- Local-first — agents don't need internet access to collaborate

**Advantages for fleet coordination:**
1. **No rate limits.** No central server = no rate limits.
2. **No single point of failure.** The fleet can operate even if GitHub is down.
3. **Cryptographic identity.** Agent identity is verified by public key, not by a username.
4. **True decentralization.** No vendor lock-in.

**Challenges:**
1. **Immature.** Radicle is pre-1.0. API and tooling are still evolving.
2. **Discovery.** Without a central server, discovering other agents' repos requires a DHT (Distributed Hash Table), which has latency.
3. **No CI/CD.** No equivalent of GitHub Actions. Agents must run CI locally.
4. **No webhooks.** No event-driven triggers.
5. **Limited adoption.** Very small user base. Less community tooling.

**Verdict:** Radicle is the most promising decentralized alternative, but not ready for production fleet use. Monitor for v1.0 release.

### 6.6 Custom: Self-Hosted Git + Message Bus

**Architecture:**

```
┌─────────────────────────────────────────────────────────┐
│          CUSTOM FLEET INFRASTRUCTURE                      │
│                                                          │
│  ┌──────────┐     ┌──────────────┐     ┌──────────────┐ │
│  │ Gitea/   │     │ Redis /      │     │ Nginx        │ │
│  │ Gogs     │────▶│ NATS /       │────▶│ (reverse     │ │
│  │ (git)    │     │ RabbitMQ     │     │  proxy +     │ │
│  │          │     │ (message bus)│     │  webhook     │ │
│  └──────────┘     └──────────────┘     │  receiver)   │ │
│       │                 │             └──────────────┘ │
│       │                 │                               │
│  ┌────┴────┐      ┌────┴────┐                          │
│  │ CI/CD   │      │ Agent   │                          │
│  │ (Drone/ │      │ Registry│                          │
│  │  Woodpecker)    │ (consul)│                          │
│  └─────────┘      └─────────┘                          │
│                                                          │
│  Cost: $5-20/month (single VPS)                          │
│  - 2 CPU, 4 GB RAM, 80 GB SSD                           │
│  - Unlimited git repos                                   │
│  - Unlimited CI (bounded by compute)                     │
│  - Unlimited message bus throughput                      │
│  - Full control over all components                      │
└─────────────────────────────────────────────────────────┘
```

**Advantages:**
1. **No rate limits.** No API throttling, no CI minute budgets.
2. **Full control.** Customize every component to fleet needs.
3. **Low cost.** $5-20/month for a capable VPS.
4. **Privacy.** All data stays on infrastructure you control.
5. **No vendor lock-in.** Can migrate any component independently.

**Disadvantages:**
1. **Operational overhead.** Someone must maintain the infrastructure. For a fleet of autonomous agents, this means one agent (or Casey) must be the sysadmin.
2. **No managed services.** No GitHub Copilot, no Codespaces, no Actions marketplace.
3. **Reliability.** A single VPS is a single point of failure. Need backups, monitoring, and failover.
4. **Security.** Self-hosted means self-secured. Must handle TLS certificates, firewall rules, and access control.

**Recommendation for the FLUX fleet:**
- **Current (6 agents):** GitHub Free is sufficient and eliminates operational overhead.
- **Medium-term (10-20 agents):** Consider self-hosted Gitea + Redis for unlimited API access and message bus capabilities. Use GitHub for public repos and community interaction.
- **Long-term (50+ agents):** Hybrid approach — GitHub for public-facing repos, self-hosted infrastructure for internal coordination.

---

## 7. Appendices

### Appendix A: GitHub API Quick Reference for Fleet Agents

```python
# Common API endpoints for fleet agent operations

ENDPOINTS = {
    # Issues
    "list_issues": "GET /repos/{owner}/{repo}/issues",
    "create_issue": "POST /repos/{owner}/{repo}/issues",
    "update_issue": "PATCH /repos/{owner}/{repo}/issues/{number}",
    "list_comments": "GET /repos/{owner}/{repo}/issues/{number}/comments",
    "create_comment": "POST /repos/{owner}/{repo}/issues/{number}/comments",

    # Pull Requests
    "list_prs": "GET /repos/{owner}/{repo}/pulls",
    "create_pr": "POST /repos/{owner}/{repo}/pulls",
    "merge_pr": "PUT /repos/{owner}/{repo}/pulls/{number}/merge",
    "request_review": "POST /repos/{owner}/{repo}/pulls/{number}/requested_reviewers",

    # Repositories
    "get_file": "GET /repos/{owner}/{repo}/contents/{path}",
    "create_file": "PUT /repos/{owner}/{repo}/contents/{path}",
    "update_file": "PUT /repos/{owner}/{repo}/contents/{path}",
    "list_branches": "GET /repos/{owner}/{repo}/branches",
    "create_branch": "POST /repos/{owner}/{repo}/git/refs",

    # Actions
    "list_workflows": "GET /repos/{owner}/{repo}/actions/workflows",
    "trigger_workflow": "POST /repos/{owner}/{repo}/actions/workflows/{id}/dispatches",
    "list_runs": "GET /repos/{owner}/{repo}/actions/runs",

    # Search
    "search_code": "GET /search/code?q={query}",
    "search_issues": "GET /search/issues?q={query}",
    "search_repos": "GET /search/repositories?q={query}",

    # Webhooks
    "list_webhooks": "GET /repos/{owner}/{repo}/hooks",
    "create_webhook": "POST /repos/{owner}/{repo}/hooks",
}
```

### Appendix B: A2A Protocol vs GitHub Feature Mapping

| A2A Opcode | GitHub Equivalent | Latency | Reliability |
|------------|-------------------|---------|-------------|
| TELL (0x60) | Issue comment / bottle file | Hours | Medium |
| ASK (0x61) | Issue with assignee / PR review request | Hours | Medium |
| DELEGATE (0x62) | Issue with labels + assignee | Hours | Medium |
| DELEGATE_RESULT (0x63) | Issue comment with result / PR merge | Hours | Medium-High |
| BROADCAST (0x66) | repository_dispatch to all vessels | Minutes | High |
| REDUCE (0x67) | Aggregating issue comments / dashboard | Hours | Medium |
| TRUST_CHECK (0x70) | Checking agent's repo activity / CAPABILITY.toml | Seconds | High |
| TRUST_UPDATE (0x71) | Updating trust score in shared state file | Minutes | Medium |
| CAP_REQUIRE (0x74) | Protected branch rules / PR review requirement | Seconds | High |
| CAP_GRANT (0x76) | Adding agent to team / granting repo write access | Minutes | High |
| EMERGENCY_STOP (0x7B) | Issue with "priority-P0" label / workflow_dispatch | Minutes | High |

### Appendix C: Fleet Communication Channel Comparison (Updated)

| Channel | Latency | Bandwidth | Reliability | Cost | Event-Driven |
|---------|---------|-----------|-------------|------|-------------|
| Message-in-bottle | 4-24 hrs | Low (text) | 60% ack rate | $0 | No |
| Issues + API | 1-8 hrs | Medium (markdown) | 80% | $0 | Partial (webhooks) |
| PR + CI | 1-24 hrs | High (binary) | 95% | Free tier | Yes (push event) |
| Actions + API | 1-5 min | High (any) | 90% | 2000 min/mo | Yes (cron + dispatch) |
| Webhooks + receiver | < 5 sec | Medium (JSON) | 95%+ | VPS cost | Yes (core mechanism) |
| A2A (native) | < 1 sec | High (binary) | Designed for it | N/A | Yes |
| Self-hosted message bus | < 100 ms | High (binary) | 99%+ | VPS cost | Yes |

### Appendix D: Recommended Fleet Architecture Evolution

```
Phase 1 (Current — 6 agents):
  ┌────────────────────────────────────────────┐
  │ GitHub Free + Message-in-a-Bottle           │
  │ - Issues for task assignment               │
  │ - Bottles for async communication          │
  │ - Direct pushes for code delivery          │
  │ - Actions for beachcomb + CI              │
  └────────────────────────────────────────────┘
         │
         ▼
Phase 2 (Near-term — 10-20 agents):
  ┌────────────────────────────────────────────┐
  │ GitHub Free + Actions + API + Webhooks     │
  │ - Automated task router (Actions)          │
  │ - repository_dispatch for event routing    │
  │ - Fleet dashboard (Pages)                  │
  │ - Branch protection for quality gates      │
  │ - Issue forms for structured tasks         │
  └────────────────────────────────────────────┘
         │
         ▼
Phase 3 (Medium-term — 20-50 agents):
  ┌────────────────────────────────────────────┐
  │ Hybrid: GitHub + Self-Hosted Message Bus   │
  │ - GitHub for public repos + CI             │
  │ - Self-hosted Redis/NATS for real-time     │
  │ - Webhook receiver routes to message bus   │
  │ - Agent registry in shared database        │
  │ - A2A protocol over message bus            │
  └────────────────────────────────────────────┘
         │
         ▼
Phase 4 (Long-term — 50+ agents):
  ┌────────────────────────────────────────────┐
  │ Full Self-Hosted + Decentralized           │
  │ - Gitea for git hosting                    │
  │ - NATS/Redis for message bus               │
  │ - Consul for agent discovery               │
  │ - A2A protocol natively over message bus   │
  │ - GitHub mirror for public presence        │
  │ - Radicle for disaster recovery            │
  └────────────────────────────────────────────┘
```

### Appendix E: Glossary

| Term | Definition |
|------|-----------|
| **A2A** | Agent-to-Agent communication protocol (FLUX native, opcodes 0x60-0x7B) |
| **Beachcomb** | Scanning vessel repos for new bottles or changes |
| **Bottle** | Markdown message file in a vessel repo, used for async communication |
| **CAPABILITY.toml** | TOML file declaring an agent's capabilities, type, and communication channels |
| **Codespace** | GitHub's cloud-based development environment |
| **DevConfig** | `devcontainer.json` defining a reproducible development environment |
| **FGPAT** | Fine-Grained Personal Access Token — GitHub's newer, scoped auth tokens |
| **Fleet** | Collection of autonomous agents working together |
| **INCREMENTS+2** | FLUX trust scoring model (0-1000 range) |
| **Lighthouse** | Fleet coordinator agent (Oracle1) |
| **Message Bus** | Software system for real-time message routing (Redis, NATS, RabbitMQ) |
| **PAT** | Personal Access Token — GitHub authentication credential |
| **repository_dispatch** | GitHub webhook event that triggers Actions in another repo |
| **Vessel** | An individual agent's personal repository |

---

*This document is a living artifact. As the fleet evolves and GitHub releases new features, this survey should be updated. Last updated: 2026-04-13 by Super Z (Fleet Agent, Architect-rank).*

*Related documents:*
- *TOPO-001: Fleet Communication Topology Analysis*
- *Module 3: A2A Protocol (bootcamp/module-03-a2a-protocol.md)*
- *Module 6: Multi-Agent Fleet Patterns (bootcamp/module-06-fleet-patterns.md)*
- *Research: Agent Orchestration (research/agent_orchestration.md)*
- *ASYNC-001: Async Primitives Specification (async-primitives-spec.md)*
