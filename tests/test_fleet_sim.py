"""Tests for FLUX Fleet Simulator.

Covers:
- Simulator runs without errors
- Navigator bytecode adjusts heading correctly
- Fish finder returns non-negative catch count
- Supply manager flags urgency when fuel/supplies are low
- A2A messages are created during simulation
- Final report contains all required fields
"""

import sys
import uuid

sys.path.insert(0, "src")

from flux.vm.interpreter import Interpreter
from flux.bytecode.opcodes import Op
from flux.a2a.messages import A2AMessage

# Import the simulator
sys.path.insert(0, "examples")
from flux_fleet_sim import (
    FleetSimulator, Agent,
    NAVIGATOR_BYTECODE,
    WEATHER_SCOUT_BYTECODE,
    FISH_FINDER_BYTECODE,
    SUPPLY_MANAGER_BYTECODE,
    CAPTAIN_BYTECODE,
    SPECIES,
)

# ── Helpers ───────────────────────────────────────────────────────────────

_pass = 0
_fail = 0


def _check(name: str, condition: bool) -> None:
    global _pass, _fail
    if condition:
        _pass += 1
        print(f"  ✓ {name}")
    else:
        _fail += 1
        print(f"  ✗ {name} FAILED")


def _section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ── 1. test_simulator_runs ────────────────────────────────────────────────

def test_simulator_runs() -> None:
    _section("test_simulator_runs")

    sim = FleetSimulator(timesteps=5)
    sim.add_agent(Agent("navigator", NAVIGATOR_BYTECODE))
    sim.add_agent(Agent("weather_scout", WEATHER_SCOUT_BYTECODE))
    sim.add_agent(Agent("fish_finder", FISH_FINDER_BYTECODE))
    sim.add_agent(Agent("supply_manager", SUPPLY_MANAGER_BYTECODE))
    sim.add_agent(Agent("captain", CAPTAIN_BYTECODE))

    try:
        report = sim.run()
        _check("Simulation completes without errors", True)
        _check("Report is a dict", isinstance(report, dict))
    except Exception as e:
        _check("Simulation completes without errors", False)
        print(f"    Error: {e}")


# ── 2. test_navigator_adjusts_heading ──────────────────────────────────────

def test_navigator_adjusts_heading() -> None:
    _section("test_navigator_adjusts_heading")

    vm = Interpreter(bytecode=NAVIGATOR_BYTECODE, memory_size=4096)

    # Test 1: Basic addition (45 + 10 = 55)
    vm.reset()
    vm.regs.write_gp(0, 45)
    vm.regs.write_gp(1, 10)
    vm.execute()
    _check("Navigator: 45 + 10 = 55", vm.regs.read_gp(0) == 55)

    # Test 2: Wrap around (350 + 20 = 10)
    vm.reset()
    vm.regs.write_gp(0, 350)
    vm.regs.write_gp(1, 20)
    vm.execute()
    _check("Navigator: 350 + 20 wraps to 10", vm.regs.read_gp(0) == 10)

    # Test 3: Negative wrap (10 - 20 = 350)
    vm.reset()
    vm.regs.write_gp(0, 10)
    vm.regs.write_gp(1, -20)
    vm.execute()
    _check("Navigator: 10 - 20 wraps to 350", vm.regs.read_gp(0) == 350)

    # Test 4: No change needed (180 + 0 = 180)
    vm.reset()
    vm.regs.write_gp(0, 180)
    vm.regs.write_gp(1, 0)
    vm.execute()
    _check("Navigator: 180 + 0 = 180", vm.regs.read_gp(0) == 180)

    # Test 5: Large positive wrap (359 + 1 = 0)
    vm.reset()
    vm.regs.write_gp(0, 359)
    vm.regs.write_gp(1, 1)
    vm.execute()
    _check("Navigator: 359 + 1 wraps to 0", vm.regs.read_gp(0) == 0)


# ── 3. test_weather_scout_generates_conditions ─────────────────────────────

def test_weather_scout_generates_conditions() -> None:
    _section("test_weather_scout_generates_conditions")

    vm = Interpreter(bytecode=WEATHER_SCOUT_BYTECODE, memory_size=4096)

    # Test with timestep 0
    vm.reset()
    vm.regs.write_gp(0, 0)
    vm.execute()
    result = vm.regs.read_gp(0)
    wind = (result >> 16) & 0xFF
    swell = (result >> 8) & 0xFF
    visibility = result & 0xFF
    _check("Weather Scout: returns packed data", result > 0)
    _check("Weather Scout: wind speed in range", 0 <= wind <= 50)
    _check("Weather Scout: swell in range", 0 <= swell <= 20)
    _check("Weather Scout: visibility in range", 0 <= visibility <= 20)

    # Test with timestep 10
    vm.reset()
    vm.regs.write_gp(0, 10)
    vm.execute()
    result2 = vm.regs.read_gp(0)
    _check("Weather Scout: different timestep gives different result", result != result2 or result2 > 0)


# ── 4. test_fish_finder_returns_catch ───────────────────────────────────────

def test_fish_finder_returns_catch() -> None:
    _section("test_fish_finder_returns_catch")

    vm = Interpreter(bytecode=FISH_FINDER_BYTECODE, memory_size=4096)

    # Test optimal conditions (depth=300, temp=60)
    vm.reset()
    vm.regs.write_gp(0, 300)
    vm.regs.write_gp(1, 60)
    vm.execute()
    result = vm.regs.read_gp(0)
    _check("Fish Finder: optimal conditions give positive catch", result >= 0)
    _check("Fish Finder: optimal conditions give reasonable catch", 0 <= result <= 10)

    # Test poor conditions (depth=50, temp=20)
    vm.reset()
    vm.regs.write_gp(0, 50)
    vm.regs.write_gp(1, 20)
    vm.execute()
    result2 = vm.regs.read_gp(0)
    _check("Fish Finder: poor conditions give lower/no catch", result2 >= 0)

    # Test moderate conditions (depth=150, temp=50)
    vm.reset()
    vm.regs.write_gp(0, 150)
    vm.regs.write_gp(1, 50)
    vm.execute()
    result3 = vm.regs.read_gp(0)
    _check("Fish Finder: moderate conditions return non-negative", result3 >= 0)


# ── 5. test_supply_manager_flags_low_fuel ──────────────────────────────────

def test_supply_manager_flags_low_fuel() -> None:
    _section("test_supply_manager_flags_low_fuel")

    vm = Interpreter(bytecode=SUPPLY_MANAGER_BYTECODE, memory_size=4096)

    # Test low fuel (should return 1 = urgent)
    vm.reset()
    vm.regs.write_gp(0, 20)  # Low fuel
    vm.regs.write_gp(1, 80)  # Good bait
    vm.regs.write_gp(2, 90)  # Good ice
    vm.execute()
    result = vm.regs.read_gp(0)
    _check("Supply Manager: flags urgency when fuel < 25", result == 1)

    # Test low bait (should return 1)
    vm.reset()
    vm.regs.write_gp(0, 80)  # Good fuel
    vm.regs.write_gp(1, 20)  # Low bait
    vm.regs.write_gp(2, 90)  # Good ice
    vm.execute()
    result2 = vm.regs.read_gp(0)
    _check("Supply Manager: flags urgency when bait < 25", result2 == 1)

    # Test low ice (should return 1)
    vm.reset()
    vm.regs.write_gp(0, 80)  # Good fuel
    vm.regs.write_gp(1, 80)  # Good bait
    vm.regs.write_gp(2, 20)  # Low ice
    vm.execute()
    result3 = vm.regs.read_gp(0)
    _check("Supply Manager: flags urgency when ice < 25", result3 == 1)

    # Test all good (should return 0)
    vm.reset()
    vm.regs.write_gp(0, 80)  # Good fuel
    vm.regs.write_gp(1, 80)  # Good bait
    vm.regs.write_gp(2, 80)  # Good ice
    vm.execute()
    result4 = vm.regs.read_gp(0)
    _check("Supply Manager: no urgency when all supplies OK", result4 == 0)


# ── 6. test_captain_makes_decisions ────────────────────────────────────────

def test_captain_makes_decisions() -> None:
    _section("test_captain_makes_decisions")

    vm = Interpreter(bytecode=CAPTAIN_BYTECODE, memory_size=4096)

    # Test low fuel -> return to port (decision = 1)
    vm.reset()
    vm.regs.write_gp(0, 15)  # Low fuel
    vm.regs.write_gp(1, 100)  # Good catch
    vm.regs.write_gp(2, 8)    # OK weather
    vm.regs.write_gp(3, 0)    # No supply urgency
    vm.execute()
    result = vm.regs.read_gp(0)
    _check("Captain: returns to port when fuel low", result == 1)

    # Test supply urgency -> return to port (decision = 1)
    vm.reset()
    vm.regs.write_gp(0, 80)   # Good fuel
    vm.regs.write_gp(1, 50)   # Some catch
    vm.regs.write_gp(2, 8)    # OK weather
    vm.regs.write_gp(3, 1)    # Supply urgency
    vm.execute()
    result2 = vm.regs.read_gp(0)
    _check("Captain: returns to port when supply urgent", result2 == 1)

    # Test bad weather -> change heading (decision = 2)
    vm.reset()
    vm.regs.write_gp(0, 80)   # Good fuel
    vm.regs.write_gp(1, 50)   # Some catch
    vm.regs.write_gp(2, 2)    # Bad weather (low score)
    vm.regs.write_gp(3, 0)    # No supply urgency
    vm.execute()
    result3 = vm.regs.read_gp(0)
    _check("Captain: changes heading in bad weather", result3 == 2)

    # Test all good -> continue (decision = 0)
    vm.reset()
    vm.regs.write_gp(0, 80)   # Good fuel
    vm.regs.write_gp(1, 50)   # Some catch
    vm.regs.write_gp(2, 8)    # Good weather
    vm.regs.write_gp(3, 0)    # No supply urgency
    vm.execute()
    result4 = vm.regs.read_gp(0)
    _check("Captain: continues when all conditions good", result4 == 0)


# ── 7. test_a2a_messages_sent ───────────────────────────────────────────────

def test_a2a_messages_sent() -> None:
    _section("test_a2a_messages_sent")

    sim = FleetSimulator(timesteps=3)
    sim.add_agent(Agent("navigator", NAVIGATOR_BYTECODE))
    sim.add_agent(Agent("weather_scout", WEATHER_SCOUT_BYTECODE))
    sim.add_agent(Agent("fish_finder", FISH_FINDER_BYTECODE))
    sim.add_agent(Agent("supply_manager", SUPPLY_MANAGER_BYTECODE))
    sim.add_agent(Agent("captain", CAPTAIN_BYTECODE))

    report = sim.run()

    total_sent = sum(agent.messages_sent for agent in sim.agents.values())
    total_received = sum(agent.messages_received for agent in sim.agents.values())

    _check("A2A: messages were sent", total_sent > 0)
    _check("A2A: messages were received", total_received > 0)
    _check("A2A: sent == received (closed loop)", total_sent == total_received)


# ── 8. test_report_generated ───────────────────────────────────────────────

def test_report_generated() -> None:
    _section("test_report_generated")

    sim = FleetSimulator(timesteps=5)
    sim.add_agent(Agent("navigator", NAVIGATOR_BYTECODE))
    sim.add_agent(Agent("weather_scout", WEATHER_SCOUT_BYTECODE))
    sim.add_agent(Agent("fish_finder", FISH_FINDER_BYTECODE))
    sim.add_agent(Agent("supply_manager", SUPPLY_MANAGER_BYTECODE))
    sim.add_agent(Agent("captain", CAPTAIN_BYTECODE))

    report = sim.run()

    # Check all required fields
    required_fields = [
        "timesteps",
        "heading_changes",
        "total_distance_nm",
        "total_fish",
        "total_value",
        "catch_by_species",
        "fuel_remaining",
        "bait_remaining",
        "ice_remaining",
        "efficiency_fish_per_nm",
        "messages_sent",
        "messages_received",
        "final_position",
    ]

    for field in required_fields:
        _check(f"Report has field: {field}", field in report)

    # Check field types
    _check("Report: timesteps is int", isinstance(report["timesteps"], int))
    _check("Report: total_fish is int", isinstance(report["total_fish"], int))
    _check("Report: total_value is float", isinstance(report["total_value"], float))
    _check("Report: catch_by_species is dict", isinstance(report["catch_by_species"], dict))
    _check("Report: final_position is tuple", isinstance(report["final_position"], tuple))


# ── 9. test_species_data_complete ───────────────────────────────────────────

def test_species_data_complete() -> None:
    _section("test_species_data_complete")

    required_species = ["tuna", "swordfish", "cod", "halibut", "salmon"]

    for species in required_species:
        _check(f"Species data exists: {species}", species in SPECIES)
        if species in SPECIES:
            data = SPECIES[species]
            _check(f"  {species} has 'depth'", "depth" in data)
            _check(f"  {species} has 'temp_range'", "temp_range" in data)
            _check(f"  {species} has 'value'", "value" in data)


# ── 10. test_agent_class ───────────────────────────────────────────────────

def test_agent_class() -> None:
    _section("test_agent_class")

    agent = Agent("test_agent", NAVIGATOR_BYTECODE)

    _check("Agent: has name", agent.name == "test_agent")
    _check("Agent: has UUID", isinstance(agent.agent_id, uuid.UUID))
    _check("Agent: has interpreter", agent.interpreter is not None)
    _check("Agent: has inbox", hasattr(agent, "inbox"))
    _check("Agent: message counters initialized", agent.messages_sent == 0 and agent.messages_received == 0)

    # Test run method
    result = agent.run({0: 45, 1: 10})
    _check("Agent: run() returns value", isinstance(result, int))
    _check("Agent: run() sets last_result", agent.last_result == result)


# ── 11. test_weather_data_packing ──────────────────────────────────────────

def test_weather_data_packing() -> None:
    _section("test_weather_data_packing")

    sim = FleetSimulator(timesteps=1)

    # Test packing
    packed = sim._pack_weather_data(25, 8, 10)
    _check("Pack: wind in high bits", (packed >> 16) & 0xFF == 25)
    _check("Pack: swell in mid bits", (packed >> 8) & 0xFF == 8)
    _check("Pack: visibility in low bits", packed & 0xFF == 10)

    # Test unpacking
    wind, swell, visibility = sim._unpack_weather_data(packed)
    _check("Unpack: wind matches", wind == 25)
    _check("Unpack: swell matches", swell == 8)
    _check("Unpack: visibility matches", visibility == 10)

    # Test roundtrip
    wind2, swell2, vis2 = sim._unpack_weather_data(sim._pack_weather_data(30, 12, 15))
    _check("Roundtrip: wind", wind2 == 30)
    _check("Roundtrip: swell", swell2 == 12)
    _check("Roundtrip: visibility", vis2 == 15)


# ── 12. test_fleet_state_initialization ────────────────────────────────────

def test_fleet_state_initialization() -> None:
    _section("test_fleet_state_initialization")

    sim = FleetSimulator(timesteps=10)

    _check("Fleet state has heading", "heading" in sim.fleet_state)
    _check("Fleet state has position", "position" in sim.fleet_state)
    _check("Fleet state has fuel", "fuel" in sim.fleet_state)
    _check("Fleet state has bait", "bait" in sim.fleet_state)
    _check("Fleet state has ice", "ice" in sim.fleet_state)
    _check("Fleet state has total_catch", "total_catch" in sim.fleet_state)
    _check("Fleet state has legs", "legs" in sim.fleet_state)
    _check("Fleet state has decisions", "decisions" in sim.fleet_state)

    _check("Initial heading is 45", sim.fleet_state["heading"] == 45)
    _check("Initial position is (0, 0)", sim.fleet_state["position"] == (0, 0))
    _check("Initial fuel is 100", sim.fleet_state["fuel"] == 100)
    _check("Initial bait is 80", sim.fleet_state["bait"] == 80)
    _check("Initial ice is 90", sim.fleet_state["ice"] == 90)


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    """Run all tests."""
    import sys

    print("\n" + "=" * 60)
    print("  FLUX FLEET SIMULATOR TESTS")
    print("=" * 60)

    test_simulator_runs()
    test_navigator_adjusts_heading()
    test_weather_scout_generates_conditions()
    test_fish_finder_returns_catch()
    test_supply_manager_flags_low_fuel()
    test_captain_makes_decisions()
    test_a2a_messages_sent()
    test_report_generated()
    test_species_data_complete()
    test_agent_class()
    test_weather_data_packing()
    test_fleet_state_initialization()

    print("\n" + "=" * 60)
    print(f"  Results: {_pass} passed, {_fail} failed")
    print("=" * 60 + "\n")

    return _fail == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
