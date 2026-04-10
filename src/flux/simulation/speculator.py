"""Speculative Execution Engine — executes multiple mutations in parallel (speculatively).

Instead of trying one mutation at a time, this engine:
1. Generates N hypotheses
2. Simulates all of them (fast, using cost model)
3. Runs the top K promising ones in parallel (real execution)
4. Keeps the best result
5. Rolls back all others

This is like a chess engine evaluating multiple moves ahead.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional, Any

from flux.evolution.genome import Genome, MutationStrategy
from flux.evolution.mutator import (
    MutationProposal,
    MutationResult,
)
from flux.flywheel.hypothesis import Hypothesis, ExperimentResult, ExperimentOutcome
from flux.adaptive.profiler import AdaptiveProfiler

from .digital_twin import DigitalTwin, SimulatedResult


# ── Data Types ──────────────────────────────────────────────────────────

@dataclass
class SpeculationResult:
    """Result of speculating on a set of hypotheses."""
    hypotheses_evaluated: int = 0
    simulations_run: int = 0
    real_executions_run: int = 0
    best_hypothesis: Optional[Hypothesis] = None
    best_simulated: Optional[SimulatedResult] = None
    best_result: Optional[ExperimentResult] = None
    total_speedup: float = 1.0
    confidence: float = 0.0
    elapsed_ms: float = 0.0
    hypotheses: list[Hypothesis] = field(default_factory=list)
    simulated_results: list[SimulatedResult] = field(default_factory=list)
    execution_results: list[ExperimentResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Did speculation produce an improvement?"""
        return (
            self.best_result is not None
            and self.best_result.outcome == ExperimentOutcome.SUCCESS
        )


# ── Speculative Engine ──────────────────────────────────────────────────

class SpeculativeEngine:
    """Executes multiple mutations in parallel (speculatively).

    Instead of trying one mutation at a time, this engine:
    1. Generates N hypotheses
    2. Simulates all of them (fast, using cost model)
    3. Runs the top K promising ones in parallel (real execution)
    4. Keeps the best result
    5. Rolls back all others

    This is like a chess engine evaluating multiple moves ahead.
    """

    def __init__(
        self,
        synthesizer: Any,
        twin: DigitalTwin,
        candidates: int = 10,
        parallel_limit: int = 3,
    ) -> None:
        self.synth = synthesizer
        self.twin = twin
        self._candidates: int = candidates       # simulate N candidates
        self._parallel_limit: int = parallel_limit  # execute top K in parallel
        self._total_speculations: int = 0
        self._total_improvements: int = 0

    @property
    def improvement_rate(self) -> float:
        """Rate of successful speculations."""
        if self._total_speculations == 0:
            return 0.0
        return self._total_improvements / self._total_speculations

    # ── Main Speculation ────────────────────────────────────────────────

    def speculate(self, hypotheses: list[Hypothesis]) -> SpeculationResult:
        """Speculate on multiple hypotheses, return the best.

        Workflow:
        1. Simulate all hypotheses using the digital twin
        2. Rank by estimated value (speedup × confidence / risk)
        3. Execute top K in parallel
        4. Keep the best result
        5. Roll back the rest

        Args:
            hypotheses: List of hypotheses to evaluate.

        Returns:
            SpeculationResult with the best outcome.
        """
        start = time.monotonic_ns()
        self._total_speculations += 1
        result = SpeculationResult(hypotheses=list(hypotheses))
        result.hypotheses_evaluated = len(hypotheses)

        if not hypotheses:
            result.elapsed_ms = (time.monotonic_ns() - start) / 1_000_000
            return result

        # Ensure shadow is current
        self.twin.capture_shadow()

        # Step 1: Simulate all hypotheses using the digital twin
        simulated: list[tuple[Hypothesis, SimulatedResult]] = []
        for hyp in hypotheses[:self._candidates]:
            proposal = self._hypothesis_to_proposal(hyp)
            sim_result = self.twin.simulate_mutation(proposal)
            simulated.append((hyp, sim_result))
            result.simulated_results.append(sim_result)

        result.simulations_run = len(simulated)

        # Step 2: Rank by estimated value (speedup × confidence × (1 - risk))
        def rank_score(item: tuple[Hypothesis, SimulatedResult]) -> float:
            hyp, sim = item
            return hyp.expected_speedup * hyp.confidence * (1.0 - hyp.risk_level)

        simulated.sort(key=rank_score, reverse=True)

        # Step 3: Execute top K in parallel (real genome mutation + fitness eval)
        top_k = simulated[:self._parallel_limit]

        if top_k:
            execution_results = self._execute_top_k(top_k)
            result.execution_results = execution_results
            result.real_executions_run = len(execution_results)

            # Step 4: Keep the best result
            best = self._select_best(execution_results)
            if best is not None:
                result.best_result = best
                result.best_hypothesis = best.hypothesis
                result.total_speedup = best.actual_speedup
                result.confidence = self._estimate_confidence(simulated, best)

                if best.was_improvement:
                    self._total_improvements += 1

        # Store the best simulated result too
        if simulated:
            best_sim = max(simulated, key=lambda x: x[1].estimated_fitness_delta)
            result.best_simulated = best_sim[1]

        result.elapsed_ms = (time.monotonic_ns() - start) / 1_000_000
        return result

    def batch_speculate(
        self, hypothesis_sets: list[list[Hypothesis]]
    ) -> list[SpeculationResult]:
        """Run speculation on multiple batches.

        Args:
            hypothesis_sets: List of hypothesis lists, one per batch.

        Returns:
            List of SpeculationResult, one per batch.
        """
        results: list[SpeculationResult] = []
        for hypotheses in hypothesis_sets:
            result = self.speculate(hypotheses)
            results.append(result)
        return results

    # ── Internal ────────────────────────────────────────────────────────

    def _hypothesis_to_proposal(self, hyp: Hypothesis) -> MutationProposal:
        """Convert a Hypothesis to a MutationProposal for the twin."""
        return MutationProposal(
            strategy=hyp.mutation_type,
            target=hyp.target_path,
            description=hyp.description,
            kwargs=dict(hyp.metadata),
            estimated_speedup=hyp.expected_speedup,
            estimated_risk=hyp.risk_level,
            priority=hyp.expected_value,
        )

    def _execute_top_k(
        self,
        top_k: list[tuple[Hypothesis, SimulatedResult]],
    ) -> list[ExperimentResult]:
        """Execute the top K hypotheses in parallel.

        Each execution creates a mutated genome copy, evaluates fitness,
        and validates correctness.
        """
        results: list[ExperimentResult] = []

        def execute_one(
            hyp: Hypothesis,
            sim: SimulatedResult,
        ) -> ExperimentResult:
            start = time.monotonic_ns()

            try:
                # Get the current genome
                genome = self.synth.evolution.genome
                fitness_before = genome.fitness_score

                # Mutate a copy
                mutated = genome.mutate(
                    strategy=hyp.mutation_type,
                    target=hyp.target_path,
                    **hyp.metadata,
                )
                mutated.evaluate_fitness()
                fitness_after = mutated.fitness_score

                elapsed = time.monotonic_ns() - start

                if fitness_after > fitness_before * 1.001:
                    outcome = ExperimentOutcome.SUCCESS
                    speedup = fitness_after / max(fitness_before, 0.001)
                else:
                    outcome = ExperimentOutcome.INCONCLUSIVE
                    speedup = fitness_after / max(fitness_before, 0.001)

                return ExperimentResult(
                    hypothesis=hyp,
                    outcome=outcome,
                    actual_speedup=speedup,
                    time_to_validate_ns=elapsed,
                    fitness_before=fitness_before,
                    fitness_after=fitness_after,
                    elapsed_ns=elapsed,
                )

            except Exception as exc:
                elapsed = time.monotonic_ns() - start
                return ExperimentResult(
                    hypothesis=hyp,
                    outcome=ExperimentOutcome.FAILURE,
                    time_to_validate_ns=elapsed,
                    details=f"Execution error: {exc}",
                    elapsed_ns=elapsed,
                )

        # Run in parallel
        max_workers = min(self._parallel_limit, len(top_k))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(execute_one, hyp, sim): (hyp, sim)
                for hyp, sim in top_k
            }
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as exc:
                    hyp, _ = futures[future]
                    results.append(ExperimentResult(
                        hypothesis=hyp,
                        outcome=ExperimentOutcome.FAILURE,
                        details=f"Thread error: {exc}",
                    ))

        return results

    def _select_best(
        self, results: list[ExperimentResult]
    ) -> Optional[ExperimentResult]:
        """Select the best result from the executed results.

        Priority: SUCCESS > INCONCLUSIVE > FAILURE
        Within same outcome: highest actual_speedup
        """
        if not results:
            return None

        # Prefer successful results
        successes = [r for r in results if r.outcome == ExperimentOutcome.SUCCESS]
        if successes:
            return max(successes, key=lambda r: r.actual_speedup)

        # Fall back to inconclusive
        inconclusive = [r for r in results if r.outcome == ExperimentOutcome.INCONCLUSIVE]
        if inconclusive:
            return max(inconclusive, key=lambda r: r.actual_speedup)

        # Return best failure (they're all bad)
        return results[0]

    def _estimate_confidence(
        self,
        simulated: list[tuple[Hypothesis, SimulatedResult]],
        best: ExperimentResult,
    ) -> float:
        """Estimate confidence in the best result.

        Based on agreement between simulation and real execution.
        """
        if not simulated or best is None:
            return 0.0

        # Find the simulated result for the best hypothesis
        matching_sim = None
        for hyp, sim in simulated:
            if hyp == best.hypothesis:
                matching_sim = sim
                break

        if matching_sim is None:
            return 0.3  # Low confidence without simulation

        # Agreement between simulated and actual
        sim_speedup = matching_sim.estimated_speedup
        actual_speedup = best.actual_speedup

        if sim_speedup < 1e-9:
            return 0.5

        ratio = min(actual_speedup, sim_speedup) / max(actual_speedup, sim_speedup)
        return max(0.0, min(1.0, ratio))

    def __repr__(self) -> str:
        return (
            f"SpeculativeEngine("
            f"candidates={self._candidates}, "
            f"parallel={self._parallel_limit}, "
            f"speculations={self._total_speculations}, "
            f"improvements={self._total_improvements}, "
            f"rate={self.improvement_rate:.2f})"
        )
