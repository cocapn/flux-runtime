"""Energy cost estimation — extends CostModel with energy and carbon analysis.

Estimates energy consumption (nanojoules) and carbon footprint for
executing FIR functions, based on instruction-level energy costs and
memory hierarchy energy models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from flux.fir.blocks import FIRFunction, FIRModule
from flux.fir.instructions import Instruction
from flux.cost.model import CostModel, CostEstimate


@dataclass
class EnergyEstimate:
    """Energy estimate for a single function execution."""
    function_name: str
    total_nj: float = 0.0  # nanojoules
    instruction_count: int = 0
    alu_energy_nj: float = 0.0
    memory_energy_nj: float = 0.0
    branch_energy_nj: float = 0.0
    call_energy_nj: float = 0.0
    a2a_energy_nj: float = 0.0
    float_energy_nj: float = 0.0
    div_energy_nj: float = 0.0

    @property
    def total_uj(self) -> float:
        """Microjoules."""
        return self.total_nj / 1000.0

    @property
    def total_mj(self) -> float:
        """Millijoules."""
        return self.total_nj / 1_000_000.0


@dataclass
class CarbonEstimate:
    """Carbon footprint estimate for a single function execution."""
    function_name: str
    energy_nj: float = 0.0
    carbon_grams: float = 0.0
    grid_carbon_g_per_kwh: float = 400.0
    executions: int = 1

    @property
    def total_carbon_grams(self) -> float:
        return self.carbon_grams * self.executions

    @property
    def carbon_per_million_executions(self) -> float:
        return self.carbon_grams * 1_000_000

    @property
    def energy_kwh(self) -> float:
        """Energy in kilowatt-hours."""
        # 1 nJ = 1e-12 kWh
        return self.energy_nj * 1e-12 * self.executions


class EnergyModel(CostModel):
    """Extends CostModel with energy estimation.

    Per-instruction energy costs (nanojoules):
    - Integer ALU (add, sub, mul): 0.1 nJ
    - Integer div/mod: 1.0 nJ
    - Float ALU: 0.5 nJ
    - Float div: 3.0 nJ
    - Memory load (L1): 0.2 nJ
    - Memory load (DRAM): 25.0 nJ
    - Branch: 0.1 nJ
    - Function call: 0.5 nJ
    - A2A message: 5000.0 nJ
    """

    # Energy costs per instruction (nanojoules)
    ENERGY_COSTS: dict[str, float] = {
        # Integer ALU
        "iadd": 0.1, "isub": 0.1, "imul": 0.1, "ineg": 0.1,
        "iand": 0.1, "ior": 0.1, "ixor": 0.1, "ishl": 0.1, "ishr": 0.1,
        "inot": 0.1, "inc": 0.05, "dec": 0.05,
        # Integer division
        "idiv": 1.0, "imod": 1.0,
        # Float ALU
        "fadd": 0.5, "fsub": 0.5, "fmul": 0.5, "fneg": 0.5,
        # Float division
        "fdiv": 3.0,
        # Comparison
        "ieq": 0.1, "ine": 0.1, "ilt": 0.1, "igt": 0.1, "ile": 0.1, "ige": 0.1,
        "feq": 0.5, "flt": 0.5, "fgt": 0.5, "fle": 0.5, "fge": 0.5,
        # Conversion
        "itrunc": 0.1, "zext": 0.05, "sext": 0.05,
        "ftrunc": 0.1, "fext": 0.1, "bitcast": 0.05,
        # Control flow
        "jump": 0.1, "branch": 0.1, "switch": 0.2,
        "call": 0.5, "return": 0.1, "unreachable": 0.01,
        # Memory
        "load": 0.5, "store": 0.3,
        "alloca": 0.05, "getfield": 0.5, "setfield": 0.3,
        "getelem": 0.5, "setelem": 0.3,
        "memcpy": 0.5, "memset": 0.5,
        # A2A
        "tell": 5000.0, "ask": 5000.0, "delegate": 5000.0,
        "trustcheck": 50.0, "caprequire": 50.0,
    }

    # Memory hierarchy energy (nanojoules per access)
    MEMORY_ENERGY: dict[str, tuple[float, float]] = {
        "L1": (0.2, 0.000032),
        "L2": (1.0, 0.05),
        "L3": (5.0, 0.20),
        "DRAM": (25.0, 0.749968),
    }

    def _energy_cost(self, instr: Instruction) -> tuple[float, str]:
        """Return (energy_nj, category) for a single instruction."""
        opcode = instr.opcode
        base_energy = self.ENERGY_COSTS.get(opcode, 0.3)

        if opcode in ("iadd", "isub", "imul", "ineg", "iand", "ior", "ixor",
                       "ishl", "ishr", "inot", "inc", "dec",
                       "ieq", "ine", "ilt", "igt", "ile", "ige",
                       "itrunc", "zext", "sext", "ftrunc", "fext", "bitcast"):
            return base_energy, "alu"
        elif opcode in ("idiv", "imod"):
            return base_energy, "div"
        elif opcode in ("fadd", "fsub", "fmul", "fneg", "feq", "flt", "fgt", "fle", "fge"):
            return base_energy, "float"
        elif opcode == "fdiv":
            return base_energy, "div"
        elif opcode in ("load", "getfield", "getelem"):
            return self._memory_energy(), "memory"
        elif opcode in ("store", "setfield", "setelem"):
            return base_energy, "memory"
        elif opcode in ("jump", "branch", "switch"):
            return base_energy, "branch"
        elif opcode == "call":
            return base_energy, "call"
        elif opcode in ("tell", "ask", "delegate"):
            return base_energy, "a2a"
        elif opcode in ("trustcheck", "caprequire"):
            return base_energy, "a2a"
        elif opcode == "return":
            return base_energy, "branch"
        elif opcode in ("alloca", "memcpy", "memset"):
            return base_energy, "memory"
        else:
            return 0.3, "other"

    def _memory_energy(self) -> float:
        """Expected energy per memory access using hierarchy probabilities."""
        expected = 0.0
        for level, (energy, prob) in self.MEMORY_ENERGY.items():
            expected += energy * prob
        return expected

    def estimate_energy(self, func: FIRFunction) -> EnergyEstimate:
        """Estimate energy consumption for one function invocation."""
        est = EnergyEstimate(function_name=func.name)
        for block in func.blocks:
            for instr in block.instructions:
                energy, category = self._energy_cost(instr)
                est.total_nj += energy
                est.instruction_count += 1
                if category == "alu":
                    est.alu_energy_nj += energy
                elif category == "memory":
                    est.memory_energy_nj += energy
                elif category == "branch":
                    est.branch_energy_nj += energy
                elif category == "call":
                    est.call_energy_nj += energy
                elif category == "a2a":
                    est.a2a_energy_nj += energy
                elif category == "float":
                    est.float_energy_nj += energy
                elif category == "div":
                    est.div_energy_nj += energy
        return est

    def carbon_estimate(
        self,
        func: FIRFunction,
        grid_carbon_g_per_kwh: float = 400,
        executions: int = 1,
    ) -> CarbonEstimate:
        """Estimate carbon footprint of executing a function.

        Parameters
        ----------
        func:
            FIR function to estimate.
        grid_carbon_g_per_kwh:
            Carbon intensity of the electrical grid (grams CO2 per kWh).
            Default 400 g/kWh is the global average.
        executions:
            Number of times the function will be executed.
        """
        energy = self.estimate_energy(func)
        energy_per_exec_kwh = energy.total_nj * 1e-12
        carbon_per_exec_kwh = energy_per_exec_kwh * grid_carbon_g_per_kwh
        total_carbon = carbon_per_exec_kwh * executions

        return CarbonEstimate(
            function_name=func.name,
            energy_nj=energy.total_nj,
            carbon_grams=carbon_per_exec_kwh,  # per-execution
            grid_carbon_g_per_kwh=grid_carbon_g_per_kwh,
            executions=executions,
        )
