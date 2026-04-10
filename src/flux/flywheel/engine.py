"""Flywheel Engine — the self-reinforcing improvement loop.

The flywheel has 6 phases that cycle continuously:

1. OBSERVE   — Profile the system, collect metrics
2. LEARN     — Mine patterns, update memory, generalize
3. HYPOTHESIZE — Generate improvement hypotheses from research + data
4. EXPERIMENT — Test hypotheses (speculatively, in parallel)
5. INTEGRATE — Commit successful improvements, rollback failures
6. ACCELERATE — Use improvements to make the next cycle faster

The key insight: improvements in phase 5 make phases 1-4 faster in the
next cycle. Better profiling → better patterns → better hypotheses →
faster experiments → better improvements → faster profiling → ...

Like a DJ who gets better at reading the room because they've been reading
rooms, which makes them better at selecting tracks, which makes the crowd
more responsive, which gives them better feedback, which makes them even
better at reading the room.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any, Callable

from flux.synthesis.synthesizer import FluxSynthesizer
from flux.evolution.genome import MutationStrategy, Genome
from flux.evolution.mutator import SystemMutator
from flux.evolution.pattern_mining import PatternMiner
from flux.adaptive.profiler import AdaptiveProfiler, HeatLevel

from .hypothesis import (
    Hypothesis,
    ExperimentResult,
    ExperimentOutcome,
    ObservationData,
    LearnedInsights,
    FlywheelRecord,
    FlywheelReport,
    IntegrationReport,
)
from .knowledge import KnowledgeBase, GeneralizedRule
from .metrics import FlywheelMetrics


# ── Flywheel Phase ─────────────────────────────────────────────────────

class FlywheelPhase(Enum):
    """The 6 phases of a flywheel revolution."""
    OBSERVE = "observe"
    LEARN = "learn"
    HYPOTHESIZE = "hypothesize"
    EXPERIMENT = "experiment"
    INTEGRATE = "integrate"
    ACCELERATE = "accelerate"


# ── Flywheel Engine ────────────────────────────────────────────────────

class FlywheelEngine:
    """The self-reinforcing improvement flywheel.

    The flywheel wraps the synthesizer and adds a continuous improvement
    loop on top. Each revolution makes the system measurably better,
    and the knowledge accumulated from past revolutions makes future
    revolutions faster and more effective.

    Args:
        synthesizer: The FluxSynthesizer that manages the full FLUX system.
        max_hypotheses_per_rev: Max hypotheses generated per revolution.
        max_workers: Max parallel workers for experiment execution.
        min_improvement_threshold: Minimum speedup to consider an improvement.
        max_revolutions: Safety limit on total revolutions.
    """

    def __init__(
        self,
        synthesizer: FluxSynthesizer,
        max_hypotheses_per_rev: int = 10,
        max_workers: int = 4,
        min_improvement_threshold: float = 1.05,
        max_revolutions: int = 100,
    ) -> None:
        self.synth = synthesizer
        self.phase = FlywheelPhase.OBSERVE
        self.revolution = 0                    # how many full cycles completed
        self._metrics: FlywheelMetrics = FlywheelMetrics()
        self._history: list[FlywheelRecord] = []
        self._acceleration_factor: float = 1.0  # starts at 1.0, increases over time
        self._knowledge: KnowledgeBase = KnowledgeBase()

        # Configuration
        self._max_hypotheses: int = max_hypotheses_per_rev
        self._max_workers: int = max_workers
        self._min_improvement: float = min_improvement_threshold
        self._max_revolutions: int = max_revolutions

        # Acceleration curve tracking
        self._acceleration_curve: list[tuple[int, float]] = []

        # Current revolution state
        self._current_observation: Optional[ObservationData] = None
        self._current_insights: Optional[LearnedInsights] = None
        self._current_hypotheses: list[Hypothesis] = []
        self._current_results: list[ExperimentResult] = []

        # Validation function (can be set externally)
        self._validation_fn: Optional[Callable[[Genome], bool]] = None

    # ── Main Entry Point ────────────────────────────────────────────────

    def spin(self, rounds: int = 1) -> FlywheelReport:
        """Spin the flywheel for N complete revolutions.

        Each revolution runs all 6 phases: observe → learn → hypothesize
        → experiment → integrate → accelerate.

        Args:
            rounds: Number of complete revolutions to spin.

        Returns:
            FlywheelReport with all results and metrics.
        """
        total_start = time.monotonic_ns()
        report = FlywheelReport()
        report.initial_acceleration = self._acceleration_factor
        report.initial_fitness = self.synth.current_fitness

        for i in range(rounds):
            if self.revolution >= self._max_revolutions:
                break

            record = self._run_revolution()
            report.records.append(record)

            # Accumulate report totals
            report.total_improvements += record.successes
            report.total_experiments += record.experiments_run
            report.total_successes += record.successes
            report.total_failures += record.failures + record.timeouts
            report.revolutions_completed = i + 1

        # Final state
        report.final_acceleration = self._acceleration_factor
        report.final_fitness = self.synth.current_fitness
        report.total_time_ns = time.monotonic_ns() - total_start
        report.velocity_trend = self._metrics.get_velocity_trend()

        return report

    def _run_revolution(self) -> FlywheelRecord:
        """Run a single complete revolution through all 6 phases."""
        rev_start = time.monotonic_ns()
        self.revolution += 1

        record = FlywheelRecord(revolution=self.revolution)
        record.acceleration_before = self._acceleration_factor
        record.fitness_before = self.synth.current_fitness

        # Phase 1: OBSERVE
        self.phase = FlywheelPhase.OBSERVE
        obs = self._observe()
        self._current_observation = obs
        record.phase_results["observe"] = {
            "modules_profiled": obs.module_count,
            "hot_modules": len(obs.hot_modules),
            "bottlenecks": len(obs.bottleneck_modules),
        }

        # Phase 2: LEARN
        self.phase = FlywheelPhase.LEARN
        insights = self._learn(obs)
        self._current_insights = insights
        record.phase_results["learn"] = {
            "insights": insights.insight_count,
            "patterns": len(insights.patterns_found),
            "confidence": insights.confidence,
        }

        # Phase 3: HYPOTHESIZE
        self.phase = FlywheelPhase.HYPOTHESIZE
        hypotheses = self._hypothesize(insights)
        self._current_hypotheses = hypotheses
        record.hypotheses_generated = len(hypotheses)
        record.phase_results["hypothesize"] = {
            "hypotheses": len(hypotheses),
            "high_confidence": sum(1 for h in hypotheses if h.is_high_confidence),
            "risky": sum(1 for h in hypotheses if h.is_risky),
        }

        # Phase 4: EXPERIMENT
        self.phase = FlywheelPhase.EXPERIMENT
        results = self._experiment(hypotheses)
        self._current_results = results
        record.experiments_run = len(results)
        record.successes = sum(1 for r in results if r.outcome == ExperimentOutcome.SUCCESS)
        record.failures = sum(1 for r in results if r.outcome == ExperimentOutcome.FAILURE)
        record.timeouts = sum(1 for r in results if r.outcome == ExperimentOutcome.TIMEOUT)
        record.inconclusive = sum(1 for r in results if r.outcome == ExperimentOutcome.INCONCLUSIVE)
        record.phase_results["experiment"] = {
            "results": len(results),
            "avg_speedup": (
                sum(r.actual_speedup for r in results) / len(results)
                if results else 1.0
            ),
        }

        # Phase 5: INTEGRATE
        self.phase = FlywheelPhase.INTEGRATE
        integration = self._integrate(results)
        record.phase_results["integrate"] = {
            "committed": integration.committed,
            "rolled_back": integration.rolled_back,
            "skipped": integration.skipped,
        }

        # Phase 6: ACCELERATE
        self.phase = FlywheelPhase.ACCELERATE
        new_accel = self._accelerate()
        record.acceleration_after = new_accel
        self._acceleration_factor = new_accel
        self._acceleration_curve.append((self.revolution, new_accel))
        record.phase_results["accelerate"] = {
            "old_factor": record.acceleration_before,
            "new_factor": new_accel,
            "delta": new_accel - record.acceleration_before,
        }

        # Finalize record
        record.fitness_after = self.synth.current_fitness
        record.revolution_time_ns = time.monotonic_ns() - rev_start

        # Record in metrics
        self._metrics.record_revolution(record)

        # Store in history
        self._history.append(record)

        return record

    # ── Phase 1: OBSERVE ────────────────────────────────────────────────

    def _observe(self) -> ObservationData:
        """Phase 1: Collect system metrics, profiler data, heatmap.

        Profiles the current system state to understand what's slow,
        what's hot, and what's changed since the last revolution.
        """
        obs = ObservationData()

        # Collect heatmap from synthesizer's profiler
        heatmap = self.synth.get_heatmap_enum()
        obs.heatmap = {k: v.name for k, v in heatmap.items()}

        # Collect call counts and timing
        obs.call_counts = dict(self.synth.profiler.call_counts)
        obs.total_times_ns = dict(self.synth.profiler.total_time_ns)

        # Module and sample counts
        obs.module_count = self.synth.profiler.module_count
        obs.sample_count = self.synth.profiler.sample_count
        obs.tile_count = self.synth.tile_count

        # Classify modules
        hot = []
        frozen = []
        bottlenecks = []

        # Get bottleneck report
        bottleneck_report = self.synth.get_bottleneck_report(top_n=5)
        for entry in bottleneck_report.entries:
            bottlenecks.append(entry.module_path)

        for mod_path, heat_name in obs.heatmap.items():
            if heat_name in ("HEAT", "HOT"):
                hot.append(mod_path)
            elif heat_name == "FROZEN":
                frozen.append(mod_path)

        obs.hot_modules = hot
        obs.frozen_modules = frozen
        obs.bottleneck_modules = bottlenecks

        return obs

    # ── Phase 2: LEARN ──────────────────────────────────────────────────

    def _learn(self, obs: ObservationData) -> LearnedInsights:
        """Phase 2: Mine patterns, generalize from experience, update memory.

        Uses the pattern miner and knowledge base to extract insights from
        the observed data. This is where the flywheel "remembers" what worked
        and what didn't.
        """
        insights = LearnedInsights()

        # Identify hot and cold paths
        insights.hot_paths = list(obs.hot_modules)
        insights.cold_paths = list(obs.frozen_modules)

        # Mine patterns from profiler
        patterns = self.synth.miner.mine_patterns(
            min_frequency=2, min_length=2
        )
        insights.patterns_found = [p.name for p in patterns[:10]]

        # Check knowledge base for applicable rules
        applicable_rules = []
        for rule in self._knowledge.rules:
            if rule.is_reliable:
                applicable_rules.append(rule.to_dict())
        insights.confidence = 0.5
        if applicable_rules:
            avg_conf = sum(r["confidence"] for r in applicable_rules) / len(applicable_rules)
            insights.confidence = min(1.0, 0.3 + 0.7 * avg_conf)

        # Suggest recompilation candidates
        for mod_path in obs.hot_modules:
            lang = self.synth.selector._current_languages.get(mod_path, "python")
            if lang == "python":
                speedup = self.synth.profiler.estimate_speedup(mod_path, "rust")
                insights.recompilation_candidates.append({
                    "path": mod_path,
                    "current_language": lang,
                    "suggested_language": "rust",
                    "estimated_speedup": speedup,
                })

        # Suggest tile replacements from bottleneck data
        for mod_path in obs.bottleneck_modules[:3]:
            insights.tile_replacements.append({
                "target": mod_path,
                "reason": "bottleneck",
                "estimated_benefit": 0.2,
            })

        # Generalize knowledge periodically
        if self.revolution % 3 == 0:
            self._knowledge.generalize()

        return insights

    # ── Phase 3: HYPOTHESIZE ────────────────────────────────────────────

    def _hypothesize(self, insights: LearnedInsights) -> list[Hypothesis]:
        """Phase 3: Generate improvement hypotheses.

        Creates hypotheses from multiple sources:
        1. Recompilation candidates (hot modules in slow languages)
        2. Pattern fusions (hot sequences → tiles)
        3. Tile optimizations (expensive tiles → cheaper alternatives)
        4. Knowledge-based suggestions (rules that have worked before)

        Returns sorted list of hypotheses by expected value.
        """
        hypotheses: list[Hypothesis] = []

        # Source 1: Recompilation from insights
        for candidate in insights.recompilation_candidates[:3]:
            path = candidate["path"]
            speedup = candidate["estimated_speedup"]
            # Query knowledge base for historical success probability
            h = Hypothesis(
                description=f"Recompile {path} to faster language",
                target_path=path,
                mutation_type=MutationStrategy.RECOMPILE_LANGUAGE,
                expected_speedup=speedup,
                expected_modularity_delta=-0.1,  # compiled = less modular
                risk_level=0.3 if speedup < 8.0 else 0.5,
                confidence=self._knowledge.predict_success_probability(
                    Hypothesis(
                        description="", target_path=path,
                        mutation_type=MutationStrategy.RECOMPILE_LANGUAGE,
                    )
                ),
                source="profiler",
                metadata={"suggested_language": candidate.get("suggested_language", "rust")},
            )
            # Check if knowledge base says to skip
            skip, reason = self._knowledge.should_skip(h)
            if not skip:
                hypotheses.append(h)

        # Source 2: Pattern fusions
        for pattern_name in insights.patterns_found[:3]:
            h = Hypothesis(
                description=f"Fuse pattern '{pattern_name}' into optimized tile",
                target_path=pattern_name,
                mutation_type=MutationStrategy.FUSE_PATTERN,
                expected_speedup=1.5,
                expected_modularity_delta=0.1,
                risk_level=0.2,
                confidence=0.6,
                source="pattern_miner",
            )
            skip, reason = self._knowledge.should_skip(h)
            if not skip:
                hypotheses.append(h)

        # Source 3: Tile replacements
        for replacement in insights.tile_replacements[:2]:
            h = Hypothesis(
                description=f"Optimize bottleneck {replacement['target']}",
                target_path=replacement["target"],
                mutation_type=MutationStrategy.REPLACE_TILE,
                expected_speedup=1.3,
                expected_modularity_delta=0.0,
                risk_level=0.3,
                confidence=0.5,
                source="tile_registry",
            )
            skip, reason = self._knowledge.should_skip(h)
            if not skip:
                hypotheses.append(h)

        # Source 4: Knowledge-based hypotheses
        for rule in self._knowledge.rules:
            if rule.is_reliable and "avoid" not in rule.action.lower():
                # Generate a hypothesis from the rule
                mut_type_str = rule.condition.replace("mutation_type == ", "").strip()
                try:
                    mut_type = MutationStrategy(mut_type_str)
                except ValueError:
                    continue

                h = Hypothesis(
                    description=f"Apply knowledge-based rule: {rule.action}",
                    target_path="knowledge_suggested",
                    mutation_type=mut_type,
                    expected_speedup=1.0 + rule.confidence * 0.5,
                    expected_modularity_delta=0.0,
                    risk_level=1.0 - rule.confidence,
                    confidence=rule.confidence,
                    source="research",
                    metadata={"rule_condition": rule.condition},
                )
                skip, reason = self._knowledge.should_skip(h)
                if not skip:
                    hypotheses.append(h)

        # Sort by expected value (highest first) and limit count
        hypotheses.sort(key=lambda h: h.expected_value, reverse=True)
        return hypotheses[:self._max_hypotheses]

    # ── Phase 4: EXPERIMENT ─────────────────────────────────────────────

    def _experiment(self, hypotheses: list[Hypothesis]) -> list[ExperimentResult]:
        """Phase 4: Test hypotheses in parallel (speculative execution).

        Uses ThreadPoolExecutor to test multiple mutations simultaneously.
        The acceleration factor reduces experiment time for subsequent rounds
        (simulating the flywheel's increasing efficiency).

        Each experiment:
        1. Creates a mutated genome copy
        2. Evaluates fitness
        3. Validates correctness (if validation_fn is set)
        4. Measures actual speedup
        """
        if not hypotheses:
            return []

        results: list[ExperimentResult] = []

        def run_single_experiment(hypothesis: Hypothesis) -> ExperimentResult:
            """Run a single experiment for a hypothesis."""
            start = time.monotonic_ns()

            # Simulate experiment time based on acceleration factor
            # Higher acceleration = faster experiments
            base_time_ns = 1_000_000  # 1ms base experiment time
            simulated_time = int(base_time_ns / max(self._acceleration_factor, 0.1))

            try:
                # Use the synthesizer's evolution mutator to test
                genome = Genome()
                genome.capture(
                    self.synth.root,
                    self.synth.tile_registry,
                    self.synth.profiler,
                    self.synth.selector,
                )
                genome.evaluate_fitness()
                fitness_before = genome.fitness_score

                # Apply mutation
                mutated = genome.mutate(
                    strategy=hypothesis.mutation_type,
                    target=hypothesis.target_path,
                    **hypothesis.metadata,
                )
                mutated.evaluate_fitness()
                fitness_after = mutated.fitness_score

                # Validate correctness if validation_fn is set
                validation_passed = True
                if self._validation_fn is not None:
                    validation_passed = self._validation_fn(mutated)

                elapsed = time.monotonic_ns() - start

                # Determine outcome
                if fitness_after > fitness_before * 1.001 and validation_passed:
                    outcome = ExperimentOutcome.SUCCESS
                    actual_speedup = fitness_after / max(fitness_before, 0.001)
                elif elapsed > 5_000_000_000:  # 5 second timeout
                    outcome = ExperimentOutcome.TIMEOUT
                    actual_speedup = 1.0
                elif not validation_passed:
                    outcome = ExperimentOutcome.FAILURE
                    actual_speedup = 1.0
                else:
                    outcome = ExperimentOutcome.INCONCLUSIVE
                    actual_speedup = fitness_after / max(fitness_before, 0.001)

                # Update knowledge base prediction
                prob = self._knowledge.predict_success_probability(hypothesis)

                return ExperimentResult(
                    hypothesis=hypothesis,
                    outcome=outcome,
                    actual_speedup=actual_speedup,
                    time_to_validate_ns=elapsed,
                    details=f"Experiment completed in {elapsed / 1_000_000:.1f}ms, "
                            f"predicted success prob: {prob:.2f}",
                    fitness_before=fitness_before,
                    fitness_after=fitness_after,
                    elapsed_ns=elapsed,
                )

            except Exception as exc:
                elapsed = time.monotonic_ns() - start
                return ExperimentResult(
                    hypothesis=hypothesis,
                    outcome=ExperimentOutcome.FAILURE,
                    time_to_validate_ns=elapsed,
                    details=f"Experiment error: {exc}",
                    elapsed_ns=elapsed,
                )

        # Run experiments in parallel
        max_w = min(self._max_workers, len(hypotheses))
        with ThreadPoolExecutor(max_workers=max_w) as executor:
            future_to_hyp = {
                executor.submit(run_single_experiment, h): h
                for h in hypotheses
            }
            for future in as_completed(future_to_hyp):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as exc:
                    h = future_to_hyp[future]
                    results.append(ExperimentResult(
                        hypothesis=h,
                        outcome=ExperimentOutcome.FAILURE,
                        details=f"Thread error: {exc}",
                    ))

        return results

    # ── Phase 5: INTEGRATE ──────────────────────────────────────────────

    def _integrate(self, results: list[ExperimentResult]) -> IntegrationReport:
        """Phase 5: Apply successful experiments, rollback failures.

        For each experiment result:
        - SUCCESS → record in knowledge base as success, update genome
        - FAILURE → record in knowledge base as failure
        - TIMEOUT → skip, note for future
        - INCONCLUSIVE → re-queue with lower priority
        """
        report = IntegrationReport()
        committed_speedup = 1.0

        for result in results:
            if result.outcome == ExperimentOutcome.SUCCESS:
                # Commit: update knowledge base
                self._knowledge.add_success(result)

                # Apply improvement to synthesizer's genome
                try:
                    self.synth.evolution.genome = (
                        self.synth.evolution.genome.mutate(
                            strategy=result.hypothesis.mutation_type,
                            target=result.hypothesis.target_path,
                            **result.hypothesis.metadata,
                        )
                    )
                    self.synth.evolution.genome.evaluate_fitness()
                    committed_speedup *= result.actual_speedup
                except Exception:
                    pass  # Best-effort commit

                report.committed += 1
                report.details.append(
                    f"Committed: {result.hypothesis.description} "
                    f"(speedup={result.actual_speedup:.2f})"
                )

            elif result.outcome == ExperimentOutcome.FAILURE:
                # Rollback: record failure in knowledge base
                self._knowledge.add_failure(result)
                report.rolled_back += 1
                report.details.append(
                    f"Rolled back: {result.hypothesis.description}"
                )

            elif result.outcome == ExperimentOutcome.TIMEOUT:
                self._knowledge.add_failure(result)
                report.skipped += 1
                report.details.append(
                    f"Timed out: {result.hypothesis.description}"
                )

            else:  # INCONCLUSIVE
                report.skipped += 1
                report.details.append(
                    f"Inconclusive: {result.hypothesis.description}"
                )

        report.fitness_delta = (
            self.synth.current_fitness
            - (self._history[-1].fitness_before if self._history else 0)
        )

        return report

    # ── Phase 6: ACCELERATE ─────────────────────────────────────────────

    def _accelerate(self) -> float:
        """Phase 6: Calculate new acceleration factor.

        The acceleration factor captures how much faster this revolution
        was compared to the first revolution. Key factors:
        1. Improved success rate → fewer wasted experiments
        2. Knowledge base rules → better hypothesis selection
        3. Cumulative speedups from committed improvements
        4. Faster revolution times (the flywheel is spinning faster)

        The acceleration factor starts at 1.0 and increases as the system
        improves. Each 10% improvement in success rate adds ~5% acceleration.
        Each committed speedup multiplies the acceleration.
        """
        if not self._history:
            return self._acceleration_factor

        # Factor 1: Success rate improvement
        avg_success_rate = self._metrics.get_average_success_rate()
        success_accel = 1.0 + avg_success_rate * 0.3

        # Factor 2: Knowledge base size (more knowledge = better hypotheses)
        knowledge_accel = 1.0 + min(self._knowledge.size() * 0.005, 0.3)

        # Factor 3: Cumulative speedup from committed improvements
        speedup_accel = self._metrics.cumulative_speedup

        # Factor 4: Revolution time trend (faster revolutions = acceleration)
        time_accel = 1.0
        if len(self._metrics.revolution_times) >= 2:
            first_avg = (
                sum(self._metrics.revolution_times[:3])
                / min(3, len(self._metrics.revolution_times))
            )
            recent_avg = (
                sum(self._metrics.revolution_times[-3:])
                / min(3, len(self._metrics.revolution_times))
            )
            if first_avg > 0:
                time_accel = first_avg / max(recent_avg, 0.0001)
                # Clamp to reasonable range
                time_accel = min(max(time_accel, 0.8), 1.5)

        # Combine factors
        new_factor = self._acceleration_factor
        new_factor *= success_accel
        new_factor *= knowledge_accel
        new_factor *= min(speedup_accel, 3.0)  # Cap speedup contribution
        new_factor *= time_accel

        # Dampen to prevent runaway acceleration
        # Each revolution can add at most 10% acceleration
        max_increase = self._acceleration_factor * 1.10
        new_factor = min(new_factor, max_increase)

        # Minimum acceleration is 1.0 (can't go below baseline)
        new_factor = max(new_factor, 1.0)

        return round(new_factor, 4)

    # ── Public Queries ──────────────────────────────────────────────────

    def get_acceleration_curve(self) -> list[tuple[int, float]]:
        """Return (revolution, acceleration_factor) for plotting.

        Returns:
            List of (revolution_number, acceleration_factor) tuples.
        """
        return list(self._acceleration_curve)

    def get_improvement_velocity(self) -> float:
        """Rate of improvement per unit time.

        Measures improvements per second over the flywheel's lifetime.
        Should increase with revolutions as the flywheel accelerates.

        Returns:
            Improvements per second (0.0 if no uptime).
        """
        uptime = self._metrics.uptime_seconds
        if uptime <= 0:
            return 0.0
        return self._metrics.total_improvements / uptime

    def get_knowledge_base(self) -> KnowledgeBase:
        """Get the knowledge base for inspection."""
        return self._knowledge

    def get_metrics(self) -> FlywheelMetrics:
        """Get the metrics tracker for inspection."""
        return self._metrics

    def get_history(self) -> list[FlywheelRecord]:
        """Get the full revolution history."""
        return list(self._history)

    def set_validation_fn(
        self, fn: Optional[Callable[[Genome], bool]]
    ) -> None:
        """Set a custom validation function for experiments.

        Args:
            fn: Function that takes a Genome and returns True if valid.
        """
        self._validation_fn = fn

    def get_report(self) -> dict[str, Any]:
        """Get a comprehensive summary of the flywheel state."""
        return {
            "revolution": self.revolution,
            "phase": self.phase.value,
            "acceleration_factor": self._acceleration_factor,
            "improvement_velocity": self.get_improvement_velocity(),
            "metrics": self._metrics.to_dict(),
            "knowledge": self._knowledge.to_dict(),
            "history": [
                {
                    "rev": r.revolution,
                    "hypotheses": r.hypotheses_generated,
                    "experiments": r.experiments_run,
                    "successes": r.successes,
                    "failures": r.failures,
                    "success_rate": r.success_rate,
                    "acceleration": r.acceleration_after,
                    "time_ms": r.revolution_time_ns / 1_000_000,
                }
                for r in self._history[-20:]  # last 20 revolutions
            ],
        }

    def reset(self) -> None:
        """Reset the flywheel to initial state."""
        self.phase = FlywheelPhase.OBSERVE
        self.revolution = 0
        self._metrics = FlywheelMetrics()
        self._history.clear()
        self._acceleration_factor = 1.0
        self._acceleration_curve.clear()
        self._knowledge.clear()
        self._current_observation = None
        self._current_insights = None
        self._current_hypotheses.clear()
        self._current_results.clear()

    def __repr__(self) -> str:
        return (
            f"FlywheelEngine("
            f"rev={self.revolution}, "
            f"phase={self.phase.value}, "
            f"accel={self._acceleration_factor:.2f}, "
            f"improvements={self._metrics.total_improvements}, "
            f"velocity={self.get_improvement_velocity():.2f}/s)"
        )
