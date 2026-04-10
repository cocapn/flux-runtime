"""Digital Twin — a shadow copy of the FLUX system that runs ahead in simulation.

The digital twin mirrors the real system's genome, modules, and profiler state.
It can simulate evolution steps without touching the real system, measure
prediction accuracy, and provide what-if analysis capabilities.
"""

from __future__ import annotations

import copy
import random
import time
from dataclasses import dataclass, field
from typing import Optional, Any

from flux.cost.model import CostModel
from flux.evolution.genome import (
    Genome,
    GenomeDiff,
    MutationStrategy,
    ModuleSnapshot,
    TileSnapshot,
    OptimizationRecord,
    ProfilerSnapshot,
)
from flux.evolution.mutator import (
    MutationProposal,
    MutationResult,
    SystemMutator,
)
from flux.evolution.pattern_mining import DiscoveredPattern
from flux.adaptive.profiler import AdaptiveProfiler, HeatLevel


# ── Data Types ──────────────────────────────────────────────────────────

@dataclass
class PredictionRecord:
    """Record of a prediction and its actual outcome for accuracy tracking."""
    prediction_type: str          # e.g. "speedup", "fitness", "heat_level"
    target: str                   # module path or mutation target
    predicted_value: float        # what we predicted
    actual_value: float           # what actually happened
    confidence: float = 0.5
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    @property
    def error(self) -> float:
        """Absolute error of the prediction."""
        return abs(self.predicted_value - self.actual_value)

    @property
    def relative_error(self) -> float:
        """Relative error (0-1). Clamped to 1.0 if actual is zero."""
        if abs(self.actual_value) < 1e-9:
            return 1.0 if abs(self.predicted_value) > 1e-9 else 0.0
        return min(1.0, self.error / abs(self.actual_value))


@dataclass
class SimulatedResult:
    """Result of simulating a single mutation on the shadow genome."""
    proposal: MutationProposal
    estimated_speedup: float = 1.0
    estimated_modularity_delta: float = 0.0
    risk_assessment: float = 0.5        # 0.0 = safe, 1.0 = risky
    time_to_apply_estimate_ms: float = 0.0
    estimated_fitness_before: float = 0.0
    estimated_fitness_after: float = 0.0
    estimated_fitness_delta: float = 0.0
    survival_probability: float = 0.5    # chance the mutation won't break things

    @property
    def should_apply(self) -> bool:
        """Simple heuristic: apply if speedup > 1 and risk < 0.7."""
        return self.estimated_speedup > 1.05 and self.risk_assessment < 0.7


@dataclass
class SimulatedEvolutionReport:
    """Report from simulating N generations of evolution."""
    generations_simulated: int = 0
    initial_fitness: float = 0.0
    final_fitness: float = 0.0
    fitness_delta: float = 0.0
    mutations_simulated: int = 0
    mutations_accepted: int = 0
    mutations_rejected: int = 0
    per_generation_fitness: list[float] = field(default_factory=list)
    best_mutation: Optional[SimulatedResult] = None
    survival_rate: float = 1.0

    @property
    def improvement_rate(self) -> float:
        """Fraction of mutations that were accepted."""
        if self.mutations_simulated == 0:
            return 0.0
        return self.mutations_accepted / self.mutations_simulated


@dataclass
class WhatIfResult:
    """Result of a what-if analysis question."""
    question: str
    predicted_outcome: str
    estimated_speedup: float = 1.0
    estimated_risk: float = 0.5
    confidence: float = 0.5
    estimated_time_cost_ms: float = 0.0
    recommendation: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChaosFault:
    """Record of a single chaos fault injection."""
    fault_type: str             # "kill_module", "corrupt_tile", "disconnect_agents", "oom"
    target: str                 # module or tile that was hit
    severity: float             # 0.0-1.0
    system_survived: bool = True
    recovery_time_ms: float = 0.0
    details: str = ""


@dataclass
class ChaosReport:
    """Report from chaos testing on the shadow system."""
    total_faults: int = 0
    system_survived: int = 0
    system_failed: int = 0
    survival_rate: float = 1.0
    faults: list[ChaosFault] = field(default_factory=list)
    worst_fault: Optional[ChaosFault] = None
    avg_recovery_time_ms: float = 0.0
    resilience_score: float = 1.0  # 0.0 = fragile, 1.0 = bulletproof

    @property
    def failure_rate(self) -> float:
        """Fraction of faults that caused system failure."""
        if self.total_faults == 0:
            return 0.0
        return self.system_failed / self.total_faults


@dataclass
class TwinReport:
    """Comprehensive report of twin state and prediction quality."""
    shadow_module_count: int = 0
    shadow_tile_count: int = 0
    shadow_fitness: float = 0.0
    shadow_generation: int = 0
    prediction_accuracy: float = 0.0
    prediction_drift: float = 0.0
    total_predictions: int = 0
    accurate_predictions: int = 0
    recent_accuracy_trend: str = "stable"  # "improving", "stable", "degrading"
    chaos_survival_rate: float = 1.0
    last_chaos_report: Optional[ChaosReport] = None
    uptime_s: float = 0.0


# ── Language Speed Factors ──────────────────────────────────────────────

LANG_SPEED_FACTORS: dict[str, float] = {
    "python": 1.0,
    "typescript": 2.0,
    "csharp": 4.0,
    "c": 8.0,
    "c_simd": 16.0,
    "rust": 10.0,
}

LANG_COMPILE_TIMES_MS: dict[str, float] = {
    "python": 0.0,
    "typescript": 2000.0,
    "csharp": 8000.0,
    "c": 15000.0,
    "c_simd": 35000.0,
    "rust": 30000.0,
}

LANG_MODULARITY: dict[str, float] = {
    "python": 1.0,
    "typescript": 0.8,
    "csharp": 0.7,
    "rust": 0.8,
    "c": 0.5,
    "c_simd": 0.3,
}


# ── Digital Twin ────────────────────────────────────────────────────────

class DigitalTwin:
    """A shadow copy of the FLUX system that runs ahead in simulation.

    The digital twin:
    - Mirrors the real system's genome, modules, and profiler state
    - Can simulate evolution steps without touching the real system
    - Measures prediction accuracy (simulated vs actual)
    - Provides "what-if" analysis capabilities

    Uses the CostModel from flux.cost to estimate performance
    without actually executing code.
    """

    def __init__(self, synthesizer: Any) -> None:
        self.synth = synthesizer
        self.shadow_genome: Genome = Genome()
        self.cost_model = CostModel()
        self._prediction_log: list[PredictionRecord] = []
        self._drift_history: list[float] = []
        self._created_at: float = time.time()
        self._last_chaos_report: Optional[ChaosReport] = None

    # ── Shadow Capture ──────────────────────────────────────────────────

    def capture_shadow(self) -> None:
        """Take a snapshot of the real system as the shadow state.

        Copies the current genome from the synthesizer's evolution engine
        into the shadow genome for simulation.
        """
        try:
            real_genome = self.synth.evolution.genome
            self.shadow_genome = Genome.from_dict(real_genome.to_dict())
            self.shadow_genome.evaluate_fitness()
        except Exception:
            # If no genome yet, create a fresh one
            self.shadow_genome = Genome()

    # ── Mutation Simulation ─────────────────────────────────────────────

    def simulate_mutation(self, proposal: MutationProposal) -> SimulatedResult:
        """Simulate a mutation on the shadow genome without touching the real system.

        Returns estimated speedup, modularity delta, risk assessment,
        and time to apply estimate.

        Args:
            proposal: The mutation proposal to simulate.

        Returns:
            SimulatedResult with all estimated outcomes.
        """
        fitness_before = self.shadow_genome.fitness_score
        if fitness_before == 0.0:
            self.shadow_genome.evaluate_fitness()
            fitness_before = self.shadow_genome.fitness_score

        # Apply mutation to a copy
        try:
            mutated = self.shadow_genome.mutate(
                strategy=proposal.strategy,
                target=proposal.target,
                **proposal.kwargs,
            )
            mutated.evaluate_fitness()
            fitness_after = mutated.fitness_score
        except Exception:
            fitness_after = fitness_before

        # Estimate speedup from proposal and cost model
        estimated_speedup = self._estimate_speedup(proposal)

        # Estimate modularity delta
        modularity_delta = self._estimate_modularity_delta(proposal)

        # Risk assessment based on strategy and target
        risk = self._assess_risk(proposal)

        # Time to apply estimate (compile time + test time)
        time_cost = self._estimate_time_cost(proposal)

        # Survival probability (inverse of risk with some base confidence)
        survival = max(0.1, 1.0 - risk * 0.8)

        fitness_delta = fitness_after - fitness_before

        return SimulatedResult(
            proposal=proposal,
            estimated_speedup=estimated_speedup,
            estimated_modularity_delta=modularity_delta,
            risk_assessment=risk,
            time_to_apply_estimate_ms=time_cost,
            estimated_fitness_before=fitness_before,
            estimated_fitness_after=fitness_after,
            estimated_fitness_delta=fitness_delta,
            survival_probability=survival,
        )

    def simulate_evolution(self, generations: int = 5) -> SimulatedEvolutionReport:
        """Simulate N generations of evolution on the shadow system.

        Compare simulated results with what actually happened.

        Args:
            generations: Number of evolution generations to simulate.

        Returns:
            SimulatedEvolutionReport with per-generation fitness tracking.
        """
        initial_fitness = self.shadow_genome.fitness_score
        if initial_fitness == 0.0:
            self.shadow_genome.evaluate_fitness()
            initial_fitness = self.shadow_genome.fitness_score

        per_gen_fitness: list[float] = [initial_fitness]
        mutations_simulated = 0
        mutations_accepted = 0
        mutations_rejected = 0
        best_result: Optional[SimulatedResult] = None

        current_genome = Genome.from_dict(self.shadow_genome.to_dict())
        mutator = SystemMutator()

        for gen in range(generations):
            # Generate synthetic proposals
            proposals = self._generate_synthetic_proposals(current_genome)

            gen_best_fitness = current_genome.fitness_score
            gen_best_result: Optional[SimulatedResult] = None

            for proposal in proposals:
                mutations_simulated += 1

                # Save current genome state
                saved = Genome.from_dict(current_genome.to_dict())

                # Simulate mutation
                try:
                    mutated = current_genome.mutate(
                        strategy=proposal.strategy,
                        target=proposal.target,
                        **proposal.kwargs,
                    )
                    mutated.evaluate_fitness()
                except Exception:
                    mutations_rejected += 1
                    continue

                if mutated.fitness_score > current_genome.fitness_score * 0.99:
                    # Accept mutation
                    current_genome = mutated
                    mutations_accepted += 1

                    result = SimulatedResult(
                        proposal=proposal,
                        estimated_speedup=proposal.estimated_speedup,
                        estimated_fitness_before=saved.fitness_score,
                        estimated_fitness_after=mutated.fitness_score,
                        estimated_fitness_delta=mutated.fitness_score - saved.fitness_score,
                    )

                    if gen_best_result is None or result.estimated_fitness_delta > gen_best_result.estimated_fitness_delta:
                        gen_best_result = result

                    if best_result is None or result.estimated_fitness_delta > best_result.estimated_fitness_delta:
                        best_result = result
                else:
                    mutations_rejected += 1

            per_gen_fitness.append(current_genome.fitness_score)

        final_fitness = current_genome.fitness_score

        return SimulatedEvolutionReport(
            generations_simulated=generations,
            initial_fitness=initial_fitness,
            final_fitness=final_fitness,
            fitness_delta=final_fitness - initial_fitness,
            mutations_simulated=mutations_simulated,
            mutations_accepted=mutations_accepted,
            mutations_rejected=mutations_rejected,
            per_generation_fitness=per_gen_fitness,
            best_mutation=best_result,
            survival_rate=mutations_accepted / max(mutations_simulated, 1),
        )

    # ── Prediction Accuracy ─────────────────────────────────────────────

    def prediction_accuracy(self) -> float:
        """How accurate have our predictions been? (0-1)

        Returns the fraction of predictions with relative error < 0.2.
        """
        if not self._prediction_log:
            return 1.0  # No predictions = perfect accuracy (vacuously true)
        accurate = sum(1 for p in self._prediction_log if p.relative_error < 0.2)
        return accurate / len(self._prediction_log)

    def prediction_drift(self) -> float:
        """How much are our predictions drifting from reality?

        Returns the average relative error of the last 20 predictions.
        0.0 = no drift, 1.0 = completely wrong.
        """
        recent = self._prediction_log[-20:]
        if not recent:
            return 0.0
        return sum(p.relative_error for p in recent) / len(recent)

    def record_prediction(
        self,
        prediction_type: str,
        target: str,
        predicted: float,
        actual: float,
        confidence: float = 0.5,
    ) -> None:
        """Record a prediction and its actual outcome."""
        record = PredictionRecord(
            prediction_type=prediction_type,
            target=target,
            predicted_value=predicted,
            actual_value=actual,
            confidence=confidence,
        )
        self._prediction_log.append(record)

        # Track drift history
        self._drift_history.append(record.relative_error)

    # ── What-If Analysis ────────────────────────────────────────────────

    def what_if_recompile(self, module_path: str, target_lang: str) -> WhatIfResult:
        """Predict what happens if we recompile a module.

        Args:
            module_path: Path to the module.
            target_lang: Target language (e.g. "rust", "c").

        Returns:
            WhatIfResult with speedup, risk, and recommendation.
        """
        current_lang = self.shadow_genome.language_assignments.get(module_path, "python")

        speedup = LANG_SPEED_FACTORS.get(target_lang, 1.0) / LANG_SPEED_FACTORS.get(current_lang, 1.0)
        compile_time = LANG_COMPILE_TIMES_MS.get(target_lang, 30000.0)
        modularity_change = LANG_MODULARITY.get(target_lang, 0.5) - LANG_MODULARITY.get(current_lang, 1.0)

        # Risk depends on how big the change is
        risk = 0.1 + 0.1 * min(speedup, 10.0) / 10.0
        if target_lang in ("c_simd", "rust"):
            risk += 0.1  # harder languages

        # Confidence based on how many similar predictions we've made
        similar = [p for p in self._prediction_log
                   if p.prediction_type == "recompile" and p.target == target_lang]
        if similar:
            confidence = sum(1 - p.relative_error for p in similar) / len(similar)
        else:
            confidence = 0.6

        # Recommendation
        if speedup > 2.0 and risk < 0.4:
            recommendation = "RECOMMENDED: High speedup, low risk"
        elif speedup > 1.5:
            recommendation = "CONSIDER: Moderate speedup, check risk tolerance"
        else:
            recommendation = "SKIP: Minimal speedup not worth compilation cost"

        # Check heat level
        module_snap = self.shadow_genome.modules.get(module_path)
        heat = module_snap.heat_level if module_snap else "FROZEN"

        return WhatIfResult(
            question=f"Recompile {module_path} from {current_lang} to {target_lang}?",
            predicted_outcome=f"{speedup:.1f}x speedup",
            estimated_speedup=speedup,
            estimated_risk=risk,
            confidence=confidence,
            estimated_time_cost_ms=compile_time,
            recommendation=recommendation,
            details={
                "current_language": current_lang,
                "target_language": target_lang,
                "modularity_delta": modularity_change,
                "module_heat": heat,
            },
        )

    def what_if_replace_tile(self, old_tile: str, new_tile: str) -> WhatIfResult:
        """Predict what happens if we swap a tile.

        Args:
            old_tile: Name of the current tile.
            new_tile: Name of the replacement tile.

        Returns:
            WhatIfResult with speedup, risk, and recommendation.
        """
        old_snap = self.shadow_genome.tiles.get(old_tile)
        new_snap = self.shadow_genome.tiles.get(new_tile)

        old_cost = old_snap.cost_estimate if old_snap else 1.0
        new_cost = new_snap.cost_estimate if new_snap else 0.5

        speedup = old_cost / max(new_cost, 0.01)
        speedup = min(speedup, 10.0)  # cap at 10x

        # Risk of tile replacement
        risk = 0.2
        if new_snap is None:
            risk = 0.5  # unknown tile

        # Same-type replacement is lower risk
        if old_snap and new_snap and old_snap.tile_type != new_snap.tile_type:
            risk += 0.2  # different type = higher risk

        confidence = 0.5 if new_snap is None else 0.7

        if speedup > 1.5 and risk < 0.4:
            recommendation = "RECOMMENDED: Significant improvement"
        elif speedup > 1.2:
            recommendation = "CONSIDER: Moderate improvement"
        else:
            recommendation = "SKIP: Not worth the risk"

        return WhatIfResult(
            question=f"Replace tile '{old_tile}' with '{new_tile}'?",
            predicted_outcome=f"{speedup:.1f}x cost reduction",
            estimated_speedup=speedup,
            estimated_risk=risk,
            confidence=confidence,
            estimated_time_cost_ms=1000.0,  # tile swap is fast
            recommendation=recommendation,
            details={
                "old_tile_cost": old_cost,
                "new_tile_cost": new_cost,
                "old_tile_type": old_snap.tile_type if old_snap else "unknown",
                "new_tile_type": new_snap.tile_type if new_snap else "unknown",
            },
        )

    # ── Chaos Testing ───────────────────────────────────────────────────

    def chaos_test(self, n_faults: int = 10) -> ChaosReport:
        """Inject random faults into the shadow system and see if it survives.

        Fault types:
        - Kill a random module
        - Corrupt a random tile
        - Disconnect agents in the swarm
        - OOM the memory system

        Args:
            n_faults: Number of faults to inject.

        Returns:
            ChaosReport with survival statistics.
        """
        faults: list[ChaosFault] = []
        survived = 0
        failed = 0

        module_paths = list(self.shadow_genome.modules.keys())
        tile_names = list(self.shadow_genome.tiles.keys())

        # If no modules or tiles, add some for testing
        if not module_paths:
            module_paths = ["mod_a", "mod_b", "mod_c"]
            for mp in module_paths:
                self.shadow_genome.modules[mp] = ModuleSnapshot(
                    path=mp, granularity="CARD", language="python",
                    version=1, checksum="abc",
                )

        if not tile_names:
            tile_names = ["tile_x", "tile_y"]
            for tn in tile_names:
                self.shadow_genome.tiles[tn] = TileSnapshot(
                    name=tn, tile_type="compute",
                    input_count=1, output_count=1,
                    cost_estimate=1.0, abstraction_level=5,
                    language_preference="fir",
                )

        fault_types = ["kill_module", "corrupt_tile", "disconnect_agents", "oom"]

        for i in range(n_faults):
            fault_type = random.choice(fault_types)
            severity = random.uniform(0.3, 1.0)

            # Simulate fault and check if system survives
            system_survived = self._simulate_fault(
                fault_type, severity, module_paths, tile_names
            )

            recovery_time = 0.0 if system_survived else severity * 500.0

            fault = ChaosFault(
                fault_type=fault_type,
                target=module_paths[0] if fault_type == "kill_module" else (
                    tile_names[0] if fault_type == "corrupt_tile" else "system"
                ),
                severity=severity,
                system_survived=system_survived,
                recovery_time_ms=recovery_time,
            )

            faults.append(fault)

            if system_survived:
                survived += 1
            else:
                failed += 1

        survival_rate = survived / max(n_faults, 1)
        avg_recovery = sum(f.recovery_time_ms for f in faults) / max(len(faults), 1)
        worst = max(faults, key=lambda f: f.severity if not f.system_survived else 0) if faults else None

        # Resilience score combines survival rate with recovery speed
        resilience = survival_rate * max(0.0, 1.0 - avg_recovery / 1000.0)

        report = ChaosReport(
            total_faults=n_faults,
            system_survived=survived,
            system_failed=failed,
            survival_rate=survival_rate,
            faults=faults,
            worst_fault=worst,
            avg_recovery_time_ms=avg_recovery,
            resilience_score=resilience,
        )

        self._last_chaos_report = report
        return report

    def _simulate_fault(
        self,
        fault_type: str,
        severity: float,
        module_paths: list[str],
        tile_names: list[str],
    ) -> bool:
        """Simulate a single fault and return whether the system survives.

        The system is resilient if:
        - It has redundancy (multiple modules/tiles)
        - The fault severity is below the resilience threshold
        - The system has enough history (well-tested)
        """
        total_components = len(module_paths) + len(tile_names)
        redundancy = max(total_components, 1)

        if fault_type == "kill_module":
            # System survives if it has more than 1 module and severity < 0.8
            return len(module_paths) > 1 and severity < 0.8
        elif fault_type == "corrupt_tile":
            # System survives if it has more than 1 tile and severity < 0.7
            return len(tile_names) > 1 and severity < 0.7
        elif fault_type == "disconnect_agents":
            # System survives if it has enough modules (agent redundancy)
            return redundancy >= 3 or severity < 0.5
        elif fault_type == "oom":
            # System survives if severity is low (partial OOM is recoverable)
            return severity < 0.6
        else:
            return True  # Unknown fault type — assume survival

    # ── Report ──────────────────────────────────────────────────────────

    def get_twin_report(self) -> TwinReport:
        """Comprehensive report of twin state and prediction quality."""
        accuracy = self.prediction_accuracy()
        drift = self.prediction_drift()
        total_preds = len(self._prediction_log)
        accurate_preds = sum(1 for p in self._prediction_log if p.relative_error < 0.2)

        # Determine accuracy trend
        if len(self._drift_history) >= 10:
            recent_drift = sum(self._drift_history[-5:]) / 5
            older_drift = sum(self._drift_history[-10:-5]) / 5 if len(self._drift_history) >= 10 else recent_drift
            if recent_drift < older_drift * 0.8:
                trend = "improving"
            elif recent_drift > older_drift * 1.2:
                trend = "degrading"
            else:
                trend = "stable"
        else:
            trend = "stable"

        chaos_rate = self._last_chaos_report.survival_rate if self._last_chaos_report else 1.0

        return TwinReport(
            shadow_module_count=len(self.shadow_genome.modules),
            shadow_tile_count=len(self.shadow_genome.tiles),
            shadow_fitness=self.shadow_genome.fitness_score,
            shadow_generation=self.shadow_genome.generation,
            prediction_accuracy=accuracy,
            prediction_drift=drift,
            total_predictions=total_preds,
            accurate_predictions=accurate_preds,
            recent_accuracy_trend=trend,
            chaos_survival_rate=chaos_rate,
            last_chaos_report=self._last_chaos_report,
            uptime_s=time.time() - self._created_at,
        )

    # ── Internal Helpers ────────────────────────────────────────────────

    def _estimate_speedup(self, proposal: MutationProposal) -> float:
        """Estimate speedup from a mutation proposal."""
        if proposal.strategy == MutationStrategy.RECOMPILE_LANGUAGE:
            new_lang = proposal.kwargs.get("new_language", "rust")
            current_lang = self.shadow_genome.language_assignments.get(
                proposal.target, "python"
            )
            return LANG_SPEED_FACTORS.get(new_lang, 1.0) / max(
                LANG_SPEED_FACTORS.get(current_lang, 1.0), 0.01
            )
        elif proposal.strategy == MutationStrategy.REPLACE_TILE:
            old_cost = proposal.kwargs.get("old_cost", 2.0)
            new_cost = proposal.kwargs.get("new_cost", 1.0)
            return old_cost / max(new_cost, 0.01)
        elif proposal.strategy == MutationStrategy.FUSE_PATTERN:
            return proposal.estimated_speedup
        elif proposal.strategy == MutationStrategy.MERGE_TILES:
            return 1.3  # typical merge speedup
        elif proposal.strategy == MutationStrategy.INLINE_OPTIMIZATION:
            return proposal.kwargs.get("speedup", 1.2)
        else:
            return proposal.estimated_speedup

    def _estimate_modularity_delta(self, proposal: MutationProposal) -> float:
        """Estimate change in modularity from a mutation."""
        if proposal.strategy == MutationStrategy.RECOMPILE_LANGUAGE:
            new_lang = proposal.kwargs.get("new_language", "rust")
            current_lang = self.shadow_genome.language_assignments.get(
                proposal.target, "python"
            )
            return LANG_MODULARITY.get(new_lang, 0.5) - LANG_MODULARITY.get(
                current_lang, 1.0
            )
        elif proposal.strategy == MutationStrategy.FUSE_PATTERN:
            return -0.1  # fusion slightly reduces modularity
        elif proposal.strategy == MutationStrategy.ADD_TILE:
            return 0.1  # more tiles = more modular
        elif proposal.strategy == MutationStrategy.MERGE_TILES:
            return -0.05  # slight modularity reduction
        else:
            return 0.0

    def _assess_risk(self, proposal: MutationProposal) -> float:
        """Assess risk of a mutation."""
        base_risk = proposal.estimated_risk

        # Adjust based on strategy
        strategy_risk = {
            MutationStrategy.RECOMPILE_LANGUAGE: 0.2,
            MutationStrategy.FUSE_PATTERN: 0.3,
            MutationStrategy.REPLACE_TILE: 0.2,
            MutationStrategy.ADD_TILE: 0.1,
            MutationStrategy.MERGE_TILES: 0.4,
            MutationStrategy.SPLIT_TILE: 0.2,
            MutationStrategy.INLINE_OPTIMIZATION: 0.15,
        }
        base_risk += strategy_risk.get(proposal.strategy, 0.2)

        # Higher speedup claims = higher risk
        if proposal.estimated_speedup > 5.0:
            base_risk += 0.1
        if proposal.estimated_speedup > 10.0:
            base_risk += 0.1

        return min(1.0, max(0.0, base_risk))

    def _estimate_time_cost(self, proposal: MutationProposal) -> float:
        """Estimate time cost of applying a mutation (in milliseconds)."""
        if proposal.strategy == MutationStrategy.RECOMPILE_LANGUAGE:
            new_lang = proposal.kwargs.get("new_language", "rust")
            return LANG_COMPILE_TIMES_MS.get(new_lang, 30000.0)
        elif proposal.strategy in (MutationStrategy.FUSE_PATTERN, MutationStrategy.MERGE_TILES):
            return 5000.0  # moderate cost
        elif proposal.strategy == MutationStrategy.INLINE_OPTIMIZATION:
            return 1000.0  # relatively cheap
        else:
            return 2000.0  # default

    def _generate_synthetic_proposals(self, genome: Genome) -> list[MutationProposal]:
        """Generate synthetic proposals for simulated evolution."""
        proposals: list[MutationProposal] = []

        # Propose recompilations for hot modules
        for path, snap in genome.modules.items():
            if snap.heat_level in ("HOT", "HEAT"):
                proposals.append(MutationProposal(
                    strategy=MutationStrategy.RECOMPILE_LANGUAGE,
                    target=path,
                    description=f"Recompile {path} to Rust",
                    kwargs={"new_language": "rust"},
                    estimated_speedup=10.0,
                    estimated_risk=0.3,
                    priority=8.0,
                ))

        # Propose tile optimizations
        for name, snap in genome.tiles.items():
            if snap.cost_estimate > 1.5:
                proposals.append(MutationProposal(
                    strategy=MutationStrategy.REPLACE_TILE,
                    target=name,
                    description=f"Optimize tile {name}",
                    kwargs={"new_cost": snap.cost_estimate * 0.5},
                    estimated_speedup=2.0,
                    estimated_risk=0.3,
                    priority=3.0,
                ))

        # Add an inline optimization if we have modules
        if genome.modules:
            target = list(genome.modules.keys())[0]
            proposals.append(MutationProposal(
                strategy=MutationStrategy.INLINE_OPTIMIZATION,
                target=target,
                description=f"Inline optimize {target}",
                kwargs={"speedup": 1.2},
                estimated_speedup=1.2,
                estimated_risk=0.1,
                priority=1.0,
            ))

        return proposals

    def __repr__(self) -> str:
        return (
            f"DigitalTwin("
            f"modules={len(self.shadow_genome.modules)}, "
            f"tiles={len(self.shadow_genome.tiles)}, "
            f"fitness={self.shadow_genome.fitness_score:.3f}, "
            f"predictions={len(self._prediction_log)}, "
            f"accuracy={self.prediction_accuracy():.2f})"
        )
