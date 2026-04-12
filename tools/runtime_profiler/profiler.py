"""FLUX Runtime Profiler — Performance profiling tool for FLUX bytecode programs.

Instruments the FLUX VM interpreter to collect per-opcode performance data,
track hot paths, and measure memory behavior.  Supports three profiling modes:

    - **opcode-level**:  per-opcode execution count, cumulative time, avg time
    - **function-level**: call graph with inclusive/exclusive time per function
    - **memory-level**:  per-opcode memory allocation/deallocation tracking

Outputs profile data as JSON (machine-readable) and Markdown (human-readable).

Usage::

    from flux.runtime_profiler.profiler import FluxProfiler

    profiler = FluxProfiler(mode="opcode")
    result = profiler.profile_bytecode(bytecode)
    profiler.export_json("profile.json")
    profiler.export_markdown("profile.md")
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
import tracemalloc
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure project source is importable
_project_root = os.path.join(os.path.dirname(__file__), "..", "..", "src")
if _project_root not in sys.path:
    sys.path.insert(0, os.path.abspath(_project_root))

from flux.bytecode.opcodes import Op, get_format  # noqa: E402
from flux.vm.interpreter import Interpreter  # noqa: E402
from flux.vm.memory import MemoryManager  # noqa: E402
from flux.vm.registers import RegisterFile  # noqa: E402


# ── Constants ─────────────────────────────────────────────────────────────────

OPCODE_NAMES: Dict[int, str] = {}
for _name, _val in Op.__members__.items():
    OPCODE_NAMES[int(_val)] = _name

OPCODE_CATEGORIES: Dict[str, List[str]] = {
    "control_flow": [
        "NOP", "HALT", "JMP", "JZ", "JNZ", "JE", "JNE", "JG", "JL",
        "JGE", "JLE", "CALL", "CALL_IND", "TAILCALL", "RET", "YIELD",
        "DEBUG_BREAK", "EMERGENCY_STOP",
    ],
    "data_movement": [
        "MOV", "MOVI", "LOAD", "STORE", "LOAD8", "STORE8",
        "PUSH", "POP", "DUP", "SWAP", "ROT",
    ],
    "integer_arithmetic": [
        "IADD", "ISUB", "IMUL", "IDIV", "IMOD", "IREM", "INEG", "INC", "DEC",
    ],
    "bitwise": [
        "IAND", "IOR", "IXOR", "INOT", "ISHL", "ISHR", "ROTL", "ROTR",
    ],
    "comparison": [
        "ICMP", "IEQ", "ILT", "ILE", "IGT", "IGE", "TEST", "SETCC", "CMP",
    ],
    "stack_frame": [
        "ENTER", "LEAVE", "ALLOCA",
    ],
    "float_arithmetic": [
        "FADD", "FSUB", "FMUL", "FDIV", "FNEG", "FABS", "FMIN", "FMAX",
    ],
    "float_comparison": [
        "FEQ", "FLT", "FLE", "FGT", "FGE",
    ],
    "simd": [
        "VLOAD", "VSTORE", "VADD", "VSUB", "VMUL", "VDIV", "VFMA",
    ],
    "memory_management": [
        "REGION_CREATE", "REGION_DESTROY", "REGION_TRANSFER",
        "MEMCOPY", "MEMSET", "MEMCMP",
    ],
    "type_operations": [
        "CAST", "BOX", "UNBOX", "CHECK_TYPE", "CHECK_BOUNDS",
    ],
    "a2a_protocol": [
        "TELL", "ASK", "DELEGATE", "DELEGATE_RESULT",
        "REPORT_STATUS", "REQUEST_OVERRIDE", "BROADCAST", "REDUCE",
        "DECLARE_INTENT", "ASSERT_GOAL", "VERIFY_OUTCOME",
        "EXPLAIN_FAILURE", "SET_PRIORITY",
    ],
    "trust_capability": [
        "TRUST_CHECK", "TRUST_UPDATE", "TRUST_QUERY", "REVOKE_TRUST",
        "CAP_REQUIRE", "CAP_REQUEST", "CAP_GRANT", "CAP_REVOKE",
    ],
    "synchronization": [
        "BARRIER", "SYNC_CLOCK", "FORMATION_UPDATE",
    ],
    "evolution": [
        "EVOLVE", "INSTINCT", "WITNESS", "SNAPSHOT",
    ],
    "meta": [
        "CONF", "MERGE", "RESTORE",
    ],
    "resource": [
        "RESOURCE_ACQUIRE", "RESOURCE_RELEASE",
    ],
}

# Build reverse map: opcode_name -> category
OPCODE_TO_CATEGORY: Dict[str, str] = {}
for _cat, _ops in OPCODE_CATEGORIES.items():
    for _op in _ops:
        OPCODE_TO_CATEGORY[_op] = _cat

# Opcodes that are known to allocate memory
MEMORY_ALLOCATING_OPCODES: Set[int] = {
    int(Op.BOX), int(Op.REGION_CREATE), int(Op.ENTER),
    int(Op.ALLOCA), int(Op.SNAPSHOT), int(Op.PUSH), int(Op.DUP),
}

# Opcodes that are known to deallocate memory
MEMORY_DEALLOCATING_OPCODES: Set[int] = {
    int(Op.REGION_DESTROY), int(Op.LEAVE), int(Op.POP),
    int(Op.SWAP), int(Op.ROT),
}

# Default memory cost (bytes) attributed to each opcode
DEFAULT_MEMORY_COST: Dict[int, int] = {
    int(Op.BOX): 16,          # box table entry
    int(Op.REGION_CREATE): 4096,  # default region
    int(Op.ENTER): 64,        # frame allocation
    int(Op.ALLOCA): 64,       # stack allocation
    int(Op.SNAPSHOT): 1024,   # state snapshot
    int(Op.PUSH): 4,          # one 32-bit word
    int(Op.POP): -4,          # deallocate one word
    int(Op.DUP): 4,           # copy on stack
    int(Op.SWAP): 0,          # no net change
    int(Op.ROT): 0,           # no net change
    int(Op.LOAD): 0,
    int(Op.STORE): 0,
    int(Op.LOAD8): 0,
    int(Op.STORE8): 0,
    int(Op.MEMCOPY): 256,     # typical copy size estimate
    int(Op.MEMSET): 256,
}


# ── Profiling Modes ───────────────────────────────────────────────────────────

class ProfileMode(Enum):
    """Supported profiling granularity levels."""
    OPCODE = "opcode"
    FUNCTION = "function"
    MEMORY = "memory"
    FULL = "full"


# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class OpcodeStats:
    """Per-opcode performance statistics."""
    name: str = ""
    opcode_byte: int = 0
    execution_count: int = 0
    total_time_ns: int = 0
    min_time_ns: int = 0
    max_time_ns: int = 0
    total_memory_bytes: int = 0
    memory_alloc_count: int = 0
    memory_dealloc_count: int = 0
    self_time_ns: int = 0  # exclusive time (excluding sub-calls)
    # Per-PC histogram for hot-path detection
    pc_histogram: Dict[int, int] = field(default_factory=dict)
    format_letter: str = "C"
    category: str = "unknown"
    _pct_total_time: float = 0.0
    _pct_total_exec: float = 0.0

    @property
    def avg_time_ns(self) -> float:
        """Average execution time in nanoseconds."""
        return self.total_time_ns / self.execution_count if self.execution_count > 0 else 0.0

    @property
    def pct_total_time(self) -> float:
        """Percentage of total execution time."""
        return self._pct_total_time

    @pct_total_time.setter
    def pct_total_time(self, value: float) -> None:
        self._pct_total_time = value

    @property
    def pct_total_exec(self) -> float:
        """Percentage of total execution count."""
        return self._pct_total_exec

    @pct_total_exec.setter
    def pct_total_exec(self, value: float) -> None:
        self._pct_total_exec = value

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "name": self.name,
            "opcode_hex": f"0x{self.opcode_byte:02X}",
            "format": self.format_letter,
            "category": self.category,
            "execution_count": self.execution_count,
            "total_time_ns": self.total_time_ns,
            "avg_time_ns": round(self.avg_time_ns, 2),
            "min_time_ns": self.min_time_ns,
            "max_time_ns": self.max_time_ns,
            "self_time_ns": self.self_time_ns,
            "total_memory_bytes": self.total_memory_bytes,
            "memory_alloc_count": self.memory_alloc_count,
            "memory_dealloc_count": self.memory_dealloc_count,
            "hot_pcs": sorted(
                self.pc_histogram.items(), key=lambda x: x[1], reverse=True
            )[:10],
        }


@dataclass
class FunctionStats:
    """Per-function (call-region) performance statistics."""
    name: str = ""
    entry_pc: int = 0
    call_count: int = 0
    inclusive_time_ns: int = 0  # total time including callees
    exclusive_time_ns: int = 0  # time in this function only
    min_time_ns: int = 0
    max_time_ns: int = 0
    total_instructions: int = 0
    children: Dict[str, int] = field(default_factory=dict)  # child -> call count
    parent_functions: Set[str] = field(default_factory=set)

    @property
    def avg_time_ns(self) -> float:
        return self.inclusive_time_ns / self.call_count if self.call_count > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "entry_pc": self.entry_pc,
            "call_count": self.call_count,
            "inclusive_time_ns": self.inclusive_time_ns,
            "exclusive_time_ns": self.exclusive_time_ns,
            "avg_time_ns": round(self.avg_time_ns, 2),
            "min_time_ns": self.min_time_ns,
            "max_time_ns": self.max_time_ns,
            "total_instructions": self.total_instructions,
            "children": dict(self.children),
            "parent_functions": list(self.parent_functions),
        }


@dataclass
class MemorySnapshot:
    """Memory state at a point in time."""
    cycle: int = 0
    pc: int = 0
    opcode_name: str = ""
    heap_used: int = 0
    stack_used: int = 0
    regions_count: int = 0
    box_count: int = 0
    rss_bytes: int = 0
    tracemalloc_current: int = 0
    tracemalloc_peak: int = 0


@dataclass
class ProfileResult:
    """Complete result of a profiling session."""
    mode: str = "opcode"
    total_cycles: int = 0
    total_time_ns: int = 0
    total_instructions: int = 0
    bytecode_size: int = 0
    memory_size: int = 0
    timestamp: str = ""
    program_name: str = ""
    halted: bool = False
    error: Optional[str] = None
    opcode_stats: Dict[str, OpcodeStats] = field(default_factory=dict)
    function_stats: Dict[str, FunctionStats] = field(default_factory=dict)
    memory_snapshots: List[MemorySnapshot] = field(default_factory=list)
    peak_memory_bytes: int = 0
    peak_rss_bytes: int = 0
    call_depth_max: int = 0
    call_depth_avg: float = 0.0
    hot_path: List[Tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the full result to JSON."""
        return {
            "metadata": {
                "mode": self.mode,
                "total_cycles": self.total_cycles,
                "total_time_ns": self.total_time_ns,
                "total_time_ms": round(self.total_time_ns / 1_000_000, 3),
                "total_instructions": self.total_instructions,
                "bytecode_size": self.bytecode_size,
                "memory_size": self.memory_size,
                "timestamp": self.timestamp,
                "program_name": self.program_name,
                "halted": self.halted,
                "error": self.error,
                "peak_memory_bytes": self.peak_memory_bytes,
                "peak_rss_bytes": self.peak_rss_bytes,
                "call_depth_max": self.call_depth_max,
                "call_depth_avg": round(self.call_depth_avg, 2),
            },
            "opcode_stats": {
                name: stats.to_dict() for name, stats in self.opcode_stats.items()
            },
            "function_stats": {
                name: stats.to_dict() for name, stats in self.function_stats.items()
            },
            "memory_snapshots": [
                {
                    "cycle": s.cycle, "pc": s.pc, "opcode": s.opcode_name,
                    "heap_used": s.heap_used, "stack_used": s.stack_used,
                    "regions_count": s.regions_count, "box_count": s.box_count,
                    "rss_bytes": s.rss_bytes,
                    "tracemalloc_current": s.tracemalloc_current,
                    "tracemalloc_peak": s.tracemalloc_peak,
                }
                for s in self.memory_snapshots
            ],
            "hot_path": [
                {"opcode": op, "count": cnt} for op, cnt in self.hot_path
            ],
        }


# ── Profiling Interpreter ────────────────────────────────────────────────────

class ProfilingInterpreter(Interpreter):
    """A FLUX interpreter subclass that instruments every opcode for profiling.

    Hooks into the fetch-decode-execute loop to measure per-opcode timing,
    memory behavior, and call graph information without modifying the base
    interpreter logic.
    """

    def __init__(
        self,
        bytecode: bytes,
        memory_size: int = 65536,
        max_cycles: int = Interpreter.MAX_CYCLES,
        profile_mode: ProfileMode = ProfileMode.OPCODE,
        sample_interval: int = 0,
    ) -> None:
        super().__init__(bytecode, memory_size, max_cycles)
        self._profile_mode = profile_mode
        self._sample_interval = sample_interval

        # Per-opcode timing
        self._opcode_times: Dict[int, List[int]] = defaultdict(list)
        self._opcode_counts: Dict[int, int] = defaultdict(int)
        self._opcode_pc_hist: Dict[int, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        self._opcode_mem_allocs: Dict[int, int] = defaultdict(int)
        self._opcode_mem_deallocs: Dict[int, int] = defaultdict(int)
        self._opcode_mem_bytes: Dict[int, int] = defaultdict(int)

        # Function-level tracking
        self._call_stack: List[Tuple[str, int, int]] = []  # (func_name, entry_pc, start_time)
        self._function_entries: Dict[int, Tuple[str, int]] = {}  # return_addr -> (func_name, call_count)
        self._function_stats_raw: Dict[str, List[Dict]] = defaultdict(list)
        self._call_depth_history: List[int] = []
        self._current_call_depth: int = 0
        self._max_call_depth: int = 0

        # Memory tracking
        self._memory_snapshots: List[MemorySnapshot] = []
        self._peak_memory: int = 0
        self._peak_rss: int = 0
        self._prev_sp: int = memory_size  # track stack usage changes

        # Hot-path tracking
        self._instruction_stream: List[Tuple[int, int]] = []  # (opcode_byte, pc)

        # Enable tracemalloc for memory-level profiling
        if profile_mode in (ProfileMode.MEMORY, ProfileMode.FULL):
            if not tracemalloc.is_tracing():
                tracemalloc.start(25)  # capture up to 25 frames

    def execute(self) -> int:
        """Execute with profiling instrumentation."""
        # Snapshot initial memory state
        self._take_memory_snapshot(0, 0, "START")

        start_time = time.perf_counter_ns()
        result_cycles = super().execute()
        end_time = time.perf_counter_ns()

        # Final memory snapshot
        self._take_memory_snapshot(self.cycle_count, self.pc, "END")
        self._peak_rss = self._get_rss()

        # Store total timing
        self._total_wall_ns = end_time - start_time

        # Finalize call depth stats
        if self._call_depth_history:
            avg_depth = sum(self._call_depth_history) / len(self._call_depth_history)
        else:
            avg_depth = 0.0

        self._final_stats = {
            "total_wall_ns": self._total_wall_ns,
            "total_cycles": result_cycles,
            "max_call_depth": self._max_call_depth,
            "avg_call_depth": avg_depth,
        }

        return result_cycles

    def _step(self) -> None:
        """Instrumented single-step: measure time, memory, call graph."""
        start_pc = self.pc
        step_start = time.perf_counter_ns()

        # Record the opcode byte before execution
        opcode_byte = self.bytecode[self.pc] if self.pc < len(self.bytecode) else 0

        # Track call depth before execution (to detect CALL/RET)
        prev_call_depth = self._current_call_depth
        prev_sp = self.regs.sp

        # Execute the instruction via the parent class
        super()._step()

        # Measure elapsed time for this single instruction
        step_end = time.perf_counter_ns()
        elapsed_ns = step_end - step_start

        # ── Opcode-level stats ───────────────────────────────────────────
        if self._profile_mode in (ProfileMode.OPCODE, ProfileMode.FULL):
            self._opcode_counts[opcode_byte] += 1
            self._opcode_times[opcode_byte].append(elapsed_ns)
            self._opcode_pc_hist[opcode_byte][start_pc] += 1

            # Memory attribution
            if opcode_byte in DEFAULT_MEMORY_COST:
                cost = DEFAULT_MEMORY_COST[opcode_byte]
                self._opcode_mem_bytes[opcode_byte] += cost
                if cost > 0:
                    self._opcode_mem_allocs[opcode_byte] += 1
                elif cost < 0:
                    self._opcode_mem_deallocs[opcode_byte] += 1

            # Track instruction stream for hot-path analysis
            self._instruction_stream.append((opcode_byte, start_pc))

        # ── Function-level stats ─────────────────────────────────────────
        if self._profile_mode in (ProfileMode.FUNCTION, ProfileMode.FULL):
            op_name = OPCODE_NAMES.get(opcode_byte, f"UNKNOWN_0x{opcode_byte:02X}")

            if opcode_byte == int(Op.CALL):
                # Record function entry
                target_pc = self.pc  # PC after CALL has updated to target
                func_name = f"func_0x{target_pc:04X}"
                self._call_stack.append((func_name, start_pc, step_start))
                self._current_call_depth += 1
                self._max_call_depth = max(self._max_call_depth, self._current_call_depth)

            elif opcode_byte == int(Op.RET):
                # Record function exit
                if self._call_stack:
                    func_name, entry_pc, call_start = self._call_stack.pop()
                    call_time = step_end - call_start
                    self._function_stats_raw[func_name].append({
                        "call_time": call_time,
                        "entry_pc": entry_pc,
                    })
                    self._current_call_depth = max(0, self._current_call_depth - 1)

            # Track call depth per instruction
            self._call_depth_history.append(self._current_call_depth)

        # ── Memory-level stats ───────────────────────────────────────────
        if self._profile_mode in (ProfileMode.MEMORY, ProfileMode.FULL):
            # Take periodic memory snapshots
            should_sample = (
                self._sample_interval > 0
                and self.cycle_count % self._sample_interval == 0
            )
            # Also sample on memory-intensive opcodes
            is_mem_heavy = opcode_byte in (
                int(Op.BOX), int(Op.REGION_CREATE), int(Op.REGION_DESTROY),
                int(Op.ENTER), int(Op.LEAVE), int(Op.ALLOCA),
            )
            if should_sample or is_mem_heavy:
                op_name = OPCODE_NAMES.get(opcode_byte, f"UNKNOWN_0x{opcode_byte:02X}")
                self._take_memory_snapshot(
                    self.cycle_count, start_pc, op_name
                )

            # Track stack usage delta
            sp_delta = prev_sp - self.regs.sp
            if sp_delta > 0:
                self._opcode_mem_allocs[opcode_byte] += 1
                self._opcode_mem_bytes[opcode_byte] += sp_delta
            elif sp_delta < 0:
                self._opcode_mem_deallocs[opcode_byte] += 1
                self._opcode_mem_bytes[opcode_byte] += sp_delta

    def _take_memory_snapshot(self, cycle: int, pc: int, opcode_name: str) -> None:
        """Capture a memory state snapshot."""
        snapshot = MemorySnapshot(
            cycle=cycle,
            pc=pc,
            opcode_name=opcode_name,
            heap_used=0,
            stack_used=self.memory.get_region("stack").size - self.regs.sp,
            regions_count=len(self.memory._regions),
            box_count=len(self._box_table),
            rss_bytes=self._get_rss(),
        )

        if tracemalloc.is_tracing():
            current, peak = tracemalloc.get_traced_memory()
            snapshot.tracemalloc_current = current
            snapshot.tracemalloc_peak = peak
            self._peak_memory = max(self._peak_memory, peak)

        self._memory_snapshots.append(snapshot)

    @staticmethod
    def _get_rss() -> int:
        """Get the resident set size (cross-platform)."""
        try:
            import resource
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        except (ImportError, AttributeError):
            pass
        try:
            # Linux /proc
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) * 1024
        except (FileNotFoundError, ValueError):
            pass
        return 0


# ── Main Profiler Class ───────────────────────────────────────────────────────

class FluxProfiler:
    """High-level FLUX runtime profiler.

    Wraps ``ProfilingInterpreter`` and provides analysis, hot-path detection,
    and export capabilities (JSON + Markdown).

    Parameters
    ----------
    mode :
        Profiling granularity: ``"opcode"``, ``"function"``, ``"memory"``, or ``"full"``.
    sample_interval :
        Number of cycles between memory snapshots (0 = only on heavy ops).
    memory_size :
        VM memory region size in bytes.
    max_cycles :
        Maximum execution cycle budget.
    """

    def __init__(
        self,
        mode: str = "opcode",
        sample_interval: int = 1000,
        memory_size: int = 65536,
        max_cycles: int = Interpreter.MAX_CYCLES,
    ) -> None:
        self.mode = ProfileMode(mode)
        self.sample_interval = sample_interval
        self.memory_size = memory_size
        self.max_cycles = max_cycles
        self._last_result: Optional[ProfileResult] = None

    def profile_bytecode(
        self,
        bytecode: bytes,
        program_name: str = "unnamed",
    ) -> ProfileResult:
        """Profile a FLUX bytecode program.

        Parameters
        ----------
        bytecode :
            Raw FLUX bytecode bytes.
        program_name :
            Human-readable name for the program (used in reports).

        Returns
        -------
        ProfileResult
            Complete profiling data.
        """
        vm = ProfilingInterpreter(
            bytecode=bytecode,
            memory_size=self.memory_size,
            max_cycles=self.max_cycles,
            profile_mode=self.mode,
            sample_interval=self.sample_interval,
        )

        try:
            total_cycles = vm.execute()
            error = None
        except Exception as exc:
            total_cycles = vm.cycle_count
            error = f"{type(exc).__name__}: {exc}"

        result = self._build_result(vm, bytecode, program_name, total_cycles, error)
        self._last_result = result
        return result

    def profile_bytecode_repeat(
        self,
        bytecode: bytes,
        program_name: str = "unnamed",
        iterations: int = 5,
    ) -> ProfileResult:
        """Profile bytecode multiple times and aggregate results.

        Runs the program *iterations* times and merges the opcode stats,
        keeping the best (lowest) total time.

        Parameters
        ----------
        bytecode :
            Raw FLUX bytecode bytes.
        program_name :
            Human-readable name for the program.
        iterations :
            Number of profiling iterations.

        Returns
        -------
        ProfileResult
            Aggregated profiling data from the best run.
        """
        best_result: Optional[ProfileResult] = None

        for i in range(iterations):
            result = self.profile_bytecode(bytecode, f"{program_name}_run{i}")
            if best_result is None or result.total_time_ns < best_result.total_time_ns:
                best_result = result

        if best_result is not None:
            best_result.program_name = f"{program_name} (best of {iterations})"
        return best_result or self._empty_result(program_name)

    def _build_result(
        self,
        vm: ProfilingInterpreter,
        bytecode: bytes,
        program_name: str,
        total_cycles: int,
        error: Optional[str],
    ) -> ProfileResult:
        """Build a ProfileResult from the raw VM profiling data."""
        result = ProfileResult(
            mode=self.mode.value,
            total_cycles=total_cycles,
            total_time_ns=getattr(vm, "_total_wall_ns", 0),
            total_instructions=sum(vm._opcode_counts.values()),
            bytecode_size=len(bytecode),
            memory_size=self.memory_size,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            program_name=program_name,
            halted=vm.halted,
            error=error,
            memory_snapshots=vm._memory_snapshots,
            peak_memory_bytes=vm._peak_memory,
            peak_rss_bytes=vm._peak_rss,
            call_depth_max=getattr(vm, "_max_call_depth", 0),
            call_depth_avg=getattr(vm, "_final_stats", {}).get("avg_call_depth", 0.0),
        )

        final_stats = getattr(vm, "_final_stats", {})
        result.call_depth_max = final_stats.get("max_call_depth", 0)
        result.call_depth_avg = final_stats.get("avg_call_depth", 0.0)

        # ── Build opcode stats ───────────────────────────────────────────
        total_time = 0
        total_exec = 0
        for opcode_byte, times in vm._opcode_times.items():
            op_name = OPCODE_NAMES.get(opcode_byte, f"UNKNOWN_0x{opcode_byte:02X}")
            stats = OpcodeStats(
                name=op_name,
                opcode_byte=opcode_byte,
                execution_count=vm._opcode_counts.get(opcode_byte, 0),
                total_time_ns=sum(times),
                min_time_ns=min(times) if times else 0,
                max_time_ns=max(times) if times else 0,
                total_memory_bytes=vm._opcode_mem_bytes.get(opcode_byte, 0),
                memory_alloc_count=vm._opcode_mem_allocs.get(opcode_byte, 0),
                memory_dealloc_count=vm._opcode_mem_deallocs.get(opcode_byte, 0),
                pc_histogram=dict(vm._opcode_pc_hist.get(opcode_byte, {})),
                format_letter=get_format(Op(opcode_byte)),
                category=OPCODE_TO_CATEGORY.get(op_name, "unknown"),
            )
            result.opcode_stats[op_name] = stats
            total_time += stats.total_time_ns
            total_exec += stats.execution_count

        # Set percentage fields
        for stats in result.opcode_stats.values():
            stats.pct_total_time = (
                (stats.total_time_ns / total_time * 100) if total_time > 0 else 0.0
            )
            stats.pct_total_exec = (
                (stats.execution_count / total_exec * 100) if total_exec > 0 else 0.0
            )

        # ── Build function stats ─────────────────────────────────────────
        for func_name, calls in vm._function_stats_raw.items():
            if not calls:
                continue
            times = [c["call_time"] for c in calls]
            entry_pc = calls[0]["entry_pc"]
            func_stat = FunctionStats(
                name=func_name,
                entry_pc=entry_pc,
                call_count=len(calls),
                inclusive_time_ns=sum(times),
                exclusive_time_ns=sum(times),  # simplified: no callee subtraction
                min_time_ns=min(times),
                max_time_ns=max(times),
                total_instructions=len(times),  # rough estimate
            )
            result.function_stats[func_name] = func_stat

        # ── Detect hot path ──────────────────────────────────────────────
        result.hot_path = self._detect_hot_path(vm._instruction_stream)

        return result

    @staticmethod
    def _detect_hot_path(
        stream: List[Tuple[int, int]],
        window_size: int = 8,
        min_repeats: int = 3,
    ) -> List[Tuple[str, int]]:
        """Detect frequently-executed instruction sequences (hot paths).

        Uses a sliding-window approach to find opcode subsequences that
        appear more than *min_repeats* times.

        Parameters
        ----------
        stream :
            List of (opcode_byte, pc) tuples.
        window_size :
            Length of the sliding window.
        min_repeats :
            Minimum repeat count for a sequence to be considered hot.

        Returns
        -------
        List of (opcode_name, occurrence_count) sorted by frequency.
        """
        if len(stream) < window_size * 2:
            return []

        # Build n-gram frequency map
        ngram_counts: Dict[Tuple[int, ...], int] = defaultdict(int)
        for i in range(len(stream) - window_size + 1):
            ngram = tuple(stream[i + j][0] for j in range(window_size))
            ngram_counts[ngram] += 1

        # Filter to hot sequences and count per-opcode appearances
        opcode_appearances: Dict[int, int] = defaultdict(int)
        for ngram, count in ngram_counts.items():
            if count >= min_repeats:
                for opcode_byte in ngram:
                    opcode_appearances[opcode_byte] += count

        # Sort by frequency
        sorted_opcodes = sorted(opcode_appearances.items(), key=lambda x: x[1], reverse=True)
        return [
            (OPCODE_NAMES.get(op, f"UNKNOWN_0x{op:02X}"), count)
            for op, count in sorted_opcodes[:20]
            if count > 0
        ]

    def _empty_result(self, program_name: str) -> ProfileResult:
        """Return an empty ProfileResult."""
        return ProfileResult(
            mode=self.mode.value,
            program_name=program_name,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        )

    # ── Export Methods ───────────────────────────────────────────────────

    def export_json(self, filepath: str, result: Optional[ProfileResult] = None) -> None:
        """Export profile data as JSON.

        Parameters
        ----------
        filepath :
            Path to write the JSON file.
        result :
            Profile result to export (defaults to last result).
        """
        result = result or self._last_result
        if result is None:
            raise ValueError("No profiling result available. Run profile_bytecode() first.")

        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(result.to_dict(), f, indent=2, default=str)

    def export_markdown(
        self,
        filepath: str,
        result: Optional[ProfileResult] = None,
        top_n: int = 20,
    ) -> None:
        """Export profile data as a Markdown report with tables.

        Parameters
        ----------
        filepath :
            Path to write the Markdown file.
        result :
            Profile result to export.
        top_n :
            Number of items to include in top-N tables.
        """
        result = result or self._last_result
        if result is None:
            raise ValueError("No profiling result available. Run profile_bytecode() first.")

        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        md = self._generate_markdown(result, top_n)
        with open(filepath, "w") as f:
            f.write(md)

    def _generate_markdown(self, result: ProfileResult, top_n: int) -> str:
        """Generate a comprehensive Markdown report."""
        lines: List[str] = []
        sep = "\n\n"

        # ── Header ────────────────────────────────────────────────────────
        lines.append(f"# FLUX Runtime Profile: {result.program_name}\n")
        lines.append(f"**Mode:** {result.mode}  ")
        lines.append(f"**Timestamp:** {result.timestamp}  ")
        lines.append(f"**Halted:** {result.halted}")
        if result.error:
            lines.append(f"\n**Error:** {result.error}")

        # ── Summary ───────────────────────────────────────────────────────
        lines.append(f"\n## Summary\n")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Total Cycles | {result.total_cycles:,} |")
        lines.append(f"| Total Instructions | {result.total_instructions:,} |")
        lines.append(f"| Total Wall Time | {self._fmt_ns(result.total_time_ns)} |")
        lines.append(f"| Bytecode Size | {result.bytecode_size:,} bytes |")
        lines.append(f"| Memory Size | {result.memory_size:,} bytes |")
        lines.append(f"| Peak Memory (tracemalloc) | {self._fmt_bytes(result.peak_memory_bytes)} |")
        lines.append(f"| Peak RSS | {self._fmt_bytes(result.peak_rss_bytes)} |")
        lines.append(f"| Max Call Depth | {result.call_depth_max} |")
        lines.append(f"| Avg Call Depth | {result.call_depth_avg:.1f} |")
        if result.total_time_ns > 0 and result.total_instructions > 0:
            ns_per_inst = result.total_time_ns / result.total_instructions
            lines.append(f"| Avg Time per Instruction | {ns_per_inst:.1f} ns |")
            inst_per_sec = result.total_instructions / (result.total_time_ns / 1e9)
            lines.append(f"| Instructions/sec | {inst_per_sec:,.0f} |")

        # ── Top Executed Opcodes ──────────────────────────────────────────
        if result.opcode_stats:
            sorted_by_exec = sorted(
                result.opcode_stats.values(),
                key=lambda s: s.execution_count,
                reverse=True,
            )[:top_n]
            lines.append(f"\n## Top {top_n} Most Executed Opcodes\n")
            lines.append("| Rank | Opcode | Category | Count | % Total | Avg Time |")
            lines.append("|------|--------|----------|-------|---------|----------|")
            for i, s in enumerate(sorted_by_exec, 1):
                lines.append(
                    f"| {i} | `{s.name}` | {s.category} | "
                    f"{s.execution_count:,} | {s.pct_total_exec:.1f}% | "
                    f"{self._fmt_ns(s.avg_time_ns)} |"
                )

        # ── Top Time-Consuming Opcodes ────────────────────────────────────
        if result.opcode_stats:
            sorted_by_time = sorted(
                result.opcode_stats.values(),
                key=lambda s: s.total_time_ns,
                reverse=True,
            )[:top_n]
            lines.append(f"\n## Top {top_n} Time-Consuming Opcodes\n")
            lines.append("| Rank | Opcode | Category | Total Time | % Time | Count | Avg |")
            lines.append("|------|--------|----------|------------|--------|-------|-----|")
            for i, s in enumerate(sorted_by_time, 1):
                lines.append(
                    f"| {i} | `{s.name}` | {s.category} | "
                    f"{self._fmt_ns(s.total_time_ns)} | {s.pct_total_time:.1f}% | "
                    f"{s.execution_count:,} | {self._fmt_ns(s.avg_time_ns)} |"
                )

        # ── Hot Path Analysis ─────────────────────────────────────────────
        if result.hot_path:
            lines.append(f"\n## Hot Path Analysis\n")
            lines.append("Opcodes most frequently found in repeating sequences:\n")
            lines.append("| Rank | Opcode | Hot Path Weight |")
            lines.append("|------|--------|----------------|")
            total_weight = sum(count for _, count in result.hot_path)
            for i, (op_name, count) in enumerate(result.hot_path[:15], 1):
                pct = (count / total_weight * 100) if total_weight > 0 else 0
                lines.append(f"| {i} | `{op_name}` | {count:,} ({pct:.1f}%) |")

        # ── Category Breakdown ────────────────────────────────────────────
        if result.opcode_stats:
            cat_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
                "count": 0, "time": 0, "memory": 0,
            })
            for s in result.opcode_stats.values():
                cat = s.category
                cat_stats[cat]["count"] += s.execution_count
                cat_stats[cat]["time"] += s.total_time_ns
                cat_stats[cat]["memory"] += s.total_memory_bytes

            lines.append(f"\n## Category Breakdown\n")
            lines.append("| Category | Instructions | % Instructions | Total Time | Memory |")
            lines.append("|----------|-------------|----------------|------------|--------|")
            total_count = sum(c["count"] for c in cat_stats.values())
            sorted_cats = sorted(cat_stats.items(), key=lambda x: x[1]["count"], reverse=True)
            for cat_name, c in sorted_cats:
                pct = (c["count"] / total_count * 100) if total_count > 0 else 0
                lines.append(
                    f"| {cat_name} | {c['count']:,} | {pct:.1f}% | "
                    f"{self._fmt_ns(c['time'])} | {self._fmt_bytes(c['memory'])} |"
                )

        # ── Memory Profile ────────────────────────────────────────────────
        if result.opcode_stats:
            mem_sorted = sorted(
                result.opcode_stats.values(),
                key=lambda s: abs(s.total_memory_bytes),
                reverse=True,
            )[:top_n]
            has_mem = any(s.total_memory_bytes != 0 for s in mem_sorted)
            if has_mem:
                lines.append(f"\n## Memory Profile\n")
                lines.append("| Opcode | Allocs | Deallocs | Net Memory |")
                lines.append("|--------|--------|----------|------------|")
                for s in mem_sorted:
                    if s.total_memory_bytes != 0:
                        net = s.total_memory_bytes
                        sign = "+" if net > 0 else ""
                        lines.append(
                            f"| `{s.name}` | {s.memory_alloc_count:,} | "
                            f"{s.memory_dealloc_count:,} | {sign}{self._fmt_bytes(abs(net))} |"
                        )

        # ── Memory Snapshots ──────────────────────────────────────────────
        if result.memory_snapshots:
            lines.append(f"\n## Memory Snapshots\n")
            lines.append("| Cycle | PC | Opcode | Stack Used | Regions | Boxes | RSS |")
            lines.append("|-------|-----|--------|------------|---------|-------|-----|")
            # Show up to 20 evenly-spaced snapshots
            snap_count = min(len(result.memory_snapshots), 20)
            step = max(1, len(result.memory_snapshots) // snap_count)
            for idx in range(0, len(result.memory_snapshots), step):
                s = result.memory_snapshots[idx]
                lines.append(
                    f"| {s.cycle:,} | 0x{s.pc:04X} | {s.opcode_name} | "
                    f"{self._fmt_bytes(s.stack_used)} | {s.regions_count} | "
                    f"{s.box_count} | {self._fmt_bytes(s.rss_bytes)} |"
                )

        # ── Function Profile ──────────────────────────────────────────────
        if result.function_stats:
            sorted_funcs = sorted(
                result.function_stats.values(),
                key=lambda f: f.inclusive_time_ns,
                reverse=True,
            )[:top_n]
            lines.append(f"\n## Function Profile\n")
            lines.append("| Function | Calls | Inclusive Time | Exclusive Time | Avg |")
            lines.append("|----------|-------|---------------|---------------|-----|")
            for f in sorted_funcs:
                lines.append(
                    f"| `{f.name}` | {f.call_count:,} | "
                    f"{self._fmt_ns(f.inclusive_time_ns)} | "
                    f"{self._fmt_ns(f.exclusive_time_ns)} | "
                    f"{self._fmt_ns(f.avg_time_ns)} |"
                )

        # ── Recommendations ───────────────────────────────────────────────
        lines.append(f"\n## Recommendations\n")
        recommendations = self._generate_recommendations(result)
        for i, rec in enumerate(recommendations, 1):
            lines.append(f"{i}. {rec}")

        return sep.join(lines)

    def _generate_recommendations(self, result: ProfileResult) -> List[str]:
        """Generate performance tuning recommendations based on profile data."""
        recs: List[str] = []

        if not result.opcode_stats:
            recs.append("No opcode statistics collected. Run with mode='opcode' or 'full'.")
            return recs

        sorted_by_time = sorted(
            result.opcode_stats.values(),
            key=lambda s: s.total_time_ns,
            reverse=True,
        )

        # Check for excessive comparisons
        cmp_ops = ["ICMP", "IEQ", "ILT", "ILE", "IGT", "IGE", "CMP", "TEST", "SETCC"]
        cmp_total = sum(
            s.execution_count for s in result.opcode_stats.values() if s.name in cmp_ops
        )
        cmp_pct = (cmp_total / result.total_instructions * 100) if result.total_instructions > 0 else 0
        if cmp_pct > 30:
            recs.append(
                f"**High comparison ratio ({cmp_pct:.1f}%):** Consider branch prediction "
                f"optimizations or restructure control flow to reduce redundant comparisons."
            )

        # Check for excessive memory ops
        mem_ops = ["LOAD", "STORE", "LOAD8", "STORE8", "PUSH", "POP"]
        mem_total = sum(
            s.execution_count for s in result.opcode_stats.values() if s.name in mem_ops
        )
        mem_pct = (mem_total / result.total_instructions * 100) if result.total_instructions > 0 else 0
        if mem_pct > 40:
            recs.append(
                f"**High memory operation ratio ({mem_pct:.1f}%):** Consider register "
                f"allocation improvements to keep values in registers longer."
            )

        # Check for NOP prevalence
        nop_count = result.opcode_stats.get("NOP", OpcodeStats()).execution_count
        nop_pct = (nop_count / result.total_instructions * 100) if result.total_instructions > 0 else 0
        if nop_pct > 5:
            recs.append(
                f"**Excessive NOP instructions ({nop_pct:.1f}%):** Remove padding NOPs "
                f"from compiled bytecode to reduce execution overhead."
            )

        # Check call depth
        if result.call_depth_max > 50:
            recs.append(
                f"**Deep call stack (max depth {result.call_depth_max}):** Consider "
                f"converting recursive algorithms to iterative ones to reduce "
                f"call/RET overhead and stack memory usage."
            )

        # Check for memory-intensive opcodes
        box_count = result.opcode_stats.get("BOX", OpcodeStats()).execution_count
        if box_count > result.total_instructions * 0.1:
            recs.append(
                f"**Heavy boxing ({box_count:,} BOX ops):** Reduce type boxing "
                f"operations by using unboxed arithmetic where possible."
            )

        # Check SIMD utilization
        simd_ops = ["VADD", "VSUB", "VMUL", "VDIV", "VLOAD", "VSTORE", "VFMA"]
        simd_total = sum(
            s.execution_count for s in result.opcode_stats.values() if s.name in simd_ops
        )
        if simd_total == 0 and result.total_instructions > 1000:
            recs.append(
                "**No SIMD usage detected:** For data-parallel workloads, consider "
                "using VADD/VSUB/VMUL vector instructions to leverage SIMD parallelism."
            )

        # General performance note
        if sorted_by_time:
            top = sorted_by_time[0]
            recs.append(
                f"**Top time consumer:** `{top.name}` accounts for "
                f"{top.pct_total_time:.1f}% of execution time. "
                f"Focus optimization efforts here first."
            )

        if not recs:
            recs.append("No major performance issues detected. The program appears well-optimized.")

        return recs

    @staticmethod
    def _fmt_ns(ns: float) -> str:
        """Format nanoseconds into human-readable string."""
        if ns < 1000:
            return f"{ns:.1f} ns"
        elif ns < 1_000_000:
            return f"{ns / 1000:.1f} us"
        elif ns < 1_000_000_000:
            return f"{ns / 1_000_000:.2f} ms"
        else:
            return f"{ns / 1_000_000_000:.3f} s"

    @staticmethod
    def _fmt_bytes(n: int) -> str:
        """Format bytes into human-readable string."""
        if n < 0:
            return f"-{FluxProfiler._fmt_bytes(-n)}"
        if n < 1024:
            return f"{n} B"
        elif n < 1024 * 1024:
            return f"{n / 1024:.1f} KB"
        elif n < 1024 * 1024 * 1024:
            return f"{n / (1024 * 1024):.1f} MB"
        else:
            return f"{n / (1024 * 1024 * 1024):.2f} GB"


# ── CLI Entry Point ───────────────────────────────────────────────────────────

def _make_bytecode(program: list) -> bytes:
    """Helper to build bytecode from instruction tuples."""
    buf = bytearray()
    for item in program:
        if isinstance(item, int):
            buf.append(item)
        elif isinstance(item, (bytes, bytearray)):
            buf.extend(item)
    return bytes(buf)


def _cli_profile_file(args: list) -> None:
    """Profile a bytecode file from the command line."""
    import argparse

    parser = argparse.ArgumentParser(description="FLUX Runtime Profiler")
    parser.add_argument("bytecode_file", help="Path to FLUX bytecode file (.bin)")
    parser.add_argument(
        "--mode", choices=["opcode", "function", "memory", "full"],
        default="opcode", help="Profiling mode (default: opcode)",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output path prefix (e.g. 'out/profile' writes .json and .md)",
    )
    parser.add_argument(
        "--top-n", type=int, default=20,
        help="Number of top items in tables (default: 20)",
    )
    parser.add_argument(
        "--iterations", type=int, default=1,
        help="Number of profiling iterations (default: 1)",
    )
    parser.add_argument(
        "--sample-interval", type=int, default=1000,
        help="Memory snapshot interval in cycles (default: 1000)",
    )
    parser.add_argument(
        "--max-cycles", type=int, default=10_000_000,
        help="Maximum execution cycle budget (default: 10M)",
    )
    parsed = parser.parse_args(args)

    # Read bytecode file
    with open(parsed.bytecode_file, "rb") as f:
        bytecode = f.read()

    program_name = os.path.basename(parsed.bytecode_file)

    # Create profiler and run
    profiler = FluxProfiler(
        mode=parsed.mode,
        sample_interval=parsed.sample_interval,
        max_cycles=parsed.max_cycles,
    )

    if parsed.iterations > 1:
        result = profiler.profile_bytecode_repeat(
            bytecode, program_name, iterations=parsed.iterations,
        )
    else:
        result = profiler.profile_bytecode(bytecode, program_name)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"  FLUX Runtime Profile: {result.program_name}")
    print(f"{'=' * 60}")
    print(f"  Mode:              {result.mode}")
    print(f"  Total Cycles:      {result.total_cycles:,}")
    print(f"  Total Instructions: {result.total_instructions:,}")
    print(f"  Total Wall Time:   {FluxProfiler._fmt_ns(result.total_time_ns)}")
    print(f"  Bytecode Size:     {result.bytecode_size:,} bytes")
    print(f"  Halted:            {result.halted}")
    if result.error:
        print(f"  Error:             {result.error}")
    print(f"{'=' * 60}\n")

    # Export
    if parsed.output:
        profiler.export_json(f"{parsed.output}.json", result)
        profiler.export_markdown(f"{parsed.output}.md", result, top_n=parsed.top_n)
        print(f"  JSON:  {parsed.output}.json")
        print(f"  Report: {parsed.output}.md")
    else:
        # Print to stdout
        md = profiler._generate_markdown(result, parsed.top_n)
        print(md)


def _cli_benchmark(args: list) -> None:
    """Run built-in benchmarks from the command line."""
    import argparse

    parser = argparse.ArgumentParser(description="FLUX Runtime Profiler - Benchmarks")
    parser.add_argument(
        "--iterations", type=int, default=5,
        help="Statistical iterations per benchmark (default: 5)",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output path prefix for results",
    )
    parser.add_argument(
        "--mode", choices=["opcode", "function", "memory", "full"],
        default="full", help="Profiling mode for benchmarks",
    )
    parsed = parser.parse_args(args)

    # Import benchmark runner
    try:
        from tools.runtime_profiler.benchmark_runner import BenchmarkRunner
    except ImportError:
        # Try relative import
        sys.path.insert(0, os.path.dirname(__file__))
        from benchmark_runner import BenchmarkRunner

    runner = BenchmarkRunner(profile_mode=parsed.mode)
    results = runner.run_all(iterations=parsed.iterations)

    # Print results
    print(f"\n{'=' * 60}")
    print(f"  FLUX Benchmark Results ({parsed.iterations} iterations each)")
    print(f"{'=' * 60}\n")
    for r in results:
        name = r.get("name", "unknown")
        cycles = r.get("total_cycles", 0)
        time_ns = r.get("total_time_ns", 0)
        instrs = r.get("total_instructions", 0)
        status = "OK" if r.get("success", False) else "FAILED"
        print(f"  [{status:6s}] {name:30s} cycles={cycles:>10,}  "
              f"time={FluxProfiler._fmt_ns(time_ns):>10s}  instrs={instrs:>10,}")

    if parsed.output:
        import json
        with open(f"{parsed.output}.json", "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n  Results saved to {parsed.output}.json")


def main() -> None:
    """CLI entry point for the FLUX Runtime Profiler."""
    import argparse

    parser = argparse.ArgumentParser(
        description="FLUX Runtime Profiler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Profile subcommand
    profile_parser = subparsers.add_parser("profile", help="Profile a bytecode file")
    profile_parser.add_argument("bytecode_file", help="Path to FLUX bytecode file")
    profile_parser.add_argument("--mode", choices=["opcode", "function", "memory", "full"],
                                default="opcode")
    profile_parser.add_argument("--output", "-o", default=None)
    profile_parser.add_argument("--top-n", type=int, default=20)
    profile_parser.add_argument("--iterations", type=int, default=1)
    profile_parser.add_argument("--sample-interval", type=int, default=1000)
    profile_parser.add_argument("--max-cycles", type=int, default=10_000_000)

    # Benchmark subcommand
    bench_parser = subparsers.add_parser("benchmark", help="Run built-in benchmarks")
    bench_parser.add_argument("--iterations", type=int, default=5)
    bench_parser.add_argument("--output", "-o", default=None)
    bench_parser.add_argument("--mode", choices=["opcode", "function", "memory", "full"],
                              default="full")

    # Quick profile subcommand (profile inline bytecode)
    quick_parser = subparsers.add_parser("quick", help="Profile a quick inline program")
    quick_parser.add_argument("--cycles", type=int, default=100000,
                              help="Number of loop iterations")
    quick_parser.add_argument("--mode", choices=["opcode", "function", "memory", "full"],
                              default="opcode")
    quick_parser.add_argument("--output", "-o", default=None)

    args = parser.parse_args()

    if args.command == "profile":
        _cli_profile_file([
            args.bytecode_file, "--mode", args.mode, "--top-n", str(args.top_n),
            "--iterations", str(args.iterations), "--sample-interval",
            str(args.sample_interval), "--max-cycles", str(args.max_cycles),
        ] + (["--output", args.output] if args.output else []))
    elif args.command == "benchmark":
        _cli_benchmark([
            "--iterations", str(args.iterations),
            "--mode", args.mode,
        ] + (["--output", args.output] if args.output else []))
    elif args.command == "quick":
        # Build a simple loop program: MOVI R0, cycles; loop: INC R0; DEC R1; JNZ loop; HALT
        iters = args.cycles
        program = [
            Op.MOVI, 0x01, iters & 0xFF, (iters >> 8) & 0xFF,  # R1 = iterations
            Op.MOVI, 0x00, 0, 0,                                 # R0 = 0
        ]
        loop_start_offset = len(program) + 4  # after the JNZ instruction
        # We'll build the loop body and patch the JNZ offset
        loop_body = [
            Op.IADD, 0x00, 0x00, 0x01,  # R0 += R1 (accumulate)
            Op.DEC, 0x01,               # R1--
        ]
        jnz_placeholder = len(program) + len(loop_body)
        loop_body += [Op.JNZ, 0x01, 0, 0, Op.HALT]  # JNZ R1, offset (patched)
        program += loop_body

        # Patch JNZ offset (relative to PC after JNZ fetch, which is 4 bytes)
        # JNZ is at jnz_placeholder, takes 4 bytes, so PC after = jnz_placeholder + 4
        # We want to jump back to loop_start_offset
        # offset = loop_start_offset - (jnz_placeholder + 4)
        loop_body_start = jnz_placeholder - len(loop_body) + 4
        # Actually, loop body starts right after MOVI instructions
        loop_body_start_actual = 6  # 2 MOVI instructions = 6 bytes
        jnz_end = jnz_placeholder + 4
        offset = loop_body_start_actual - jnz_end
        # Encode offset as signed i16 little-endian
        program[jnz_placeholder + 2] = offset & 0xFF
        program[jnz_placeholder + 3] = (offset >> 8) & 0xFF

        bytecode = _make_bytecode(program)

        profiler = FluxProfiler(mode=args.mode)
        result = profiler.profile_bytecode(bytecode, f"quick_loop_{iters}")

        print(f"\nQuick Profile: {iters} loop iterations")
        print(f"  Total Instructions: {result.total_instructions:,}")
        print(f"  Total Time: {FluxProfiler._fmt_ns(result.total_time_ns)}")
        if result.total_time_ns > 0:
            ips = result.total_instructions / (result.total_time_ns / 1e9)
            print(f"  Throughput: {ips:,.0f} instructions/sec")

        if args.output:
            profiler.export_json(f"{args.output}.json", result)
            profiler.export_markdown(f"{args.output}.md", result)
            print(f"  Saved to {args.output}.json / {args.output}.md")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
