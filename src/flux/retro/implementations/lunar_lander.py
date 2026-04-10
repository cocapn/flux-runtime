"""FLUX Retro: Lunar Lander — physics simulation in pure FLUX bytecode.

The VM simulates a lunar lander descending to the surface:
  • R0 = altitude  (starts at 1000 m)
  • R1 = velocity  (starts at 0 m/tick, positive = upward)
  • R2 = fuel      (starts at 100 units)
  • R4 = tick counter
  • R5 = result code (0 = crashed, 1 = safe landing, 2 = still flying)
  • R6 = landing velocity (saved on touchdown)

Each tick:  velocity -= 2 (gravity),  optional thrust (+5, costs 1 fuel),
            altitude += velocity.  Safe landing when |velocity| < 10.
"""

from __future__ import annotations

import struct
from flux.bytecode.opcodes import Op
from flux.vm.interpreter import Interpreter
from ._builder import BytecodeBuilder

# Memory layout
_MEM_TICK_LOG = 1000       # start of tick-log area (altitude, velocity, fuel per tick)
_LOG_ENTRY_SIZE = 12       # 3 × i32 per tick
_MAX_TICKS = 50


class LunarLander:
    """Lunar Lander physics simulation running entirely in FLUX bytecode."""

    def __init__(self, thrust_schedule: list[int] | None = None):
        """
        Parameters
        ----------
        thrust_schedule:
            List of 0/1 values, one per tick.  1 = burn fuel, 0 = free-fall.
            If *None*, a smart default schedule is used that attempts a safe landing.
        """
        self.thrust_schedule = thrust_schedule or self._default_schedule()

    # ── smart default: burn near the end ────────────────────────────────

    @staticmethod
    def _default_schedule() -> list[int]:
        # Free-fall for 25 ticks then try to brake — dramatic demo
        sched = [0] * _MAX_TICKS
        for t in range(25, 40):
            sched[t] = 1
        return sched

    # ── bytecode generation ─────────────────────────────────────────────

    def build_bytecode(self) -> bytes:
        """Build FLUX bytecode that runs the full simulation.

        The thrust schedule is encoded in memory so the VM can read it.
        """
        b = BytecodeBuilder()

        # ── initialise registers ────────────────────────────────────────
        b.movi(0, 1000)   # R0  altitude = 1000
        b.movi(1, 0)      # R1  velocity = 0
        b.movi(2, 100)    # R2  fuel = 100
        b.movi(4, 0)      # R4  tick = 0
        b.movi(5, 0)      # R5  result = 0 (assume crash)
        b.movi(7, 0)      # R7  temp

        # ── main loop ───────────────────────────────────────────────────
        b.label("loop")

        # -- log current state before this tick --
        # R7 = _MEM_TICK_LOG + tick * 12
        b.movi(7, _MEM_TICK_LOG)
        b.movi(8, 12)                   # R8 = 12
        b.imul(8, 4, 8)                # R8 = tick * 12
        b.iadd(7, 7, 8)                # R7 = base + tick*12
        b.store(0, 7)                  # store altitude
        b.movi(8, 4)
        b.iadd(7, 7, 8)                # R7 += 4
        b.store(1, 7)                  # store velocity
        b.movi(8, 4)
        b.iadd(7, 7, 8)                # R7 += 4
        b.store(2, 7)                  # store fuel

        # -- read thrust for this tick from schedule in memory --
        b.movi(7, 500)                  # base of thrust schedule
        b.mov(8, 4)                    # R8 = tick
        b.iadd(7, 7, 8)                # R7 = 500 + tick
        b.load8(6, 7)                   # R6 = thrust schedule[tick]

        # -- gravity: velocity -= 2 --
        b.movi(7, 2)
        b.isub(1, 1, 7)               # R1 -= 2

        # -- thrust check: if thrust (R6 != 0) and fuel > 0 --
        b.jz(6, "skip_thrust")         # if R6 == 0, skip
        b.movi(7, 0)
        b.cmp(2, 7)                    # compare fuel with 0
        b.jle("skip_thrust")           # if fuel <= 0, skip

        # apply thrust
        b.movi(7, 5)
        b.iadd(1, 1, 7)               # velocity += 5
        b.dec(2)                       # fuel -= 1

        b.label("skip_thrust")

        # -- altitude += velocity --
        b.iadd(0, 0, 1)               # altitude += velocity

        # -- check landing: altitude <= 0 --
        b.movi(7, 0)
        b.cmp(0, 7)
        b.jg("not_landed")             # if altitude > 0, continue

        # --- landed ---
        b.mov(6, 1)                    # R6 = velocity (save)
        b.movi(5, 0)                   # assume crash

        # check |velocity| < 10  →  velocity > -10 AND velocity < 10
        b.movi(7, -10)
        b.cmp(6, 7)
        b.jl("crash")                  # velocity < -10 → crash

        b.movi(7, 10)
        b.cmp(6, 7)
        b.jge("crash")                 # velocity >= 10 → crash

        b.movi(5, 1)                   # safe landing!
        b.jmp("done")

        b.label("crash")
        b.movi(5, 0)                   # result = crash
        b.jmp("done")

        # --- not landed yet ---
        b.label("not_landed")

        b.inc(4)                       # tick++
        b.movi(7, _MAX_TICKS)
        b.cmp(4, 7)
        b.jl("loop")                   # if tick < 50, continue

        # ran out of ticks
        b.movi(5, 2)                   # still flying

        b.label("done")
        b.halt()

        return b.build()

    # ── execution ───────────────────────────────────────────────────────

    def run(self) -> dict:
        bc = self.build_bytecode()
        vm = Interpreter(bc, memory_size=65536)
        # Write thrust schedule into stack memory at offset 500
        stack = vm.memory.get_region("stack")
        for i, t in enumerate(self.thrust_schedule[:_MAX_TICKS]):
            stack.write(500 + i, bytes([t]))
        cycles = vm.execute()
        return {
            "cycles": cycles,
            "registers": {f"R{i}": vm.regs.read_gp(i) for i in range(16)},
            "halted": vm.halted,
            "altitude": vm.regs.read_gp(0),
            "velocity": vm.regs.read_gp(1),
            "fuel": vm.regs.read_gp(2),
            "ticks": vm.regs.read_gp(4),
            "result_code": vm.regs.read_gp(5),
        }

    def run_with_log(self) -> dict:
        """Run and also decode the tick-by-tick log from memory."""
        bc = self.build_bytecode()
        vm = Interpreter(bc, memory_size=65536)
        stack = vm.memory.get_region("stack")
        for i, t in enumerate(self.thrust_schedule[:_MAX_TICKS]):
            stack.write(500 + i, bytes([t]))
        cycles = vm.execute()
        ticks_completed = vm.regs.read_gp(4)
        log = []
        for t in range(ticks_completed):
            base = _MEM_TICK_LOG + t * _LOG_ENTRY_SIZE
            alt = stack.read_i32(base)
            vel = stack.read_i32(base + 4)
            fuel = stack.read_i32(base + 8)
            thrust = self.thrust_schedule[t] if t < len(self.thrust_schedule) else 0
            log.append({"tick": t, "altitude": alt, "velocity": vel,
                        "fuel": fuel, "thrust": bool(thrust)})
        # Add final state
        log.append({"tick": ticks_completed, "altitude": vm.regs.read_gp(0),
                     "velocity": vm.regs.read_gp(1), "fuel": vm.regs.read_gp(2),
                     "thrust": False})
        return {
            "cycles": cycles,
            "result_code": vm.regs.read_gp(5),
            "log": log,
        }

    # ── demonstration ───────────────────────────────────────────────────

    @staticmethod
    def demonstrate():
        print("=" * 60)
        print("  FLUX RETRO — LUNAR LANDER")
        print("  Physics simulation in FLUX bytecode")
        print("=" * 60)

        game = LunarLander()
        result = game.run_with_log()
        log = result["log"]
        rc = result["result_code"]

        print(f"\n  Thrust schedule: free-fall 25 ticks, burn ticks 25-39, coast")
        print(f"  {'TICK':>4}  {'ALT':>7}  {'VEL':>7}  {'FUEL':>5}  {'BURN':>4}")
        print("  " + "-" * 38)

        for entry in log:
            tick = entry["tick"]
            alt = entry["altitude"]
            vel = entry["velocity"]
            fuel = entry["fuel"]
            thrust = entry["thrust"]
            # Only print every 5th tick + first + last
            if tick <= 2 or tick >= len(log) - 2 or tick % 5 == 0:
                burn_str = "🔥" if thrust else "  "
                bar_len = min(max(alt // 20, 0), 30)
                bar = "█" * bar_len
                print(f"  {tick:>4}  {alt:>7}  {vel:>+7}  {fuel:>5}  {burn_str}  {bar}")

        print()
        result_text = {0: "CRASHED 💥", 1: "SAFE LANDING 🎉", 2: "STILL FLYING ✈️"}
        print(f"  Result: {result_text.get(rc, 'UNKNOWN')}")
        final = log[-1]
        print(f"  Final altitude: {final['altitude']} m")
        print(f"  Final velocity: {final['velocity']} m/tick")
        print(f"  Fuel remaining: {final['fuel']}")
        print(f"  Ticks used:     {len(log) - 1}")
        print(f"  VM cycles:      {result['cycles']}")
        print()
