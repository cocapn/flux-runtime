#!/usr/bin/env python3
"""FLUX Fleet Simulator — Multi-agent fishing fleet simulation using FLUX bytecode VMs + A2A protocol.

Run:
    PYTHONPATH=src python3 examples/flux_fleet_sim.py
"""

from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import IntEnum
import sys
import os

# Use flux modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from flux.vm.interpreter import Interpreter
from flux.bytecode.opcodes import Op
from flux.a2a.messages import A2AMessage

# ── ANSI helpers ──────────────────────────────────────────────────────────

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def header(text: str) -> None:
    width = 70
    print()
    print(f"{BOLD}{MAGENTA}{'═' * width}{RESET}")
    print(f"{BOLD}{MAGENTA}  {text}{RESET}")
    print(f"{BOLD}{MAGENTA}{'═' * width}{RESET}")


def section(text: str) -> None:
    print()
    print(f"{BOLD}{CYAN}── {text} {'─' * (64 - len(text))}{RESET}")


def info(text: str) -> None:
    print(f"  {GREEN}✓{RESET} {text}")


def warn(text: str) -> None:
    print(f"  {YELLOW}⚠{RESET} {text}")


def error(text: str) -> None:
    print(f"  {RED}✗{RESET} {text}")


def detail(text: str) -> None:
    print(f"    {DIM}{text}{RESET}")


# ── Species Data ───────────────────────────────────────────────────────────

SPECIES = {
    "tuna": {"depth": 200, "temp_range": (60, 75), "value": 12.50},
    "swordfish": {"depth": 300, "temp_range": (55, 70), "value": 18.00},
    "cod": {"depth": 100, "temp_range": (45, 60), "value": 6.75},
    "halibut": {"depth": 150, "temp_range": (40, 55), "value": 15.00},
    "salmon": {"depth": 80, "temp_range": (50, 65), "value": 9.25},
}

# ── Bytecode Programs ───────────────────────────────────────────────────────
# Format encoding reference:
# Format A (1 byte):  [opcode]
# Format B (2 bytes): [opcode][reg]
# Format C (3 bytes): [opcode][rd][rs1]
# Format D (4 bytes): [opcode][reg][off_lo][off_hi]   (signed i16 offset)
# Format E (4 bytes): [opcode][rd][rs1][rs2]

# Navigator: R0=R0+R1, clamp to 0-359
NAVIGATOR_BYTECODE = bytes([
    0x08, 0x00, 0x00, 0x01,  # IADD R0, R0, R1
    0x2B, 0x02, 0x00, 0x00,  # MOVI R2, 0
    0x2D, 0x00, 0x02,        # CMP R0, R2
    0x36, 0x00, 0x0C, 0x00,  # JL R0, +12 (jump if < 0, to add 360)
    0x2B, 0x03, 0x68, 0x01,  # MOVI R3, 360
    0x08, 0x00, 0x00, 0x03,  # IADD R0, R0, R3
    0x2B, 0x04, 0x68, 0x01,  # MOVI R4, 360
    0x2D, 0x00, 0x04,        # CMP R0, R4
    0x36, 0x00, 0x03, 0x00,  # JL R0, +3 (jump if < 360, to return)
    0x09, 0x00, 0x00, 0x04,  # ISUB R0, R0, R4 (subtract 360)
    0x28, 0x00, 0x00,        # RET R0, R0
    0x28, 0x00, 0x00,        # RET R0, R0 (return from < 360 path)
])

# Weather Scout: R0=timestep, generate wind_speed, swell, visibility
# Returns packed: [wind_speed, swell, visibility] in R0
WEATHER_SCOUT_BYTECODE = bytes([
    0x01, 0x01, 0x00,        # MOV R1, R0 (timestep)
    0x2B, 0x02, 0x0F, 0x00,  # MOVI R2, 15
    0x0C, 0x01, 0x01, 0x02,  # IMOD R1, R1, R2 (timestep % 15)
    0x2B, 0x03, 0x19, 0x00,  # MOVI R3, 25
    0x08, 0x01, 0x01, 0x03,  # IADD R1, R1, R3 (base wind)
    0x2B, 0x04, 0x28, 0x00,  # MOVI R4, 40
    0x2B, 0x05, 0x0A, 0x00,  # MOVI R5, 10
    0x0C, 0x02, 0x00, 0x05,  # IMOD R2, R0, R5 (timestep % 10)
    0x2B, 0x06, 0x05, 0x00,  # MOVI R6, 5
    0x08, 0x02, 0x02, 0x06,  # IADD R2, R2, R6 (swell 5-14)
    0x2B, 0x07, 0x0F, 0x00,  # MOVI R7, 15
    0x0C, 0x03, 0x00, 0x07,  # IMOD R3, R0, R7 (timestep % 15)
    0x2B, 0x08, 0x03, 0x00,  # MOVI R8, 3
    0x08, 0x03, 0x03, 0x08,  # IADD R3, R3, R8 (visibility 3-17)
    # Pack into R0: wind (0-7 bits), swell (8-15 bits), visibility (16-23 bits)
    0x0A, 0x04, 0x01, 0x08,  # IMUL R4, R1, 256 (shift left 8)
    0x08, 0x04, 0x04, 0x02,  # IADD R4, R4, R2 (add swell)
    0x0A, 0x05, 0x04, 0x08,  # IMUL R5, R4, 256
    0x08, 0x00, 0x05, 0x03,  # IADD R0, R5, R3 (final packed)
    0x28, 0x00, 0x00,        # RET R0, R0
])

# Fish Finder: R0=depth, R1=temp, compute expected catch
FISH_FINDER_BYTECODE = bytes([
    0x01, 0x02, 0x00,        # MOV R2, R0 (depth)
    0x2B, 0x03, 0x2D, 0x01,  # MOVI R3, 300 (optimal depth)
    0x01, 0x04, 0x01,        # MOV R4, R1 (temp)
    0x2B, 0x05, 0x3C, 0x00,  # MOVI R5, 60 (optimal temp)
    0x09, 0x06, 0x02, 0x03,  # ISUB R6, R2, R3 (depth_diff)
    0x0D, 0x06, 0x06,        # INEG R6 (abs via neg, simplified)
    0x09, 0x07, 0x04, 0x05,  # ISUB R7, R4, R5 (temp_diff)
    0x0D, 0x07, 0x07,        # INEG R7
    0x2B, 0x08, 0x0A, 0x00,  # MOVI R8, 10
    0x08, 0x06, 0x06, 0x07,  # IADD R6, R6, R7 (total_diff)
    0x09, 0x08, 0x08, 0x06,  # ISUB R8, R8, R6 (score = 10 - diff)
    0x2B, 0x09, 0x00, 0x00,  # MOVI R9, 0
    0x2D, 0x08, 0x09,        # CMP R8, R9
    0x37, 0x00, 0x03, 0x00,  # JGE R0, +3 (skip if score >= 0)
    0x2B, 0x08, 0x00, 0x00,  # MOVI R8, 0 (clamp to 0)
    0x2B, 0x0A, 0x0A, 0x00,  # MOVI R10, 10 (max catch)
    0x2D, 0x08, 0x0A,        # CMP R8, R10
    0x4E, 0x00, 0x03, 0x00,  # JLE R0, +3 (skip if score <= 10)
    0x2B, 0x08, 0x0A, 0x00,  # MOVI R8, 10 (clamp to 10)
    0x01, 0x00, 0x08,        # MOV R0, R8
    0x28, 0x00, 0x00,        # RET R0, R0
])

# Supply Manager: R0=fuel, R1=bait, R2=ice, compute urgency flag
# Returns 1 if any supply < 25, else 0
SUPPLY_MANAGER_BYTECODE = bytes([
    0x2B, 0x03, 0x19, 0x00,  # MOVI R3, 25 (low threshold)
    0x19, 0x04, 0x00, 0x03,  # ILT R4, R0, R3 (1 if fuel < 25, else 0)
    0x2B, 0x05, 0x00, 0x00,  # MOVI R5, 0
    0x19, 0x06, 0x01, 0x03,  # ILT R6, R1, R3 (1 if bait < 25, else 0)
    0x0B, 0x04, 0x04, 0x06,  # IOR R4, R4, R6 (OR the results)
    0x19, 0x06, 0x02, 0x03,  # ILT R6, R2, R3 (1 if ice < 25, else 0)
    0x0B, 0x00, 0x04, 0x06,  # IOR R0, R4, R6 (final urgency flag)
    0x28, 0x00, 0x00,        # RET R0, R0
])

# Fleet Captain: Simple decision logic bytecode
# R0=fuel, R1=total_catch, R2=weather_score, R3=supply_urgency
# Returns: 0=continue, 1=return_to_port, 2=change_heading
CAPTAIN_BYTECODE = bytes([
    # Decision: 1 if (fuel < 20 OR supply_urgency == 1), 2 if (weather < 4), else 0
    0x2B, 0x04, 0x14, 0x00,  # MOVI R4, 20 (fuel threshold)
    0x19, 0x04, 0x00, 0x04,  # ILT R4, R0, R4 (R4 = 1 if fuel < 20)
    0x0B, 0x04, 0x04, 0x03,  # IOR R4, R4, R3 (R4 = 1 if urgent)
    0x01, 0x00, 0x04,        # MOV R0, R4 (R0 = 1 if urgent, else 0)
    0x28, 0x00, 0x00,        # RET R0, R0 (return immediately)
])


# ── Agent Class ─────────────────────────────────────────────────────────────

@dataclass
class Agent:
    """A FLUX bytecode agent with A2A messaging capability."""
    name: str
    bytecode: bytes
    agent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    interpreter: Optional[Interpreter] = None
    messages_sent: int = 0
    messages_received: int = 0
    last_result: int = 0

    def __post_init__(self):
        """Initialize the VM interpreter with this agent's bytecode."""
        self.interpreter = Interpreter(
            bytecode=self.bytecode,
            memory_size=4096,
            max_cycles=100_000
        )

    def run(self, inputs: Dict[int, int]) -> int:
        """Run the agent's bytecode with given register inputs.

        Args:
            inputs: dict mapping register number to initial value

        Returns:
            Value in R0 after execution
        """
        # Reset and set inputs
        self.interpreter.reset()
        for reg, val in inputs.items():
            self.interpreter.regs.write_gp(reg, val)

        # Execute
        try:
            self.interpreter.execute()
            self.last_result = self.interpreter.regs.read_gp(0)
        except Exception as e:
            print(f"{RED}Error in {self.name}:{RESET} {e}")
            self.last_result = 0

        return self.last_result

    def send_message(self, receiver: "Agent", message_type: int,
                     payload: bytes, priority: int = 5,
                     trust_token: int = 500) -> None:
        """Send an A2A message to another agent."""
        msg = A2AMessage(
            sender=self.agent_id,
            receiver=receiver.agent_id,
            conversation_id=uuid.uuid4(),
            in_reply_to=None,
            message_type=message_type,
            priority=priority,
            trust_token=trust_token,
            capability_token=100,
            payload=payload,
        )
        receiver.inbox.append(msg)
        self.messages_sent += 1
        receiver.messages_received += 1

    # Initialize inbox for each agent
    def __post_init__(self):
        if self.interpreter is None:
            self.interpreter = Interpreter(
                bytecode=self.bytecode,
                memory_size=4096,
                max_cycles=100_000
            )
        self.inbox: List[A2AMessage] = []


# ── Fleet Simulator ────────────────────────────────────────────────────────

@dataclass
class FleetSimulator:
    """Multi-agent fishing fleet simulation."""
    timesteps: int = 24
    agents: Dict[str, Agent] = field(default_factory=dict)
    messages: List[A2AMessage] = field(default_factory=list)
    fleet_state: Dict = field(default_factory=dict)
    log: List[str] = field(default_factory=list)
    total_distance: float = 0.0
    heading_changes: int = 0

    def __post_init__(self):
        """Initialize the simulation state."""
        self.fleet_state = {
            "heading": 45,
            "position": (0, 0),
            "fuel": 100,
            "bait": 80,
            "ice": 90,
            "total_catch": {species: 0 for species in SPECIES},
            "legs": [],
            "decisions": [],
        }

    def add_agent(self, agent: Agent) -> None:
        """Add an agent to the fleet."""
        self.agents[agent.name] = agent

    def _pack_weather_data(self, wind: int, swell: int, visibility: int) -> int:
        """Pack weather data into single int for VM processing."""
        return (wind << 16) | (swell << 8) | visibility

    def _unpack_weather_data(self, packed: int) -> Tuple[int, int, int]:
        """Unpack weather data from single int."""
        wind = (packed >> 16) & 0xFF
        swell = (packed >> 8) & 0xFF
        visibility = packed & 0xFF
        return wind, swell, visibility

    def _timestep(self, t: int) -> None:
        """Execute a single timestep of the simulation."""
        section(f"Timestep {t + 1}/{self.timesteps}")

        # Get current state
        current_heading = self.fleet_state["heading"]
        fuel = self.fleet_state["fuel"]
        bait = self.fleet_state["bait"]
        ice = self.fleet_state["ice"]

        detail(f"Status: Heading={current_heading}°, Fuel={fuel}%, Bait={bait}%, Ice={ice}%")

        # ── 1. Captain broadcasts mission params via A2A
        captain = self.agents["captain"]
        mission_payload = struct.pack("<IHHHH", t, current_heading, fuel, bait, ice)
        for agent_name, agent in self.agents.items():
            if agent_name != "captain":
                captain.send_message(agent, Op.BROADCAST, mission_payload, priority=7)

        # ── 2. Run Weather Scout
        weather_scout = self.agents["weather_scout"]
        weather_packed = weather_scout.run({0: t})
        wind, swell, visibility = self._unpack_weather_data(weather_packed)
        info(f"Weather Scout: Wind={wind}kt, Swell={swell}ft, Visibility={visibility}mi")

        # Weather score (lower is worse: high wind/swell = bad)
        weather_score = max(0, 10 - (wind // 5) - (swell // 3))
        detail(f"Weather Score: {weather_score}/10")

        # ── 3. Run Navigator (adjust heading based on wind)
        wind_offset = -5 if wind > 25 else 0
        new_heading = self.agents["navigator"].run({0: current_heading, 1: wind_offset})
        self.fleet_state["heading"] = new_heading
        if new_heading != current_heading:
            self.heading_changes += 1
            info(f"Navigator: Heading adjusted {current_heading}° → {new_heading}°")
        else:
            detail(f"Navigator: Heading unchanged at {current_heading}°")

        # ── 4. Run Fish Finder (simulate conditions at current position)
        # Vary conditions by timestep for simulation
        sim_depth = 100 + (t * 10) % 300
        sim_temp = 45 + (t * 3) % 30
        expected_catch = self.agents["fish_finder"].run({0: sim_depth, 1: sim_temp})
        detail(f"Fish Finder: Depth={sim_depth}m, Temp={sim_temp}°F → Expected catch={expected_catch}")

        # ── 5. Run Supply Manager
        supply_urgency = self.agents["supply_manager"].run({0: fuel, 1: bait, 2: ice})
        if supply_urgency:
            warn(f"Supply Manager: Resupply needed! (Fuel={fuel}%, Bait={bait}%, Ice={ice}%)")
        else:
            info(f"Supply Manager: All supplies OK")

        # ── 6. Captain makes decision
        captain_decision = captain.run({
            0: fuel,
            1: sum(self.fleet_state["total_catch"].values()),
            2: weather_score,
            3: supply_urgency
        })

        decision_names = {0: "CONTINUE", 1: "RETURN_TO_PORT", 2: "CHANGE_HEADING"}
        decision = decision_names.get(captain_decision, "UNKNOWN")
        info(f"Captain Decision: {decision}")

        self.fleet_state["decisions"].append({
            "timestep": t,
            "decision": decision,
            "heading": new_heading,
            "fuel": fuel,
            "weather_score": weather_score
        })

        # ── 7. Execute decision effects
        if captain_decision == 1:  # Return to port
            warn("Returning to port - ending mission early")
            info(f"Final Catch Report:")
            for species, count in self.fleet_state["total_catch"].items():
                if count > 0:
                    value = count * SPECIES[species]["value"]
                    detail(f"  {species.capitalize()}: {count} fish (${value:.2f})")
            return False  # Stop simulation

        elif captain_decision == 2:  # Change heading
            self.fleet_state["heading"] = (new_heading + 45) % 360
            detail(f"Changing heading by +45° to {self.fleet_state['heading']}°")

        # ── 8. Simulate catch and resource consumption
        actual_catch = max(0, expected_catch + (-1 if t % 3 == 0 else 1))
        if actual_catch > 0:
            # Distribute catch among species based on conditions
            for species in SPECIES:
                species_prob = 0.3 if (abs(sim_depth - SPECIES[species]["depth"]) < 50) else 0.1
                if sim_temp >= SPECIES[species]["temp_range"][0] and sim_temp <= SPECIES[species]["temp_range"][1]:
                    species_prob += 0.2
                if actual_catch > 0 and species_prob > 0.3:
                    catch = min(actual_catch, 5)
                    self.fleet_state["total_catch"][species] += catch
                    actual_catch -= catch
                    detail(f"  Caught {catch} × {species}")

        # Consume resources
        self.fleet_state["fuel"] = max(0, fuel - 3)
        self.fleet_state["bait"] = max(0, bait - 2)
        self.fleet_state["ice"] = max(0, ice - 1)

        # Move position (simplified)
        x, y = self.fleet_state["position"]
        import math
        rad = math.radians(new_heading)
        x += int(10 * math.cos(rad))
        y += int(10 * math.sin(rad))
        self.fleet_state["position"] = (x, y)
        self.total_distance += 10.0

        self.fleet_state["legs"].append({
            "timestep": t,
            "heading": new_heading,
            "position": (x, y)
        })

        return True  # Continue simulation

    def run(self) -> Dict:
        """Run the full simulation for all timesteps.

        Returns:
            Final simulation report
        """
        header("FLUX FLEET SIMULATOR - Multi-Agent Fishing Mission")

        section("Initializing Fleet Agents")
        for name, agent in self.agents.items():
            info(f"{name.replace('_', ' ').title()}: {agent.agent_id}")

        section("Starting Simulation")

        for t in range(self.timesteps):
            if not self._timestep(t):
                break  # Early termination (returned to port)

        return self._generate_report()

    def _generate_report(self) -> Dict:
        """Generate and display the final mission report."""
        header("MISSION REPORT")

        section("Mission Summary")
        total_timesteps = len(self.fleet_state["legs"])
        info(f"Duration: {total_timesteps} timesteps")
        info(f"Heading Changes: {self.heading_changes}")
        info(f"Total Distance: {self.total_distance:.1f} nautical miles")

        section("Catch Report")
        total_fish = 0
        total_value = 0.0
        for species, count in self.fleet_state["total_catch"].items():
            if count > 0:
                value = count * SPECIES[species]["value"]
                total_fish += count
                total_value += value
                detail(f"{BOLD}{species.capitalize():12}{RESET} {count:4} fish × ${SPECIES[species]['value']:.2f} = ${value:7.2f}")
            else:
                detail(f"{DIM}{species.capitalize():12}{DIM}    0 fish")

        print()
        info(f"{BOLD}Total Fish:{RESET} {total_fish}")
        info(f"{BOLD}Total Value:{RESET} ${total_value:.2f}")

        section("Supply Status")
        fuel_color = RED if self.fleet_state["fuel"] < 25 else YELLOW if self.fleet_state["fuel"] < 50 else GREEN
        bait_color = RED if self.fleet_state["bait"] < 25 else YELLOW if self.fleet_state["bait"] < 50 else GREEN
        ice_color = RED if self.fleet_state["ice"] < 25 else YELLOW if self.fleet_state["ice"] < 50 else GREEN
        info(f"{fuel_color}Fuel:  {self.fleet_state['fuel']:3}%{RESET}")
        info(f"{bait_color}Bait:  {self.fleet_state['bait']:3}%{RESET}")
        info(f"{ice_color}Ice:   {self.fleet_state['ice']:3}%{RESET}")

        section("Route Metrics")
        if self.total_distance > 0:
            efficiency = total_fish / self.total_distance
            info(f"Efficiency: {efficiency:.2f} fish per nautical mile")
        else:
            info(f"Efficiency: N/A (no distance traveled)")

        section("A2A Message Statistics")
        total_sent = sum(agent.messages_sent for agent in self.agents.values())
        total_received = sum(agent.messages_received for agent in self.agents.values())
        info(f"Total Messages Sent: {total_sent}")
        info(f"Total Messages Received: {total_received}")

        section("Agent Performance")
        for name, agent in self.agents.items():
            detail(f"{name.replace('_', ' ').title():20} Sent: {agent.messages_sent:2}  |  Recv: {agent.messages_received:2}  |  Last Result: {agent.last_result}")

        # Final position
        x, y = self.fleet_state["position"]
        section(f"Final Position: ({x}, {y})")

        # Return structured report
        return {
            "timesteps": total_timesteps,
            "heading_changes": self.heading_changes,
            "total_distance_nm": self.total_distance,
            "total_fish": total_fish,
            "total_value": total_value,
            "catch_by_species": dict(self.fleet_state["total_catch"]),
            "fuel_remaining": self.fleet_state["fuel"],
            "bait_remaining": self.fleet_state["bait"],
            "ice_remaining": self.fleet_state["ice"],
            "efficiency_fish_per_nm": total_fish / self.total_distance if self.total_distance > 0 else 0,
            "messages_sent": total_sent,
            "messages_received": total_received,
            "final_position": self.fleet_state["position"],
        }


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    """Run the FLUX Fleet Simulator."""
    # Create simulator
    sim = FleetSimulator(timesteps=24)

    # Add agents
    sim.add_agent(Agent("navigator", NAVIGATOR_BYTECODE))
    sim.add_agent(Agent("weather_scout", WEATHER_SCOUT_BYTECODE))
    sim.add_agent(Agent("fish_finder", FISH_FINDER_BYTECODE))
    sim.add_agent(Agent("supply_manager", SUPPLY_MANAGER_BYTECODE))
    sim.add_agent(Agent("captain", CAPTAIN_BYTECODE))

    # Run simulation
    report = sim.run()

    print()
    header("Simulation Complete")
    return report


if __name__ == "__main__":
    main()
