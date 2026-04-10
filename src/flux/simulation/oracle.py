"""Decision Oracle — combines predictions, twin simulations, and historical data
to make optimal evolution decisions.

The oracle answers questions like:
- "Should I recompile module X to Rust?" (YES, with 87% confidence)
- "What's the next best mutation?" (FUSE pattern Y for 15% speedup)
- "Is it worth spending time on optimization Z?" (ROI: 4.2x payback)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Any

from flux.evolution.genome import Genome, MutationStrategy
from flux.evolution.mutator import MutationProposal, SystemMutator
from flux.evolution.pattern_mining import DiscoveredPattern
from flux.flywheel.hypothesis import Hypothesis
from flux.flywheel.knowledge import KnowledgeBase
from flux.adaptive.profiler import AdaptiveProfiler, HeatLevel

from .predictor import PerformancePredictor
from .digital_twin import DigitalTwin, SimulatedResult


# ── Data Types ──────────────────────────────────────────────────────────

@dataclass
class OracleDecision:
    """Decision from the oracle with confidence and reasoning."""
    proposal: MutationProposal
    should_apply: bool
    confidence: float             # 0.0-1.0
    reasoning: str = ""
    estimated_speedup: float = 1.0
    estimated_risk: float = 0.5
    expected_value: float = 0.0   # speedup × confidence × (1 - risk)
    priority: float = 0.0

    @property
    def is_high_confidence(self) -> bool:
        return self.confidence >= 0.7

    @property
    def is_recommended(self) -> bool:
        return self.should_apply and self.confidence >= 0.5


@dataclass
class ROIEstimate:
    """Return on investment estimate for a mutation.

    ROI = (speedup × frequency × time_saved) / (compile_time + test_time)
    """
    proposal: MutationProposal
    estimated_speedup: float = 1.0
    call_frequency: float = 0.0       # calls per second
    current_avg_time_ns: float = 0.0
    time_saved_per_call_ns: float = 0.0
    total_time_saved_per_s_ns: float = 0.0
    compile_time_s: float = 0.0
    test_time_s: float = 0.0
    downtime_s: float = 0.0
    total_cost_s: float = 0.0
    payback_time_s: float = float('inf')
    roi_ratio: float = 0.0            # benefit / cost
    is_worth_it: bool = False
    recommendation: str = ""


@dataclass
class OracleRecommendation:
    """The oracle's recommendation for the next best action."""
    action: str                       # e.g. "recompile:module_path", "fuse:pattern", "wait"
    target: str                       # module path or pattern name
    estimated_speedup: float = 1.0
    confidence: float = 0.5
    risk: float = 0.5
    reasoning: str = ""
    alternative_actions: list[str] = field(default_factory=list)
    time_to_implement_ms: float = 0.0
    roi_estimate: Optional[ROIEstimate] = None


# ── Language Cost Data ──────────────────────────────────────────────────

COMPILE_TIMES_S: dict[str, float] = {
    "python": 0.0,
    "typescript": 2.0,
    "csharp": 8.0,
    "c": 15.0,
    "c_simd": 35.0,
    "rust": 30.0,
}


# ── Decision Oracle ─────────────────────────────────────────────────────

class DecisionOracle:
    """Combines predictions, twin simulations, and historical data
    to make optimal evolution decisions.

    The oracle answers questions like:
    - "Should I recompile module X to Rust?" (YES, with 87% confidence)
    - "What's the next best mutation?" (FUSE pattern Y for 15% speedup)
    - "Is it worth spending time on optimization Z?" (ROI: 4.2x payback)
    """

    def __init__(
        self,
        predictor: PerformancePredictor,
        twin: DigitalTwin,
        knowledge: KnowledgeBase,
        mutator: Optional[SystemMutator] = None,
    ) -> None:
        self.predictor = predictor
        self.twin = twin
        self.knowledge = knowledge
        self.mutator = mutator or SystemMutator()
        self._decisions_made: int = 0
        self._decisions_accepted: int = 0

    # ── Decision Making ─────────────────────────────────────────────────

    def should_mutate(self, proposal: MutationProposal) -> OracleDecision:
        """Should we apply this mutation? With what confidence?

        Combines multiple signals:
        1. Twin simulation result
        2. Historical success rate from knowledge base
        3. Risk assessment
        4. Expected value calculation

        Args:
            proposal: The mutation proposal to evaluate.

        Returns:
            OracleDecision with recommendation and confidence.
        """
        # Step 1: Simulate on the twin
        sim_result = self.twin.simulate_mutation(proposal)

        # Step 2: Check knowledge base for historical data
        stats = self.knowledge.get_mutation_stats(proposal.strategy.value)
        historical_success_rate = 0.5
        if stats["attempts"] > 0:
            historical_success_rate = stats["successes"] / stats["attempts"]

        # Step 3: Calculate confidence
        # Blend simulation confidence with historical confidence
        sim_confidence = sim_result.survival_probability
        knowledge_confidence = historical_success_rate

        if stats["attempts"] >= 5:
            # Trust knowledge more when we have more data
            confidence = 0.3 * sim_confidence + 0.7 * knowledge_confidence
        else:
            # Trust simulation more when data is sparse
            confidence = 0.7 * sim_confidence + 0.3 * knowledge_confidence

        # Step 4: Calculate expected value
        speedup = sim_result.estimated_speedup
        risk = sim_result.risk_assessment
        expected_value = speedup * confidence * (1.0 - risk)

        # Step 5: Should we apply?
        should_apply = (
            confidence >= 0.4
            and expected_value > 0.3
            and sim_result.estimated_speedup > 1.02
        )

        # Step 6: Build reasoning
        reasons: list[str] = []
        if speedup > 1.5:
            reasons.append(f"High speedup ({speedup:.1f}x)")
        elif speedup > 1.1:
            reasons.append(f"Moderate speedup ({speedup:.1f}x)")
        else:
            reasons.append(f"Low speedup ({speedup:.2f}x)")

        if confidence > 0.7:
            reasons.append("High confidence")
        elif confidence < 0.4:
            reasons.append("Low confidence")

        if risk > 0.6:
            reasons.append("High risk")
        elif risk < 0.3:
            reasons.append("Low risk")

        reasoning = "; ".join(reasons)

        self._decisions_made += 1
        if should_apply:
            self._decisions_accepted += 1

        return OracleDecision(
            proposal=proposal,
            should_apply=should_apply,
            confidence=confidence,
            reasoning=reasoning,
            estimated_speedup=speedup,
            estimated_risk=risk,
            expected_value=expected_value,
            priority=expected_value,
        )

    def rank_proposals(
        self, proposals: list[MutationProposal]
    ) -> list[tuple[MutationProposal, float]]:
        """Rank proposals by expected value.

        Args:
            proposals: List of mutation proposals to rank.

        Returns:
            List of (proposal, score) sorted by score descending.
        """
        scored: list[tuple[MutationProposal, float]] = []

        for proposal in proposals:
            decision = self.should_mutate(proposal)
            score = decision.expected_value
            scored.append((proposal, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def roi_estimate(self, proposal: MutationProposal) -> ROIEstimate:
        """Estimate return on investment for a mutation.

        ROI = (speedup × frequency × time_saved) / (compile_time + test_time)

        Args:
            proposal: The mutation proposal to evaluate.

        Returns:
            ROIEstimate with detailed cost-benefit analysis.
        """
        # Estimate speedup from simulation
        sim_result = self.twin.simulate_mutation(proposal)
        speedup = sim_result.estimated_speedup

        # Get call frequency from profiler store
        call_freq_key = f"calls:{proposal.target}"
        total_calls = self.predictor.store.get(call_freq_key, 0)

        # Estimate calls per second (assume 1 second observation window)
        calls_per_sec = max(total_calls, 0.1)

        # Current average execution time
        current_avg = self.predictor.predict_execution_time(proposal.target)

        # Time saved per call
        if speedup > 0:
            time_saved_per_call = current_avg * (1.0 - 1.0 / speedup)
        else:
            time_saved_per_call = 0.0

        # Total time saved per second (ns)
        total_saved_per_s = time_saved_per_call * calls_per_sec

        # Cost of the mutation
        compile_time = COMPILE_TIMES_S.get(
            proposal.kwargs.get("new_language", ""), 5.0
        )
        if proposal.strategy != MutationStrategy.RECOMPILE_LANGUAGE:
            compile_time = sim_result.time_to_apply_estimate_ms / 1000.0

        test_time = 5.0   # standard test time
        downtime = 0.1    # hot-swap downtime
        total_cost = compile_time + test_time + downtime

        # Payback time: how long until savings cover cost
        if total_saved_per_s > 0:
            saved_per_s = total_saved_per_s / 1e9  # convert ns to seconds
            payback = total_cost / saved_per_s if saved_per_s > 0 else float('inf')
        else:
            payback = float('inf')

        # ROI ratio: total benefit / total cost
        if total_cost > 0 and payback < float('inf'):
            # Benefit over a 1-hour window
            one_hour_savings = (total_saved_per_s / 1e9) * 3600
            roi_ratio = one_hour_savings / total_cost
        else:
            roi_ratio = 0.0

        # Is it worth it?
        is_worth_it = (
            speedup > 1.05
            and payback < 3600.0  # payback within 1 hour
            and roi_ratio > 1.0
        )

        if is_worth_it:
            recommendation = (
                f"Worth it: {speedup:.1f}x speedup, "
                f"payback in {payback:.0f}s, ROI={roi_ratio:.1f}x"
            )
        elif payback < 3600:
            recommendation = (
                f"Marginal: {speedup:.1f}x speedup, "
                f"payback in {payback:.0f}s"
            )
        else:
            recommendation = (
                f"Not worth it: payback > 1 hour "
                f"({payback:.0f}s) for {speedup:.1f}x speedup"
            )

        return ROIEstimate(
            proposal=proposal,
            estimated_speedup=speedup,
            call_frequency=calls_per_sec,
            current_avg_time_ns=current_avg,
            time_saved_per_call_ns=time_saved_per_call,
            total_time_saved_per_s_ns=total_saved_per_s,
            compile_time_s=compile_time,
            test_time_s=test_time,
            downtime_s=downtime,
            total_cost_s=total_cost,
            payback_time_s=payback,
            roi_ratio=roi_ratio,
            is_worth_it=is_worth_it,
            recommendation=recommendation,
        )

    def next_best_action(self) -> OracleRecommendation:
        """What should the system do next?

        Analyzes the current system state and recommends the best
        next action, considering:
        - Current heatmap and bottlenecks
        - Available mutation opportunities
        - Historical success rates
        - ROI of potential actions

        Returns:
            OracleRecommendation with the best next action.
        """
        self.twin.capture_shadow()
        genome = self.twin.shadow_genome

        # Analyze modules
        best_action = ""
        best_target = ""
        best_speedup = 1.0
        best_confidence = 0.0
        best_risk = 0.5
        best_reasoning = ""
        best_roi: Optional[ROIEstimate] = None

        for mod_path, snap in genome.modules.items():
            heat = snap.heat_level
            current_lang = genome.language_assignments.get(mod_path, snap.language)

            if heat == "FROZEN":
                continue

            if heat in ("HEAT", "HOT") and current_lang == "python":
                # Strong candidate for recompilation
                proposal = MutationProposal(
                    strategy=MutationStrategy.RECOMPILE_LANGUAGE,
                    target=mod_path,
                    description=f"Recompile {mod_path} to Rust",
                    kwargs={"new_language": "rust"},
                    estimated_speedup=10.0,
                    estimated_risk=0.3,
                    priority=8.0,
                )
                decision = self.should_mutate(proposal)
                roi = self.roi_estimate(proposal)

                if decision.expected_value > best_speedup * best_confidence:
                    best_action = f"recompile:{mod_path}"
                    best_target = mod_path
                    best_speedup = decision.estimated_speedup
                    best_confidence = decision.confidence
                    best_risk = decision.estimated_risk
                    best_reasoning = decision.reasoning
                    best_roi = roi

            elif heat == "WARM" and current_lang == "python":
                proposal = MutationProposal(
                    strategy=MutationStrategy.RECOMPILE_LANGUAGE,
                    target=mod_path,
                    description=f"Recompile {mod_path} to TypeScript",
                    kwargs={"new_language": "typescript"},
                    estimated_speedup=2.0,
                    estimated_risk=0.1,
                    priority=3.0,
                )
                decision = self.should_mutate(proposal)

                if best_action == "" and decision.should_apply:
                    best_action = f"recompile:{mod_path}"
                    best_target = mod_path
                    best_speedup = decision.estimated_speedup
                    best_confidence = decision.confidence
                    best_risk = decision.estimated_risk
                    best_reasoning = decision.reasoning

        # Check tile optimization opportunities
        for tile_name, tile_snap in genome.tiles.items():
            if tile_snap.cost_estimate > 2.0:
                proposal = MutationProposal(
                    strategy=MutationStrategy.REPLACE_TILE,
                    target=tile_name,
                    description=f"Replace expensive tile {tile_name}",
                    kwargs={"new_cost": tile_snap.cost_estimate * 0.5},
                    estimated_speedup=2.0,
                    estimated_risk=0.3,
                    priority=tile_snap.cost_estimate,
                )
                decision = self.should_mutate(proposal)

                if best_action == "" and decision.should_apply:
                    best_action = f"replace_tile:{tile_name}"
                    best_target = tile_name
                    best_speedup = decision.estimated_speedup
                    best_confidence = decision.confidence
                    best_risk = decision.estimated_risk
                    best_reasoning = decision.reasoning

        # Default recommendation
        if not best_action:
            best_action = "wait"
            best_target = ""
            best_reasoning = "No actionable mutations found. Monitor and re-evaluate."
            best_confidence = 0.5

        # Generate alternative actions
        alternatives = []
        if best_action.startswith("recompile:"):
            alternatives.append("wait")
            if genome.tiles:
                alternatives.append(f"replace_tile:{list(genome.tiles.keys())[0]}")
        elif best_action.startswith("replace_tile:"):
            alternatives.append("wait")

        # Time to implement
        if best_action.startswith("recompile:"):
            lang = "rust" if "HEAT" in best_reasoning or "HOT" in best_reasoning else "typescript"
            impl_time = COMPILE_TIMES_S.get(lang, 5.0) * 1000
        elif best_action.startswith("replace_tile:"):
            impl_time = 1000.0
        else:
            impl_time = 0.0

        return OracleRecommendation(
            action=best_action,
            target=best_target,
            estimated_speedup=best_speedup,
            confidence=best_confidence,
            risk=best_risk,
            reasoning=best_reasoning,
            alternative_actions=alternatives,
            time_to_implement_ms=impl_time,
            roi_estimate=best_roi,
        )

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def acceptance_rate(self) -> float:
        """Fraction of decisions that were accepted."""
        if self._decisions_made == 0:
            return 0.0
        return self._decisions_accepted / self._decisions_made

    @property
    def total_decisions(self) -> int:
        return self._decisions_made

    def __repr__(self) -> str:
        return (
            f"DecisionOracle("
            f"decisions={self._decisions_made}, "
            f"accepted={self._decisions_accepted}, "
            f"rate={self.acceptance_rate:.2f})"
        )
