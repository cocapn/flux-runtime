"""FIR-level cost estimation — static performance analysis without execution.

Estimates execution cost (nanoseconds) by walking FIR instruction trees
and summing per-instruction costs with memory hierarchy and branch
prediction models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from flux.fir.blocks import FIRFunction, FIRModule, FIRBlock
from flux.fir.instructions import (
    Instruction, IAdd, ISub, IMul, IDiv, IMod, INeg,
    FAdd, FSub, FMul, FDiv, FNeg,
    IAnd, IOr, IXor, IShl, IShr, INot,
    IEq, INe, ILt, IGt, ILe, IGe,
    FEq, FLt, FGt, FLe, FGe,
    ITrunc, ZExt, SExt, FTrunc, FExt, Bitcast,
    Load, Store, Alloca, GetField, SetField, GetElem, SetElem, MemCopy, MemSet,
    Jump, Branch, Switch, Call, Return, Unreachable,
    Tell, Ask, Delegate, TrustCheck, CapRequire,
)


@dataclass
class CostEstimate:
    """Cost estimate for a single function execution (one invocation)."""
    function_name: str
    total_ns: float = 0.0
    instruction_count: int = 0
    alu_ops: int = 0
    memory_ops: int = 0
    branch_ops: int = 0
    call_ops: int = 0
    a2a_ops: int = 0
    float_ops: int = 0
    div_ops: int = 0
    vector_ops: int = 0

    @property
    def total_us(self) -> float:
        return self.total_ns / 1000.0

    @property
    def total_ms(self) -> float:
        return self.total_ns / 1_000_000.0


@dataclass
class ModuleCostReport:
    """Cost estimates for all functions in a module."""
    module_name: str
    functions: dict[str, CostEstimate] = field(default_factory=dict)
    total_ns: float = 0.0
    total_instructions: int = 0

    @property
    def function_count(self) -> int:
        return len(self.functions)


@dataclass
class SpeedupReport:
    """Comparison of before/after optimization costs."""
    before_ns: float = 0.0
    after_ns: float = 0.0
    speedup_ratio: float = 1.0
    improvement_ns: float = 0.0
    improved_functions: list[str] = field(default_factory=list)
    regressed_functions: list[str] = field(default_factory=list)


class CostModel:
    """Estimates execution cost from FIR structure without running code.

    Per-instruction costs (nanoseconds):
    - Integer ALU (add, sub, mul, neg, bitwise): 0.3ns
    - Integer div/mod: 3.0ns
    - Float ALU (add, sub, mul, neg): 0.5ns
    - Float div: 5.0ns
    - Memory load (L1): 0.5ns
    - Memory load (L2): 3.0ns
    - Memory load (L3): 10.0ns
    - Memory load (DRAM): 80.0ns
    - Branch (predicted): 0.5ns
    - Branch (mispredicted): 5.0ns
    - Function call: 2.0ns
    - A2A message: 10000.0ns (10μs)
    - Conversion: 0.3ns
    """

    # Base instruction costs (nanoseconds)
    INSTRUCTION_COSTS: dict[str, float] = {
        # Integer ALU
        "iadd": 0.3, "isub": 0.3, "imul": 0.3, "ineg": 0.3,
        "iand": 0.3, "ior": 0.3, "ixor": 0.3, "ishl": 0.3, "ishr": 0.3,
        "inot": 0.3, "inc": 0.1, "dec": 0.1,
        # Integer division
        "idiv": 3.0, "imod": 3.0,
        # Float ALU
        "fadd": 0.5, "fsub": 0.5, "fmul": 0.5, "fneg": 0.5,
        # Float division
        "fdiv": 5.0,
        # Comparison
        "ieq": 0.3, "ine": 0.3, "ilt": 0.3, "igt": 0.3, "ile": 0.3, "ige": 0.3,
        "feq": 0.5, "flt": 0.5, "fgt": 0.5, "fle": 0.5, "fge": 0.5,
        # Conversion
        "itrunc": 0.3, "zext": 0.1, "sext": 0.1,
        "ftrunc": 0.3, "fext": 0.3, "bitcast": 0.1,
        # Control flow
        "jump": 0.5, "branch": 0.5, "switch": 1.0,
        "call": 2.0, "return": 0.3, "unreachable": 0.1,
        # Memory
        "load": 0.5, "store": 0.5,
        "alloca": 0.1, "getfield": 0.5, "setfield": 0.5,
        "getelem": 0.5, "setelem": 0.5,
        "memcpy": 1.0, "memset": 1.0,
        # A2A
        "tell": 10000.0, "ask": 10000.0, "delegate": 10000.0,
        "trustcheck": 100.0, "caprequire": 100.0,
    }

    # Memory hierarchy: (latency_ns, probability_of_accessing_this_level)
    MEMORY_HIERARCHY: dict[str, tuple[float, float]] = {
        "L1": (0.5, 0.000032),
        "L2": (3.0, 0.05),
        "L3": (10.0, 0.20),
        "DRAM": (80.0, 0.749968),
    }

    # Branch prediction accuracy
    BRANCH_PREDICTION_ACCURACY: float = 0.90
    BRANCH_MISPREDICT_COST_NS: float = 5.0

    def _instruction_cost(self, instr: Instruction) -> tuple[float, str]:
        """Return (cost_ns, category) for a single instruction."""
        opcode = instr.opcode
        base_cost = self.INSTRUCTION_COSTS.get(opcode, 0.5)

        if opcode in ("iadd", "isub", "imul", "ineg", "iand", "ior", "ixor",
                       "ishl", "ishr", "inot", "inc", "dec"):
            return base_cost, "alu"
        elif opcode in ("idiv", "imod"):
            return base_cost, "div"
        elif opcode in ("fadd", "fsub", "fmul", "fneg"):
            return base_cost, "float"
        elif opcode == "fdiv":
            return base_cost, "div"
        elif opcode in ("load", "getfield", "getelem"):
            return self._memory_cost(), "memory"
        elif opcode in ("store", "setfield", "setelem"):
            return base_cost, "memory"
        elif opcode in ("ieq", "ine", "ilt", "igt", "ile", "ige",
                         "feq", "flt", "fgt", "fle", "fge"):
            return base_cost, "alu"
        elif opcode in ("jump", "branch", "switch"):
            return self._branch_cost(), "branch"
        elif opcode == "call":
            return base_cost, "call"
        elif opcode in ("tell", "ask", "delegate"):
            return base_cost, "a2a"
        elif opcode in ("trustcheck", "caprequire"):
            return base_cost, "a2a"
        elif opcode in ("itrunc", "zext", "sext", "ftrunc", "fext", "bitcast"):
            return base_cost, "alu"
        elif opcode == "return":
            return base_cost, "branch"
        elif opcode in ("alloca", "memcpy", "memset"):
            return base_cost, "memory"
        else:
            return 0.5, "other"

    def _memory_cost(self) -> float:
        """Expected memory access cost using hierarchy probabilities."""
        expected = 0.0
        for level, (latency, prob) in self.MEMORY_HIERARCHY.items():
            expected += latency * prob
        return expected

    def _branch_cost(self) -> float:
        """Expected branch cost with misprediction penalty."""
        predicted_cost = 0.5
        mispredict_penalty = self.BRANCH_MISPREDICT_COST_NS
        accuracy = self.BRANCH_PREDICTION_ACCURACY
        return predicted_cost * accuracy + mispredict_penalty * (1.0 - accuracy)

    def estimate_function(self, func: FIRFunction) -> CostEstimate:
        """Estimate total cost of executing a function once."""
        est = CostEstimate(function_name=func.name)
        for block in func.blocks:
            for instr in block.instructions:
                cost, category = self._instruction_cost(instr)
                est.total_ns += cost
                est.instruction_count += 1
                if category == "alu":
                    est.alu_ops += 1
                elif category == "memory":
                    est.memory_ops += 1
                elif category == "branch":
                    est.branch_ops += 1
                elif category == "call":
                    est.call_ops += 1
                elif category == "a2a":
                    est.a2a_ops += 1
                elif category == "float":
                    est.float_ops += 1
                elif category == "div":
                    est.div_ops += 1
        return est

    def estimate_module(self, module: FIRModule) -> ModuleCostReport:
        """Estimate costs for all functions in a module."""
        report = ModuleCostReport(module_name=module.name)
        for fname, func in module.functions.items():
            est = self.estimate_function(func)
            report.functions[fname] = est
            report.total_ns += est.total_ns
            report.total_instructions += est.instruction_count
        return report

    def compare(self, before: FIRModule, after: FIRModule) -> SpeedupReport:
        """Compare before/after optimization costs."""
        before_report = self.estimate_module(before)
        after_report = self.estimate_module(after)

        speedup = SpeedupReport(
            before_ns=before_report.total_ns,
            after_ns=after_report.total_ns,
        )

        if after_report.total_ns > 0:
            speedup.speedup_ratio = before_report.total_ns / after_report.total_ns
        speedup.improvement_ns = before_report.total_ns - after_report.total_ns

        for fname in before_report.functions:
            b_cost = before_report.functions[fname].total_ns
            a_cost = after_report.functions.get(fname, CostEstimate(fname)).total_ns
            if a_cost < b_cost:
                speedup.improved_functions.append(fname)
            elif a_cost > b_cost:
                speedup.regressed_functions.append(fname)

        return speedup

    def bottleneck_function(self, module: FIRModule) -> tuple[str, float]:
        """Find the most expensive function in a module.

        Returns (function_name, cost_ns).  Returns ("", 0.0) if module is empty.
        """
        best_name = ""
        best_cost = 0.0
        for fname, func in module.functions.items():
            est = self.estimate_function(func)
            if est.total_ns > best_cost:
                best_cost = est.total_ns
                best_name = fname
        return best_name, best_cost

    def memory_access_pattern(self, func: FIRFunction) -> str:
        """Classify memory access pattern: 'sequential' / 'strided' / 'random'."""
        load_count = 0
        total_index_variance = 0.0
        has_getelem = False
        has_loop_induction = False

        for block in func.blocks:
            for instr in block.instructions:
                if isinstance(instr, Load):
                    load_count += 1
                elif isinstance(instr, GetElem):
                    has_getelem = True
                    load_count += 1
                elif isinstance(instr, (IAdd, ISub)):
                    # Check if this looks like a loop induction variable
                    if hasattr(instr.lhs, 'name') and 'i' in getattr(instr.lhs, 'name', '').lower():
                        has_loop_induction = True

        if load_count == 0:
            return "none"

        # Heuristic classification
        if has_loop_induction and not has_getelem:
            return "sequential"
        elif has_getelem and has_loop_induction:
            return "strided"
        else:
            return "random"
