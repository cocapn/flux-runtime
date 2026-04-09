"""System Mutator — applies mutations (potential improvements) to the system.

Each mutation is a hypothesis: "If I change X, the system will be better."
The mutator proposes, applies, validates, commits, or rolls back mutations
based on profiler data and pattern mining results.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Any, Callable

from .genome import Genome, MutationStrategy, OptimizationRecord
from .pattern_mining import DiscoveredPattern


# ── Proposal Types ────────────────────────────────────────────────────────────

@dataclass
class MutationProposal:
    """A proposed mutation to the system."""
    strategy: MutationStrategy
    target: str  # module path or tile name
    description: str
    kwargs: dict[str, Any] = field(default_factory=dict)
    estimated_speedup: float = 1.0
    estimated_risk: float = 0.5  # 0.0 = safe, 1.0 = risky
    priority: float = 0.0  # higher = more impactful, should try first
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def __repr__(self) -> str:
        return (
            f"MutationProposal({self.strategy.value}, "
            f"target={self.target!r}, speedup={self.estimated_speedup:.2f}, "
            f"risk={self.estimated_risk:.2f})"
        )


@dataclass
class MutationResult:
    """Result of applying a mutation."""
    proposal: MutationProposal
    success: bool
    fitness_before: float = 0.0
    fitness_after: float = 0.0
    fitness_delta: float = 0.0
    measured_speedup: float = 1.0
    validation_passed: bool = True
    error: str = ""
    elapsed_ns: int = 0

    @property
    def is_improvement(self) -> bool:
        """Did the mutation actually improve things?"""
        return self.success and self.fitness_delta > 0

    def __repr__(self) -> str:
        status = "OK" if self.success else "FAIL"
        return (
            f"MutationResult({status}, "
            f"delta={self.fitness_delta:+.4f}, "
            f"speedup={self.measured_speedup:.2f})"
        )


@dataclass
class MutationRecord:
    """Record of a committed or failed mutation."""
    proposal: MutationProposal
    result: MutationResult
    committed: bool
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


# ── System Mutator ────────────────────────────────────────────────────────────

class SystemMutator:
    """Applies mutations (potential improvements) to the running system.

    Each mutation is a hypothesis: "If I change X, the system will be better."
    The mutator:
    1. Proposes a mutation based on profiler data and pattern mining
    2. Applies the mutation to a COPY (not the live system)
    3. Validates correctness (does the mutated version produce same results?)
    4. Measures improvement (is it actually faster?)
    5. If both pass → commit the mutation (hot-swap into live system)
    6. If either fails → rollback, record the failure
    """

    def __init__(
        self,
        max_mutations_per_step: int = 5,
        min_speedup_threshold: float = 1.05,
        max_risk_tolerance: float = 0.8,
    ) -> None:
        self._mutations_applied: list[MutationRecord] = []
        self._mutations_failed: list[MutationRecord] = []
        self._mutations_pending: list[MutationProposal] = []
        self._max_per_step: int = max_mutations_per_step
        self._min_speedup: float = min_speedup_threshold
        self._max_risk: float = max_risk_tolerance

    # ── Proposal ────────────────────────────────────────────────────────

    def propose_mutations(
        self,
        genome: Genome,
        patterns: list[DiscoveredPattern],
    ) -> list[MutationProposal]:
        """Analyze current state and propose improvements.

        For each hot pattern:
          - Propose: fuse into a single optimized tile
        For each HEAT module still in Python:
          - Propose: recompile to C/Rust
        For each slow tile composition:
          - Propose: replace with a faster alternative

        Args:
            genome: Current genome snapshot.
            patterns: Discovered patterns from the miner.

        Returns:
            List of MutationProposals sorted by priority descending.
        """
        proposals: list[MutationProposal] = []

        # 1. Propose recompilation for hot modules still in Python
        self._propose_recompilations(genome, proposals)

        # 2. Propose pattern fusions
        self._propose_pattern_fusions(genome, patterns, proposals)

        # 3. Propose tile optimizations
        self._propose_tile_optimizations(genome, proposals)

        # 4. Propose tile merges
        self._propose_tile_merges(genome, proposals)

        # Sort by priority descending
        proposals.sort(key=lambda p: p.priority, reverse=True)

        # Filter by risk tolerance
        proposals = [p for p in proposals if p.estimated_risk <= self._max_risk]

        self._mutations_pending = proposals[:self._max_per_step]
        return self._mutations_pending

    def _propose_recompilations(
        self, genome: Genome, proposals: list[MutationProposal]
    ) -> None:
        """Propose language recompilation for hot modules."""
        for mod_path, snap in genome.modules.items():
            if snap.heat_level == "FROZEN":
                continue

            current_lang = genome.language_assignments.get(mod_path, snap.language)
            if current_lang != "python":
                continue  # already compiled

            if snap.heat_level == "HEAT":
                proposals.append(MutationProposal(
                    strategy=MutationStrategy.RECOMPILE_LANGUAGE,
                    target=mod_path,
                    description=f"Recompile HEAT module {mod_path} from Python to C+SIMD",
                    kwargs={"new_language": "c_simd"},
                    estimated_speedup=16.0,
                    estimated_risk=0.4,
                    priority=10.0 * snap.call_count,
                ))
            elif snap.heat_level == "HOT":
                proposals.append(MutationProposal(
                    strategy=MutationStrategy.RECOMPILE_LANGUAGE,
                    target=mod_path,
                    description=f"Recompile HOT module {mod_path} from Python to Rust",
                    kwargs={"new_language": "rust"},
                    estimated_speedup=10.0,
                    estimated_risk=0.3,
                    priority=8.0 * snap.call_count,
                ))
            elif snap.heat_level == "WARM":
                proposals.append(MutationProposal(
                    strategy=MutationStrategy.RECOMPILE_LANGUAGE,
                    target=mod_path,
                    description=f"Recompile WARM module {mod_path} from Python to TypeScript",
                    kwargs={"new_language": "typescript"},
                    estimated_speedup=2.0,
                    estimated_risk=0.1,
                    priority=3.0 * snap.call_count,
                ))

    def _propose_pattern_fusions(
        self,
        genome: Genome,
        patterns: list[DiscoveredPattern],
        proposals: list[MutationProposal],
    ) -> None:
        """Propose fusing hot patterns into tiles."""
        for pattern in patterns[:10]:  # top 10 patterns
            if pattern.length < 2:
                continue

            pattern_name = f"evolved_{pattern.name}"
            # Check if already exists
            if pattern_name in genome.tiles:
                continue

            proposals.append(MutationProposal(
                strategy=MutationStrategy.FUSE_PATTERN,
                target=",".join(pattern.sequence),
                description=(
                    f"Fuse {pattern.length}-module pattern "
                    f"({pattern.frequency}x occurrences) into tile"
                ),
                kwargs={
                    "pattern_name": pattern_name,
                    "cost_savings": pattern.estimated_speedup - 1.0,
                    "sequence": list(pattern.sequence),
                    "frequency": pattern.frequency,
                },
                estimated_speedup=pattern.estimated_speedup,
                estimated_risk=0.2,
                priority=pattern.benefit_score * 2.0,
            ))

    def _propose_tile_optimizations(
        self, genome: Genome, proposals: list[MutationProposal]
    ) -> None:
        """Propose replacing expensive tiles with cheaper alternatives."""
        for tile_name, tile_snap in genome.tiles.items():
            if tile_snap.cost_estimate < 2.0:
                continue  # not expensive enough

            # Propose replacing with a cheaper version
            proposals.append(MutationProposal(
                strategy=MutationStrategy.REPLACE_TILE,
                target=tile_name,
                description=f"Replace expensive tile {tile_name} (cost {tile_snap.cost_estimate})",
                kwargs={"new_cost": tile_snap.cost_estimate * 0.5},
                estimated_speedup=2.0,
                estimated_risk=0.3,
                priority=tile_snap.cost_estimate,
            ))

    def _propose_tile_merges(
        self, genome: Genome, proposals: list[MutationProposal]
    ) -> None:
        """Propose merging co-occurring tiles."""
        tile_names = sorted(genome.tiles.keys())
        for i in range(min(len(tile_names), 10)):
            for j in range(i + 1, min(len(tile_names), 10)):
                tile_a = tile_names[i]
                tile_b = tile_names[j]
                merged = f"{tile_a}__merged__{tile_b}"
                if merged in genome.tiles:
                    continue

                proposals.append(MutationProposal(
                    strategy=MutationStrategy.MERGE_TILES,
                    target=merged,
                    description=f"Merge tiles {tile_a} + {tile_b}",
                    kwargs={
                        "tile_a": tile_a,
                        "tile_b": tile_b,
                        "merged_name": merged,
                    },
                    estimated_speedup=1.3,
                    estimated_risk=0.4,
                    priority=1.0,
                ))

    # ── Apply ───────────────────────────────────────────────────────────

    def apply_mutation(
        self,
        proposal: MutationProposal,
        genome: Genome,
        validation_fn: Optional[Callable[[Genome], bool]] = None,
    ) -> MutationResult:
        """Apply a mutation and validate it.

        1. Clone the genome
        2. Apply the mutation
        3. Evaluate fitness
        4. Validate correctness
        5. Return result

        Args:
            proposal: The mutation to apply.
            genome: The current genome (not modified in place).
            validation_fn: Optional correctness validator.

        Returns:
            MutationResult with outcome details.
        """
        start = time.monotonic_ns()
        fitness_before = genome.fitness_score

        try:
            # Apply mutation (creates a new genome)
            mutated = genome.mutate(
                strategy=proposal.strategy,
                target=proposal.target,
                **proposal.kwargs,
            )

            # Evaluate fitness
            mutated.evaluate_fitness()
            fitness_after = mutated.fitness_score

            # Validate correctness if provided
            validation_passed = True
            if validation_fn is not None:
                validation_passed = validation_fn(mutated)

            elapsed = time.monotonic_ns() - start

            success = validation_passed and fitness_after >= fitness_before

            return MutationResult(
                proposal=proposal,
                success=success,
                fitness_before=fitness_before,
                fitness_after=fitness_after,
                fitness_delta=fitness_after - fitness_before,
                measured_speedup=fitness_after / max(fitness_before, 0.001),
                validation_passed=validation_passed,
                elapsed_ns=elapsed,
            )

        except Exception as exc:
            elapsed = time.monotonic_ns() - start
            return MutationResult(
                proposal=proposal,
                success=False,
                fitness_before=fitness_before,
                error=str(exc),
                elapsed_ns=elapsed,
            )

    # ── Commit / Rollback ───────────────────────────────────────────────

    def commit_mutation(
        self,
        proposal: MutationProposal,
        result: MutationResult,
    ) -> None:
        """Commit a validated mutation to the live system.

        Args:
            proposal: The original proposal.
            result: The successful result.
        """
        record = MutationRecord(
            proposal=proposal,
            result=result,
            committed=True,
        )
        self._mutations_applied.append(record)

    def rollback_mutation(
        self,
        proposal: MutationProposal,
        result: MutationResult,
    ) -> None:
        """Rollback a failed mutation.

        Args:
            proposal: The failed proposal.
            result: The failed result.
        """
        record = MutationRecord(
            proposal=proposal,
            result=result,
            committed=False,
        )
        self._mutations_failed.append(record)

    # ── Queries ─────────────────────────────────────────────────────────

    def get_success_rate(self) -> float:
        """What fraction of mutations were successful?

        Returns:
            Fraction between 0.0 and 1.0. Returns 0.0 if no mutations.
        """
        total = len(self._mutations_applied) + len(self._mutations_failed)
        if total == 0:
            return 0.0
        return len(self._mutations_applied) / total

    def get_total_speedup(self) -> float:
        """Cumulative speedup from all successful mutations.

        Returns:
            Product of all successful speedup factors.
        """
        speedup = 1.0
        for record in self._mutations_applied:
            speedup *= record.result.measured_speedup
        return speedup

    def get_applied_mutations(self) -> list[MutationRecord]:
        """Get all successfully committed mutations."""
        return list(self._mutations_applied)

    def get_failed_mutations(self) -> list[MutationRecord]:
        """Get all failed mutations."""
        return list(self._mutations_failed)

    def get_pending_mutations(self) -> list[MutationProposal]:
        """Get currently pending mutation proposals."""
        return list(self._mutations_pending)

    def clear_history(self) -> None:
        """Clear all mutation history."""
        self._mutations_applied.clear()
        self._mutations_failed.clear()
        self._mutations_pending.clear()

    @property
    def total_mutations(self) -> int:
        """Total number of mutations attempted."""
        return len(self._mutations_applied) + len(self._mutations_failed)

    @property
    def success_count(self) -> int:
        """Number of successful mutations."""
        return len(self._mutations_applied)

    @property
    def failure_count(self) -> int:
        """Number of failed mutations."""
        return len(self._mutations_failed)

    def __repr__(self) -> str:
        return (
            f"SystemMutator("
            f"applied={self.success_count}, "
            f"failed={self.failure_count}, "
            f"pending={len(self._mutations_pending)}, "
            f"speedup={self.get_total_speedup():.2f}x)"
        )
