"""Tests for the FLUX cost model and energy estimation."""

import pytest

from flux.fir.types import TypeContext
from flux.fir.values import Value
from flux.fir.instructions import (
    IAdd, ISub, IMul, IDiv, IMod, INeg,
    FAdd, FSub, FMul, FDiv, FNeg,
    IAnd, IOr, IXor, IShl, IShr, INot,
    IEq, INe, ILt, IGt, ILe, IGe,
    FEq, FLt, FGt, FLe, FGe,
    ITrunc, ZExt, SExt, FTrunc, FExt, Bitcast,
    Load, Store, Alloca, GetField, SetField, GetElem, SetElem, MemCopy, MemSet,
    Jump, Branch, Switch, Call, Return, Unreachable,
    Tell, Ask, Delegate, TrustCheck, CapRequire,
)
from flux.fir.blocks import FIRBlock, FIRFunction, FIRModule
from flux.cost.model import CostModel, CostEstimate, ModuleCostReport, SpeedupReport
from flux.cost.energy import EnergyModel, EnergyEstimate, CarbonEstimate


# ── Helpers ──────────────────────────────────────────────────────────────

ctx = TypeContext()
I32 = ctx.i32
F32 = ctx.f32
BOOL = ctx.get_bool()
UNIT = ctx.get_unit()

_val_counter = 0
def _val(name: str, typ=None) -> Value:
    global _val_counter
    _val_counter += 1
    return Value(id=_val_counter, name=name, type=typ or I32)

def _simple_func(name: str, instructions: list) -> FIRFunction:
    """Build a simple single-block FIR function."""
    block = FIRBlock(label="entry", instructions=instructions)
    sig = ctx.get_func((I32,), (I32,))
    return FIRFunction(name=name, sig=sig, blocks=[block])

def _empty_module(name: str) -> FIRModule:
    return FIRModule(name=name, type_ctx=ctx)


# ── Cost Model Tests ─────────────────────────────────────────────────────


class TestCostModelBasics:
    def test_empty_function(self):
        """Empty function has zero cost."""
        func = _simple_func("empty", [Return()])
        model = CostModel()
        est = model.estimate_function(func)
        assert est.total_ns > 0  # at least RET costs something
        assert est.instruction_count == 1

    def test_single_iadd(self):
        """Single IADD instruction."""
        func = _simple_func("add", [
            IAdd(lhs=_val("a"), rhs=_val("b")),
            Return(),
        ])
        model = CostModel()
        est = model.estimate_function(func)
        assert est.instruction_count == 2
        assert est.alu_ops == 1
        assert est.total_ns > 0

    def test_arithmetic_cost(self):
        """Arithmetic operations have correct cost category."""
        func = _simple_func("arith", [
            IAdd(_val("a"), _val("b")),
            ISub(_val("c"), _val("d")),
            IMul(_val("e"), _val("f")),
            Return(),
        ])
        model = CostModel()
        est = model.estimate_function(func)
        assert est.alu_ops == 3

    def test_division_cost(self):
        """Division is more expensive than addition."""
        add_func = _simple_func("add", [
            IAdd(_val("a"), _val("b")),
            Return(),
        ])
        div_func = _simple_func("div", [
            IDiv(_val("a"), _val("b")),
            Return(),
        ])
        model = CostModel()
        add_est = model.estimate_function(add_func)
        div_est = model.estimate_function(div_func)
        assert div_est.total_ns > add_est.total_ns

    def test_float_cost_higher_than_int(self):
        """Float operations cost more than integer operations."""
        int_func = _simple_func("int_op", [
            IAdd(_val("a"), _val("b")),
            Return(),
        ])
        float_func = _simple_func("float_op", [
            FAdd(_val("a", F32), _val("b", F32)),
            Return(),
        ])
        model = CostModel()
        int_est = model.estimate_function(int_func)
        float_est = model.estimate_function(float_func)
        assert float_est.total_ns > int_est.total_ns


class TestMemoryHierarchy:
    def test_memory_hierarchy_levels(self):
        """All 4 memory hierarchy levels defined."""
        model = CostModel()
        assert len(model.MEMORY_HIERARCHY) == 4
        assert "L1" in model.MEMORY_HIERARCHY
        assert "L2" in model.MEMORY_HIERARCHY
        assert "L3" in model.MEMORY_HIERARCHY
        assert "DRAM" in model.MEMORY_HIERARCHY

    def test_memory_hierarchy_probabilities_sum(self):
        """Memory hierarchy probabilities should sum to ~1.0."""
        model = CostModel()
        total = sum(prob for _, prob in model.MEMORY_HIERARCHY.values())
        assert abs(total - 1.0) < 0.001

    def test_l1_cheapest(self):
        """L1 has lowest latency."""
        model = CostModel()
        assert model.MEMORY_HIERARCHY["L1"][0] < model.MEMORY_HIERARCHY["L2"][0]
        assert model.MEMORY_HIERARCHY["L2"][0] < model.MEMORY_HIERARCHY["L3"][0]
        assert model.MEMORY_HIERARCHY["L3"][0] < model.MEMORY_HIERARCHY["DRAM"][0]

    def test_load_cost_uses_hierarchy(self):
        """Load instruction cost includes memory hierarchy model."""
        func = _simple_func("load_test", [
            Load(type=I32, ptr=_val("ptr")),
            Return(),
        ])
        model = CostModel()
        est = model.estimate_function(func)
        assert est.memory_ops == 1
        # Expected cost = sum of (latency * probability)
        expected = sum(lat * prob for lat, prob in model.MEMORY_HIERARCHY.values())
        # Total includes RET cost too
        assert est.total_ns > expected

    def test_store_is_cheaper_than_load(self):
        """Store costs less than load (no hierarchy model)."""
        load_func = _simple_func("ld", [Load(I32, _val("p")), Return()])
        store_func = _simple_func("st", [Store(_val("v"), _val("p")), Return()])
        model = CostModel()
        ld_est = model.estimate_function(load_func)
        st_est = model.estimate_function(store_func)
        # Load uses memory hierarchy (expected ~19ns), store is flat 0.5ns
        assert ld_est.total_ns > st_est.total_ns


class TestBranchPrediction:
    def test_branch_prediction_accuracy(self):
        """Default branch prediction accuracy is 90%."""
        model = CostModel()
        assert model.BRANCH_PREDICTION_ACCURACY == 0.90

    def test_branch_cost_model(self):
        """Branch cost accounts for misprediction penalty."""
        func = _simple_func("branch", [
            Branch(cond=_val("c"), true_block="t", false_block="f"),
            Return(),
        ])
        model = CostModel()
        est = model.estimate_function(func)
        # Branch is categorized as branch, Return is also categorized as branch
        assert est.branch_ops == 2
        # Expected: 0.5 * 0.9 + 5.0 * 0.1 = 0.45 + 0.5 = 0.95 per branch
        expected_branch = (0.5 * model.BRANCH_PREDICTION_ACCURACY +
                          model.BRANCH_MISPREDICT_COST_NS * (1 - model.BRANCH_PREDICTION_ACCURACY))
        assert est.total_ns > expected_branch


class TestModuleCostReport:
    def test_empty_module(self):
        """Empty module has zero cost."""
        module = _empty_module("empty")
        model = CostModel()
        report = model.estimate_module(module)
        assert report.function_count == 0
        assert report.total_ns == 0.0

    def test_module_with_multiple_functions(self):
        """Module with multiple functions sums costs."""
        f1 = _simple_func("f1", [IAdd(_val("a"), _val("b")), Return()])
        f2 = _simple_func("f2", [IMul(_val("a"), _val("b")), Return()])
        module = _empty_module("mod")
        module.functions["f1"] = f1
        module.functions["f2"] = f2
        model = CostModel()
        report = model.estimate_module(module)
        assert report.function_count == 2
        assert report.total_instructions > 0
        assert "f1" in report.functions
        assert "f2" in report.functions
        assert report.total_ns == report.functions["f1"].total_ns + report.functions["f2"].total_ns

    def test_module_name_preserved(self):
        """Module name is preserved in report."""
        module = _empty_module("test_mod")
        model = CostModel()
        report = model.estimate_module(module)
        assert report.module_name == "test_mod"


class TestBeforeAfterComparison:
    def test_identical_modules(self):
        """Comparing identical modules gives speedup of 1.0."""
        f1 = _simple_func("f", [IAdd(_val("a"), _val("b")), Return()])
        before = _empty_module("before")
        before.functions["f"] = f1
        after = _empty_module("after")
        after.functions["f"] = f1
        model = CostModel()
        report = model.compare(before, after)
        assert report.speedup_ratio == 1.0
        assert report.improvement_ns == 0.0

    def test_optimized_module(self):
        """After optimization (fewer instructions) shows speedup > 1."""
        before_f = _simple_func("f", [
            IAdd(_val("a"), _val("b")),
            IMul(_val("c"), _val("d")),
            Return(),
        ])
        after_f = _simple_func("f", [
            IMul(_val("c"), _val("d")),
            Return(),
        ])
        before = _empty_module("before")
        before.functions["f"] = before_f
        after = _empty_module("after")
        after.functions["f"] = after_f
        model = CostModel()
        report = model.compare(before, after)
        assert report.speedup_ratio > 1.0
        assert report.improvement_ns > 0
        assert "f" in report.improved_functions

    def test_regressed_function_detected(self):
        """Adding expensive instructions is detected as regression."""
        before_f = _simple_func("f", [Return()])
        after_f = _simple_func("f", [IDiv(_val("a"), _val("b")), Return()])
        before = _empty_module("b")
        before.functions["f"] = before_f
        after = _empty_module("a")
        after.functions["f"] = after_f
        model = CostModel()
        report = model.compare(before, after)
        assert report.speedup_ratio < 1.0
        assert "f" in report.regressed_functions


class TestBottleneckDetection:
    def test_bottleneck_found(self):
        """Most expensive function is identified as bottleneck."""
        cheap = _simple_func("cheap", [Return()])
        expensive = _simple_func("expensive", [
            IDiv(_val("a"), _val("b")),
            IDiv(_val("c"), _val("d")),
            FDiv(_val("e", F32), _val("f", F32)),
            Return(),
        ])
        module = _empty_module("mod")
        module.functions["cheap"] = cheap
        module.functions["expensive"] = expensive
        model = CostModel()
        name, cost = model.bottleneck_function(module)
        assert name == "expensive"
        assert cost > 0

    def test_empty_module_bottleneck(self):
        """Empty module returns empty bottleneck."""
        module = _empty_module("empty")
        model = CostModel()
        name, cost = model.bottleneck_function(module)
        assert name == ""
        assert cost == 0.0

    def test_single_function_bottleneck(self):
        """Single function module returns that function."""
        f = _simple_func("only", [IAdd(_val("a"), _val("b")), Return()])
        module = _empty_module("mod")
        module.functions["only"] = f
        model = CostModel()
        name, cost = model.bottleneck_function(module)
        assert name == "only"


class TestMemoryAccessPattern:
    def test_no_loads_is_none(self):
        """Function with no loads returns 'none'."""
        func = _simple_func("nop", [Return()])
        model = CostModel()
        assert model.memory_access_pattern(func) == "none"

    def test_loop_induction_is_sequential(self):
        """Loop induction variable suggests sequential pattern."""
        # Use a value named 'i' to trigger loop induction heuristic
        func = _simple_func("loop", [
            IAdd(_val("i"), _val("b")),
            Load(I32, _val("ptr")),
            Return(),
        ])
        model = CostModel()
        assert model.memory_access_pattern(func) == "sequential"

    def test_getelem_is_strided(self):
        """GetElem with induction suggests strided pattern."""
        func = _simple_func("indexed", [
            IAdd(_val("i"), _val("b")),
            GetElem(array_val=_val("arr"), index=_val("i"), elem_type=I32),
            Return(),
        ])
        model = CostModel()
        assert model.memory_access_pattern(func) == "strided"

    def test_random_load_is_random(self):
        """Random load without induction is 'random'."""
        func = _simple_func("random", [
            Load(I32, _val("ptr")),
            Return(),
        ])
        model = CostModel()
        assert model.memory_access_pattern(func) == "random"


class TestA2ACost:
    def test_tell_is_expensive(self):
        """A2A TELL is much more expensive than arithmetic."""
        a2a_func = _simple_func("a2a", [
            Tell(target_agent="agent", message=_val("m"), cap=_val("c")),
            Return(),
        ])
        arith_func = _simple_func("arith", [
            IAdd(_val("a"), _val("b")),
            Return(),
        ])
        model = CostModel()
        a2a_est = model.estimate_function(a2a_func)
        arith_est = model.estimate_function(arith_func)
        assert a2a_est.total_ns > arith_est.total_ns * 1000

    def test_a2a_counted(self):
        """A2A operations are counted separately."""
        func = _simple_func("multi_a2a", [
            Tell("a", _val("m1"), _val("c1")),
            Ask("b", _val("m2"), I32, _val("c2")),
            Return(),
        ])
        model = CostModel()
        est = model.estimate_function(func)
        assert est.a2a_ops == 2


class TestCostEstimateProperties:
    def test_total_us(self):
        """CostEstimate.total_us converts nanoseconds to microseconds."""
        est = CostEstimate("test", total_ns=1000.0)
        assert est.total_us == 1.0

    def test_total_ms(self):
        """CostEstimate.total_ms converts nanoseconds to milliseconds."""
        est = CostEstimate("test", total_ns=1_000_000.0)
        assert est.total_ms == 1.0


# ── Energy Model Tests ───────────────────────────────────────────────────


class TestEnergyModelBasics:
    def test_empty_function_energy(self):
        """Empty function has some energy cost."""
        func = _simple_func("empty", [Return()])
        model = EnergyModel()
        est = model.estimate_energy(func)
        assert est.total_nj > 0

    def test_iadd_energy(self):
        """Integer ALU energy cost is low."""
        func = _simple_func("add", [IAdd(_val("a"), _val("b")), Return()])
        model = EnergyModel()
        est = model.estimate_energy(func)
        assert est.alu_energy_nj > 0

    def test_fadd_more_energy_than_iadd(self):
        """Float ALU uses more energy than integer ALU."""
        int_func = _simple_func("iadd", [IAdd(_val("a"), _val("b")), Return()])
        float_func = _simple_func("fadd", [FAdd(_val("a", F32), _val("b", F32)), Return()])
        model = EnergyModel()
        i_est = model.estimate_energy(int_func)
        f_est = model.estimate_energy(float_func)
        assert f_est.float_energy_nj > 0
        assert f_est.total_nj > i_est.total_nj

    def test_idiv_more_energy_than_iadd(self):
        """Integer division uses more energy than addition."""
        add_func = _simple_func("add", [IAdd(_val("a"), _val("b")), Return()])
        div_func = _simple_func("div", [IDiv(_val("a"), _val("b")), Return()])
        model = EnergyModel()
        add_est = model.estimate_energy(add_func)
        div_est = model.estimate_energy(div_func)
        assert div_est.total_nj > add_est.total_nj

    def test_memory_energy_uses_hierarchy(self):
        """Memory energy uses hierarchy model."""
        model = EnergyModel()
        assert len(model.MEMORY_ENERGY) == 4
        total_prob = sum(p for _, p in model.MEMORY_ENERGY.values())
        assert abs(total_prob - 1.0) < 0.001


class TestEnergyCategories:
    def test_energy_categories(self):
        """Energy estimate tracks all categories."""
        func = _simple_func("mixed", [
            IAdd(_val("a"), _val("b")),
            Load(I32, _val("p")),
            Branch(cond=_val("c"), true_block="t", false_block="f"),
            Call(func="helper"),
            Tell("agent", _val("m"), _val("c")),
            Return(),
        ])
        model = EnergyModel()
        est = model.estimate_energy(func)
        assert est.alu_energy_nj > 0
        assert est.memory_energy_nj > 0
        assert est.branch_energy_nj > 0
        assert est.call_energy_nj > 0
        assert est.a2a_energy_nj > 0

    def test_energy_estimate_properties(self):
        """EnergyEstimate unit conversion."""
        est = EnergyEstimate("test", total_nj=1_000_000.0)
        assert est.total_uj == 1000.0
        assert est.total_mj == 1.0


class TestCarbonEstimate:
    def test_basic_carbon(self):
        """Carbon estimate is computed for single execution."""
        func = _simple_func("f", [IAdd(_val("a"), _val("b")), Return()])
        model = EnergyModel()
        carbon = model.carbon_estimate(func)
        assert carbon.function_name == "f"
        assert carbon.carbon_grams > 0
        assert carbon.executions == 1

    def test_carbon_with_executions(self):
        """Carbon scales linearly with executions."""
        func = _simple_func("f", [IAdd(_val("a"), _val("b")), Return()])
        model = EnergyModel()
        c1 = model.carbon_estimate(func, executions=1)
        c100 = model.carbon_estimate(func, executions=100)
        # total_carbon_grams should be 100x the single-execution carbon
        expected = c1.total_carbon_grams * 100
        assert abs(c100.total_carbon_grams - expected) < 1e-20

    def test_carbon_per_million(self):
        """Carbon per million executions helper."""
        func = _simple_func("f", [Return()])
        model = EnergyModel()
        carbon = model.carbon_estimate(func)
        assert carbon.carbon_per_million_executions == carbon.carbon_grams * 1_000_000

    def test_grid_carbon_intensity(self):
        """Different grid carbon intensities affect estimate."""
        func = _simple_func("f", [Return()])
        model = EnergyModel()
        c_low = model.carbon_estimate(func, grid_carbon_g_per_kwh=100)
        c_high = model.carbon_estimate(func, grid_carbon_g_per_kwh=800)
        assert c_high.carbon_grams > c_low.carbon_grams

    def test_energy_kwh(self):
        """Energy in kWh is tiny for single execution."""
        func = _simple_func("f", [Return()])
        model = EnergyModel()
        carbon = model.carbon_estimate(func)
        assert carbon.energy_kwh > 0
        assert carbon.energy_kwh < 1e-9  # extremely small

    def test_carbon_properties(self):
        """CarbonEstimate property access."""
        func = _simple_func("f", [Return()])
        model = EnergyModel()
        carbon = model.carbon_estimate(func, executions=5)
        assert carbon.total_carbon_grams > 0
        assert carbon.executions == 5


class TestEnergyModelInheritsCostModel:
    def test_inherits_instruction_costs(self):
        """EnergyModel has all cost model instruction costs too."""
        model = EnergyModel()
        assert "iadd" in model.INSTRUCTION_COSTS
        assert "fdiv" in model.INSTRUCTION_COSTS
        assert "tell" in model.INSTRUCTION_COSTS

    def test_inherits_estimate_function(self):
        """EnergyModel can do cost estimation via parent."""
        func = _simple_func("f", [IAdd(_val("a"), _val("b")), Return()])
        model = EnergyModel()
        est = model.estimate_function(func)
        assert est.instruction_count == 2
        assert est.total_ns > 0

    def test_inherits_bottleneck(self):
        """EnergyModel inherits bottleneck detection."""
        f = _simple_func("f", [IDiv(_val("a"), _val("b")), Return()])
        module = _empty_module("mod")
        module.functions["f"] = f
        model = EnergyModel()
        name, cost = model.bottleneck_function(module)
        assert name == "f"


class TestMultipleBlockFunctions:
    def test_multi_block_cost(self):
        """Multi-block function sums all block costs."""
        block1 = FIRBlock(label="entry", instructions=[
            Branch(cond=_val("c"), true_block="then", false_block="end"),
        ])
        block2 = FIRBlock(label="then", instructions=[
            IAdd(_val("a"), _val("b")),
            Jump(target_block="end"),
        ])
        block3 = FIRBlock(label="end", instructions=[
            Return(),
        ])
        sig = ctx.get_func((I32,), (I32,))
        func = FIRFunction(name="multi", sig=sig, blocks=[block1, block2, block3])
        model = CostModel()
        est = model.estimate_function(func)
        assert est.instruction_count == 4  # branch + iadd + jump + return

    def test_multi_block_energy(self):
        """Multi-block function energy sums all blocks."""
        block1 = FIRBlock(label="entry", instructions=[
            Branch(cond=_val("c"), true_block="then", false_block="end"),
        ])
        block2 = FIRBlock(label="then", instructions=[
            FAdd(_val("a", F32), _val("b", F32)),
            Jump(target_block="end"),
        ])
        block3 = FIRBlock(label="end", instructions=[
            Return(),
        ])
        sig = ctx.get_func((I32,), (I32,))
        func = FIRFunction(name="multi", sig=sig, blocks=[block1, block2, block3])
        model = EnergyModel()
        est = model.estimate_energy(func)
        assert est.float_energy_nj > 0
        assert est.branch_energy_nj > 0
