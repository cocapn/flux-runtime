"""Text Adventure engine — FLUX bytecode + Python hybrid.

Five rooms connected in a simple map.  The bytecode validates exit
directions using bit-mask operations.  Python handles all game state,
command parsing, and I/O.

Register layout (bytecode exit-validator)
-----------------------------------------
    R3  direction bit (1<<dir_idx, set by Python)
    R5  exit_flags   (loaded from memory by bytecode)
    R6  result       (0 = blocked, 1 = allowed)
    R7  grid_base    (0x5000)
    R8  room_idx     (set by Python)
"""

from __future__ import annotations

from flux.bytecode.opcodes import Op
from flux.vm.interpreter import Interpreter
from ._asm import Assembler


# ── Room definitions ─────────────────────────────────────────────────────

ROOMS = [
    {
        "name": "Entrance Hall",
        "desc": "A grand hall with marble floors. Exits lead north and east.",
        "exits": {"north": 1, "east": 2},
        "items": ["torch"],
    },
    {
        "name": "Library",
        "desc": "Towering bookshelves line the walls. Exits lead south and east.",
        "exits": {"south": 0, "east": 3},
        "items": ["old_key"],
    },
    {
        "name": "Kitchen",
        "desc": "A dusty kitchen with a broken stove. Exits lead west and north.",
        "exits": {"west": 0, "north": 4},
        "items": ["bread"],
    },
    {
        "name": "Tower Room",
        "desc": "A circular stone room at the top of a tower. Exit south.",
        "exits": {"south": 1},
        "items": ["crystal"],
    },
    {
        "name": "Garden",
        "desc": "An overgrown garden with a rusted gate. Exit south.",
        "exits": {"south": 2},
        "items": ["flower"],
    },
]

DIR_BITS = {"north": 1, "south": 2, "east": 4, "west": 8}
DIR_NAMES = ["north", "south", "east", "west"]


class TextAdventure:
    """Text adventure with bytecode exit-validation engine."""

    # Registers used by the bytecode
    DIR_BIT = 3
    EXIT_FLAGS = 5
    RESULT = 6
    TABLE_BASE = 7
    ROOM_IDX = 8

    MEM_BASE = 0x5000

    @classmethod
    def build_bytecode(cls) -> bytes:
        """Build the exit-validation bytecode.

        Expects:
          R7 = table_base (0x5000)
          R8 = room_idx
          R3 = direction bit (1 << dir_index)

        The bytecode:
          1. Loads exit_flags from memory[TABLE_BASE + ROOM_IDX * 4]
          2. Computes EXIT_FLAGS & DIR_BIT
          3. Sets RESULT = 1 if non-zero, else 0

        This demonstrates LOAD, IAND, CMP, conditional MOV in bytecode.
        """
        a = Assembler()

        # Load exit_flags for current room
        # addr = TABLE_BASE + ROOM_IDX * 4
        a.movi(cls.TABLE_BASE, 0x5000)
        a.mov(cls.EXIT_FLAGS, cls.ROOM_IDX)
        a.movi(cls.RESULT, 4)
        a.imul(cls.EXIT_FLAGS, cls.EXIT_FLAGS, cls.RESULT)  # *4
        a.iadd(cls.EXIT_FLAGS, cls.EXIT_FLAGS, cls.TABLE_BASE)
        a.load(cls.EXIT_FLAGS, cls.EXIT_FLAGS)              # load flags from memory

        # Test: exit_flags & dir_bit
        a.iand(cls.RESULT, cls.EXIT_FLAGS, cls.DIR_BIT)

        # RESULT = (RESULT != 0) ? 1 : 0
        a.movi(cls.EXIT_FLAGS, 0)
        a.cmp(cls.RESULT, cls.EXIT_FLAGS)
        a.je("blocked")
        a.movi(cls.RESULT, 1)
        a.jmp("done")
        a.label("blocked")
        a.movi(cls.RESULT, 0)
        a.label("done")

        a.halt()
        return a.to_bytes()

    @classmethod
    def _init_room_data(cls, vm: Interpreter) -> None:
        """Write room exit flags into heap memory (one i32 per room)."""
        stack = vm.memory.get_region("stack")
        base = cls.MEM_BASE
        for i, room in enumerate(ROOMS):
            flags = 0
            for d in room["exits"]:
                flags |= DIR_BITS[d]
            stack.write_i32(base + i * 4, flags)

    @classmethod
    def _check_exit(cls, vm: Interpreter, room_idx: int,
                    direction: str) -> bool:
        """Run bytecode to validate an exit direction."""
        dir_idx = DIR_NAMES.index(direction)
        dir_bit = 1 << dir_idx

        # Set up registers (without re-running init bytecode)
        vm.regs.write_gp(cls.TABLE_BASE, cls.MEM_BASE)
        vm.regs.write_gp(cls.ROOM_IDX, room_idx)
        vm.regs.write_gp(cls.DIR_BIT, dir_bit)

        vm.pc = 0
        vm.halted = False
        vm.running = False
        vm._flag_zero = False
        vm._flag_sign = False
        vm._flag_carry = False
        vm._flag_overflow = False
        vm.execute()

        return vm.regs.read_gp(cls.RESULT) == 1

    # ── Demonstrate ─────────────────────────────────────────────────────

    @classmethod
    def demonstrate(cls) -> None:
        """Run an automated text adventure tour."""
        bytecode = cls.build_bytecode()
        vm = Interpreter(bytecode, memory_size=65536)
        cls._init_room_data(vm)

        # Run once to verify bytecode works
        vm.execute()

        print("=" * 64)
        print("  FLUX BYTECODE TEXT ADVENTURE  —  5-room dungeon")
        print("=" * 64)
        print(f"  Bytecode size: {len(bytecode)} bytes")
        print(f"  Rooms: {len(ROOMS)}")

        # Game state managed by Python
        current_room = 0
        inventory: list[str] = []

        def look():
            room = ROOMS[current_room]
            print(f"\n  [{room['name']}]")
            print(f"  {room['desc']}")
            exits = ", ".join(room["exits"].keys())
            print(f"  Exits: {exits}")
            if room["items"]:
                print(f"  You see: {', '.join(room['items'])}")

        def go(direction: str):
            nonlocal current_room
            room = ROOMS[current_room]

            # Validate exit using BYTECODE
            allowed = cls._check_exit(vm, current_room, direction)

            if not allowed:
                print(f"\n  You can't go {direction}.")
                return

            current_room = room["exits"][direction]
            new_room = ROOMS[current_room]
            print(f"\n  You go {direction}.")
            print(f"  [{new_room['name']}]")
            print(f"  {new_room['desc']}")
            exits = ", ".join(new_room["exits"].keys())
            print(f"  Exits: {exits}")
            if new_room["items"]:
                print(f"  You see: {', '.join(new_room['items'])}")

        def take(item_name: str):
            room = ROOMS[current_room]
            if item_name in room["items"]:
                room["items"].remove(item_name)
                inventory.append(item_name)
                print(f"\n  You take the {item_name}.")
            else:
                print(f"\n  There is no {item_name} here.")

        def show_inventory():
            if inventory:
                print(f"\n  Inventory: {', '.join(inventory)}")
            else:
                print(f"\n  Inventory: (empty)")

        # ── Automated tour ──────────────────────────────────────────────
        print("\n  --- Automated Tour ---")

        commands = [
            ("look", []),
            ("go", ["north"]),
            ("go", ["east"]),
            ("take", ["crystal"]),
            ("go", ["south"]),
            ("take", ["old_key"]),
            ("go", ["south"]),
            ("take", ["torch"]),
            ("go", ["east"]),
            ("take", ["bread"]),
            ("go", ["north"]),
            ("take", ["flower"]),
            ("go", ["south"]),
            ("go", ["west"]),
            ("inventory", []),
            ("look", []),
        ]

        for cmd, args in commands:
            if cmd == "look":
                look()
            elif cmd == "go":
                go(args[0])
            elif cmd == "take":
                take(args[0])
            elif cmd == "inventory":
                show_inventory()

        print(f"\n  --- Tour Complete ---")
        print(f"  Final room: {ROOMS[current_room]['name']}")
        print(f"  Items collected: {len(inventory)}")
        print(f"  Inventory: {', '.join(inventory) if inventory else '(empty)'}")

        # Verify bytecode exit check for all rooms/directions
        print(f"\n  --- Bytecode Exit Validation Verification ---")
        for i, room in enumerate(ROOMS):
            valid = []
            for d in DIR_NAMES:
                if cls._check_exit(vm, i, d):
                    valid.append(d)
            expected = sorted(room["exits"].keys())
            match = "OK" if sorted(valid) == expected else f"MISMATCH (got {valid})"
            print(f"  Room {i} ({room['name']}): exits={valid} {match}")

        gp = vm.regs.snapshot()["gp"]
        print(f"\n  Registers: {' '.join(f'R{i}={gp[i]}' for i in range(9))}")
        print()


if __name__ == "__main__":
    TextAdventure.demonstrate()
