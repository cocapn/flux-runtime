"""Evolution Engine — the main self-evolution loop.

This is the DJ at the center of the rave:
- Listens to the room (profiler)
- Feels the rhythm (pattern mining)
- Tries new beats (mutation proposals)
- Keeps what works (validation + commit)
- Drops what doesn't (rollback)
- Gets better over time (fitness tracking)

The evolution loop:
1. CAPTURE: Take a genome snapshot of the current system
2. PROFILE: Run representative workloads, collect execution data
3. MINE: Find hot patterns in execution traces
4. PROPOSE: Generate mutation proposals based on findings
5. EVALUATE: Test each proposal (correctness + speed)
6. COMMIT: Apply successful mutations to the live system
7. MEASURE: Compare new genome to old genome (fitness delta)
8. RECORD: Save the new genome, increment generation
9. REPEAT
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Any, Callable

from .genome import Genome
from .pattern_mining import PatternMiner, DiscoveredPattern, ExecutionTrace
from .mutator import SystemMutator, MutationProposal, MutationResult, MutationRecord
from .validator import CorrectnessValidator, ValidationResult
from flux.adaptive.profiler import AdaptiveProfiler, HeatLevel
from flux.adaptive.selector import AdaptiveSelector


# ── Record Types ───────────────────────────────────────────────────────────────

@dataclass
class EvolutionRecord:
    """Record of one evolution step."""
    generation: int
    fitness_before: float
    fitness_after: float
    fitness_delta: float
    mutations_proposed: int
    mutations_committed: int
    mutations_failed: int
    patterns_found: int
    validation_result: Optional[ValidationResult] = None
    elapsed_ns: int = 0
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    @property
    def is_improvement(self) -> bool:
        return self.fitness_delta > 0

    @property
    def success_rate(self) -> float:
        total = self.mutations_committed + self.mutations_failed
        if total == 0:
            return 0.0
        return self.mutations_committed / total

    def __repr__(self) -> str:
        arrow = "↑" if self.is_improvement else "→"
        return (
            f"Gen {self.generation} {arrow} "
            f"fitness={self.fitness_after:.4f} "
            f"(Δ{self.fitness_delta:+.4f}) "
            f"mutations={self.mutations_committed}/{self.mutations_proposed}"
        )


@dataclass
class EvolutionReport:
    """Summary of an evolution run."""
    generations: int = 0
    initial_fitness: float = 0.0
    final_fitness: float = 0.0
    total_speedup: float = 1.0
    mutations_proposed: int = 0
    mutations_succeeded: int = 0
    mutations_failed: int = 0
    tiles_created: int = 0
    modules_recompiled: int = 0
    patterns_discovered: int = 0
    records: list[EvolutionRecord] = field(default_factory=list)
    elapsed_ns: int = 0

    @property
    def fitness_improvement(self) -> float:
        return self.final_fitness - self.initial_fitness

    @property
    def fitness_improvement_pct(self) -> float:
        if self.initial_fitness == 0:
            return 0.0
        return (self.fitness_improvement / self.initial_fitness) * 100.0

    @property
    def success_rate(self) -> float:
        total = self.mutations_succeeded + self.mutations_failed
        if total == 0:
            return 0.0
        return self.mutations_succeeded / total

    def __repr__(self) -> str:
        return (
            f"EvolutionReport("
            f"generations={self.generations}, "
            f"fitness={self.initial_fitness:.4f}→{self.final_fitness:.4f}, "
            f"speedup={self.total_speedup:.2f}x, "
            f"mutations={self.mutations_succeeded}/{self.mutations_proposed})"
        )


@dataclass
class EvolutionStep:
    """Result of one evolution step."""
    generation: int
    fitness_before: float
    fitness_after: float
    mutations_proposed: int
    mutations_committed: int
    patterns_found: int
    time_ns: int = 0
    record: Optional[EvolutionRecord] = None

    @property
    def improved(self) -> bool:
        return self.fitness_after > self.fitness_before

    def __repr__(self) -> str:
        arrow = "↑" if self.improved else "→"
        return (
            f"EvolutionStep(gen={self.generation} {arrow} "
            f"fitness={self.fitness_after:.4f})"
        )


# ── Evolution Engine ───────────────────────────────────────────────────────────

class EvolutionEngine:
    """The main self-evolution engine.

    Orchestrates the full evolution loop: capture → profile → mine →
    propose → evaluate → commit → measure → repeat.

    Args:
        profiler: The AdaptiveProfiler for execution monitoring.
        selector: The AdaptiveSelector for language recommendations.
        validator: Optional CorrectnessValidator for mutation validation.
        max_generations: Maximum evolution cycles (safety limit).
        convergence_threshold: Stop if fitness improvement < threshold.
    """

    def __init__(
        self,
        profiler: Optional[AdaptiveProfiler] = None,
        selector: Optional[AdaptiveSelector] = None,
        validator: Optional[CorrectnessValidator] = None,
        max_generations: int = 100,
        convergence_threshold: float = 0.001,
    ) -> None:
        self.genome = Genome()
        self.profiler = profiler or AdaptiveProfiler()
        self.selector = selector or AdaptiveSelector(self.profiler)
        self.validator = validator or CorrectnessValidator()
        self.miner = PatternMiner(self.profiler)
        self.mutator = SystemMutator()
        self.generation: int = 0
        self._history: list[EvolutionRecord] = []
        self._max_generations: int = max_generations
        self._convergence_threshold: float = convergence_threshold

    # ── Main Loop ───────────────────────────────────────────────────────

    def evolve(
        self,
        module_root: Any,
        tile_registry: Any,
        workloads: list[Callable[[], None]],
        max_generations: int = 10,
        validation_fn: Optional[Callable[[Genome], bool]] = None,
    ) -> EvolutionReport:
        """Run the evolution loop for N generations.

        Args:
            module_root: The root ModuleContainer.
            tile_registry: Available tiles (TileRegistry).
            workloads: List of workload functions to profile.
            max_generations: How many evolution cycles to run.
            validation_fn: Optional function that validates system correctness.

        Returns:
            EvolutionReport with all improvements made.
        """
        start = time.monotonic_ns()
        report = EvolutionReport()
        report.generations = max_generations

        # Capture initial state
        self.genome.capture(module_root, tile_registry, self.profiler, self.selector)
        self.genome.evaluate_fitness()
        report.initial_fitness = self.genome.fitness_score

        # Capture validation baseline
        self.validator.capture_baseline()

        for gen in range(max_generations):
            if gen >= self._max_generations:
                break

            # Run one step
            step = self.step(
                module_root=module_root,
                tile_registry=tile_registry,
                workload=workloads[gen % len(workloads)],
                validation_fn=validation_fn,
            )

            report.records.append(step.record) if step.record else None
            report.mutations_proposed += step.mutations_proposed
            report.mutations_succeeded += step.mutations_committed
            report.patterns_discovered += step.patterns_found

            # Check convergence
            if gen > 0 and step.record and not step.record.is_improvement:
                if step.record.fitness_delta >= -self._convergence_threshold:
                    # Converged — no significant improvement
                    break

        # Final state
        final_genome = Genome()
        final_genome.capture(module_root, tile_registry, self.profiler, self.selector)
        final_genome.evaluate_fitness()
        report.final_fitness = final_genome.fitness_score
        report.total_speedup = self.mutator.get_total_speedup()
        report.mutations_failed = self.mutator.failure_count
        report.elapsed_ns = time.monotonic_ns() - start

        return report

    def step(
        self,
        module_root: Any,
        tile_registry: Any,
        workload: Optional[Callable[[], None]] = None,
        validation_fn: Optional[Callable[[Genome], bool]] = None,
    ) -> EvolutionStep:
        """Run one evolution step: capture → profile → mine → propose → evaluate → commit.

        Args:
            module_root: The root ModuleContainer.
            tile_registry: Available tiles (TileRegistry).
            workload: Optional workload function to profile.
            validation_fn: Optional correctness validator.

        Returns:
            EvolutionStep with the outcome of this step.
        """
        step_start = time.monotonic_ns()
        self.generation += 1

        # 1. CAPTURE — Take genome snapshot
        self.genome.capture(module_root, tile_registry, self.profiler, self.selector)
        self.genome.evaluate_fitness()
        fitness_before = self.genome.fitness_score

        # 2. PROFILE — Run workload if provided
        if workload is not None:
            trace = self._profile_workload(workload)
            self.miner.record_trace(trace)

        # 3. MINE — Find hot patterns
        patterns = self.miner.mine_patterns(min_frequency=2, min_length=2)
        patterns_found = len(patterns)

        # 4. PROPOSE — Generate mutation proposals
        proposals = self.mutator.propose_mutations(self.genome, patterns)
        mutations_proposed = len(proposals)

        # 5-6. EVALUATE + COMMIT — Test and apply
        mutations_committed = 0
        mutations_failed = 0
        fitness_after = fitness_before
        validation_result: Optional[ValidationResult] = None

        for proposal in proposals:
            result = self.mutator.apply_mutation(
                proposal, self.genome, validation_fn
            )

            if result.success:
                # Commit
                self.mutator.commit_mutation(proposal, result)

                # Update live genome
                self.genome = self.genome.mutate(
                    strategy=proposal.strategy,
                    target=proposal.target,
                    **proposal.kwargs,
                )
                self.genome.evaluate_fitness()
                fitness_after = self.genome.fitness_score

                # Update selector language assignments
                if proposal.strategy.value == "recompile_language":
                    new_lang = proposal.kwargs.get("new_language", "python")
                    self.selector.apply_recommendation(proposal.target, new_lang)

                mutations_committed += 1
            else:
                # Rollback
                self.mutator.rollback_mutation(proposal, result)
                mutations_failed += 1

        # 7. MEASURE — Run validation
        validation_result = self.validator.validate()

        # 8. RECORD — Save evolution record
        elapsed = time.monotonic_ns() - step_start
        record = EvolutionRecord(
            generation=self.generation,
            fitness_before=fitness_before,
            fitness_after=fitness_after,
            fitness_delta=fitness_after - fitness_before,
            mutations_proposed=mutations_proposed,
            mutations_committed=mutations_committed,
            mutations_failed=mutations_failed,
            patterns_found=patterns_found,
            validation_result=validation_result,
            elapsed_ns=elapsed,
        )
        self._history.append(record)

        return EvolutionStep(
            generation=self.generation,
            fitness_before=fitness_before,
            fitness_after=fitness_after,
            mutations_proposed=mutations_proposed,
            mutations_committed=mutations_committed,
            patterns_found=patterns_found,
            time_ns=elapsed,
            record=record,
        )

    # ── Profiling Helper ────────────────────────────────────────────────

    def _profile_workload(self, workload: Callable[[], None]) -> ExecutionTrace:
        """Run a workload and capture its execution trace.

        Args:
            workload: Callable to execute and profile.

        Returns:
            ExecutionTrace with the captured module calls.
        """
        start = time.monotonic_ns()

        # Capture module calls from profiler before
        calls_before = set(self.profiler.call_counts.keys())

        try:
            workload()
        except Exception:
            pass  # Don't let workload errors stop evolution

        elapsed = time.monotonic_ns() - start

        # Capture module calls from profiler after
        calls_after = set(self.profiler.call_counts.keys())
        new_calls = sorted(calls_after - calls_before)

        return ExecutionTrace(
            module_calls=new_calls,
            total_duration_ns=elapsed,
        )

    # ── Queries ─────────────────────────────────────────────────────────

    def get_improvement_history(self) -> list[tuple[int, float]]:
        """Return (generation, fitness_score) pairs."""
        return [(r.generation, r.fitness_after) for r in self._history]

    def get_best_mutations(self, n: int = 10) -> list[MutationRecord]:
        """Return the N most impactful successful mutations."""
        applied = self.mutator.get_applied_mutations()
        applied.sort(
            key=lambda r: r.result.fitness_delta,
            reverse=True,
        )
        return applied[:n]

    def get_history(self) -> list[EvolutionRecord]:
        """Get full evolution history."""
        return list(self._history)

    @property
    def current_fitness(self) -> float:
        """Current genome fitness score."""
        return self.genome.fitness_score

    def reset(self) -> None:
        """Reset the engine to initial state."""
        self.genome = Genome()
        self.generation = 0
        self._history.clear()
        self.miner.clear_traces()
        self.mutator.clear_history()
        self.profiler.reset()
        self.validator.clear_all()

    def __repr__(self) -> str:
        return (
            f"EvolutionEngine("
            f"gen={self.generation}, "
            f"fitness={self.genome.fitness_score:.4f}, "
            f"history={len(self._history)})"
        )
