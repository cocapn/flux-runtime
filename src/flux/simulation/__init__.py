"""FLUX Simulation — digital twin, performance prediction, and speculative execution.

The simulation layer lets the system predict the future before committing to
changes. It provides:

- DigitalTwin: A shadow copy of the FLUX system that runs ahead in simulation
- PerformancePredictor: Predicts system performance without running workloads
- SpeculativeEngine: Executes multiple mutations in parallel (speculatively)
- DecisionOracle: Combines predictions and historical data for optimal decisions
"""

from .digital_twin import (
    DigitalTwin,
    SimulatedResult,
    SimulatedEvolutionReport,
    PredictionRecord,
    WhatIfResult,
    ChaosReport,
    ChaosFault,
    TwinReport,
)
from .predictor import (
    PerformancePredictor,
    CapacityForecast,
    MemoryStore,
)
from .speculator import (
    SpeculativeEngine,
    SpeculationResult,
)
from .oracle import (
    DecisionOracle,
    OracleDecision,
    OracleRecommendation,
    ROIEstimate,
)

__all__ = [
    # Digital Twin
    "DigitalTwin",
    "SimulatedResult",
    "SimulatedEvolutionReport",
    "PredictionRecord",
    "WhatIfResult",
    "ChaosReport",
    "ChaosFault",
    "TwinReport",
    # Predictor
    "PerformancePredictor",
    "CapacityForecast",
    "MemoryStore",
    # Speculator
    "SpeculativeEngine",
    "SpeculationResult",
    # Oracle
    "DecisionOracle",
    "OracleDecision",
    "OracleRecommendation",
    "ROIEstimate",
]
