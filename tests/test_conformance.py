"""
FLUX Conformance Test Suite — Bytecode test vectors all VMs must pass.

WHY THIS EXISTS:
The fleet has 8+ FLUX VM implementations (Rust, Zig, JS, Python, C, Java, CUDA,
WASM). They all claim to implement the same ISA (flux-spec/ISA.md, 247 opcodes).
But there's no way to verify they actually behave identically.

This test suite provides canonical test vectors — bytecodes with expected
results. Any FLUX VM that passes all tests is ISA-conformant. Any failure
indicates an ISA divergence that needs resolution.

COOPERATION PATTERN: Audit and Converge.
This is the cartographer pattern — measuring the fleet's alignment and
identifying divergences. Without conformance tests, parallel divergence
becomes permanent fragmentation.

DESIGN PRINCIPLES:
1. Language-agnostic — tests are defined as bytecode + expected result,
   not as source code in any specific language.
2. Minimal — each test is one opcode or one simple program.
3. Complete — covers all opcode categories and edge cases.
4. Self-documenting — each test has a name explaining what it verifies.

HOW TO USE:
Each test is a dict with:
  - name: human-readable description
  - bytecode: list of ints (the program)
  - expected: expected result or condition
  - category: which opcode category this tests

A VM runner executes the bytecode and checks the expected result.
See the runner template at the bottom of this file.

Author: Super Z (Cartographer)
Date: 2026-04-12
Status: DRAFT — Phase 1 (basic arithmetic + control flow + memory)
"""

# ===========================================================================
# Test Vectors
# ===========================================================================

# Each test is a dictionary:
# {
#     "name": "What this test verifies",
#     "bytecode": [opcode, ...],  # The program
#     "expected": ...,             # Expected result
#     "category": "arithmetic",    # Opcode category
#     "notes": "Why this matters", # Optional reasoning
# }

TEST_VECTORS = [
    # =========================================================================
    # Category: System Control (0x00-0x07)
    # =========================================================================
    {
        "name": "NOP does nothing",
        "bytecode": [0x01, 0x00],  # NOP, HALT
        "expected": "no_crash",
        "category": "control",
        "notes": "NOP (0x01) should execute without modifying any state. The VM should reach HALT normally.",
    },
    {
        "name": "HALT terminates execution",
        "bytecode": [0x00],  # HALT
        "expected": "no_crash",
        "category": "control",
        "notes": "HALT (0x00) should stop the VM immediately. No registers modified.",
    },

    # =========================================================================
    # Category: Data Movement
    # =========================================================================
    {
        "name": "MOVI loads immediate value",
        "bytecode": [0x18, 0, 42, 0x00],  # MOVI R0, 42; HALT
        "expected": {"register": 0, "value": 42},
        "category": "data",
        "notes": "MOVI (0x18) Format D: opcode, rd, imm8. Should set R0 = 42. Verifies immediate loading.",
    },
    {
        "name": "MOVI loads negative value",
        "bytecode": [0x18, 0, 0x80, 0x00],  # MOVI R0, -128; HALT (0x80 = -128 as signed i8)
        "expected": {"register": 0, "value": -128},
        "category": "data",
        "notes": "MOVI should handle signed i8 values. 0x80 = -128 in two's complement. Tests signed extension.",
    },
    {
        "name": "MOVI16 loads large immediate",
        "bytecode": [0x40, 0, 0x10, 0x00, 0x00],  # MOVI16 R0, 4096; HALT (Format F)
        "expected": {"register": 0, "value": 4096},
        "category": "data",
        "notes": "MOVI16 (0x40) Format F: opcode, rd, imm16. 4096 = 0x1000. Tests 16-bit immediate.",
    },

    # =========================================================================
    # Category: Arithmetic (0x20-0x2F)
    # =========================================================================
    {
        "name": "ADD two registers",
        "bytecode": [0x18, 0, 10, 0x18, 1, 20, 0x20, 2, 0, 1, 0x00],  # MOVI R0,10; MOVI R1,20; ADD R2,R0,R1; HALT
        "expected": {"register": 2, "value": 30},
        "category": "arithmetic",
        "notes": "ADD (0x20) Format E: opcode, rd, rs1, rs2. R2 = R0 + R1 = 10 + 20 = 30.",
    },
    {
        "name": "SUB two registers",
        "bytecode": [0x18, 0, 30, 0x18, 1, 12, 0x21, 2, 0, 1, 0x00],  # MOVI R0,30; MOVI R1,12; SUB R2,R0,R1; HALT
        "expected": {"register": 2, "value": 18},
        "category": "arithmetic",
        "notes": "SUB (0x21): R2 = R0 - R1 = 30 - 12 = 18.",
    },
    {
        "name": "MUL two registers",
        "bytecode": [0x18, 0, 7, 0x18, 1, 6, 0x22, 2, 0, 1, 0x00],  # MOVI R0,7; MOVI R1,6; MUL R2,R0,R1; HALT
        "expected": {"register": 2, "value": 42},
        "category": "arithmetic",
        "notes": "MUL (0x22): R2 = R0 * R1 = 7 * 6 = 42.",
    },
    {
        "name": "MOD two registers",
        "bytecode": [0x18, 0, 17, 0x18, 1, 5, 0x24, 2, 0, 1, 0x00],  # MOVI R0,17; MOVI R1,5; MOD R2,R0,R1; HALT
        "expected": {"register": 2, "value": 2},
        "category": "arithmetic",
        "notes": "MOD (0x24): R2 = R0 mod R1 = 17 mod 5 = 2.",
    },

    # =========================================================================
    # Category: Comparison (0x2C-0x2F)
    # =========================================================================
    {
        "name": "CMP_EQ sets result for equal values",
        "bytecode": [0x18, 0, 5, 0x18, 1, 5, 0x2C, 2, 0, 1, 0x00],  # MOVI R0,5; MOVI R1,5; CMP_EQ R2,R0,R1; HALT
        "expected": {"register": 2, "value_neq_zero": True},
        "category": "comparison",
        "notes": "CMP_EQ (0x2C): R2 = (R0 == R1) ? 1 : 0. 5 == 5, so R2 should be nonzero (true).",
    },
    {
        "name": "CMP_EQ sets result for unequal values",
        "bytecode": [0x18, 0, 5, 0x18, 1, 3, 0x2C, 2, 0, 1, 0x00],  # MOVI R0,5; MOVI R1,3; CMP_EQ R2,R0,R1; HALT
        "expected": {"register": 2, "value": 0},
        "category": "comparison",
        "notes": "CMP_EQ: 5 != 3, so R2 should be 0 (false).",
    },

    # =========================================================================
    # Category: Register Overlap Safety
    # =========================================================================
    {
        "name": "ADD with rd=rs1 overlap (R1 = R1 + R2)",
        "bytecode": [0x18, 0, 10, 0x18, 1, 5, 0x18, 2, 3, 0x20, 1, 1, 2, 0x00],
        # MOVI R0,10; MOVI R1,5; MOVI R2,3; ADD R1,R1,R2; HALT
        "expected": {"register": 1, "value": 8},
        "category": "arithmetic",
        "notes": "CRITICAL: rd=rs1 overlap. The VM MUST read R1 before writing R1. Expected: R1 = 5 + 3 = 8. If the VM writes before reading, R1 = 0 + 3 = 3 (wrong).",
    },
    {
        "name": "ADD with rd=rs2 overlap (R2 = R0 + R2)",
        "bytecode": [0x18, 0, 10, 0x18, 1, 5, 0x18, 2, 3, 0x20, 2, 0, 2, 0x00],
        # MOVI R0,10; MOVI R1,5; MOVI R2,3; ADD R2,R0,R2; HALT
        "expected": {"register": 2, "value": 13},
        "category": "arithmetic",
        "notes": "CRITICAL: rd=rs2 overlap. R2 = R0 + R2 = 10 + 3 = 13. Same safety requirement.",
    },
    {
        "name": "ADD with all-three overlap (R0 = R0 + R0)",
        "bytecode": [0x18, 0, 7, 0x20, 0, 0, 0, 0x00],  # MOVI R0,7; ADD R0,R0,R0; HALT
        "expected": {"register": 0, "value": 14},
        "category": "arithmetic",
        "notes": "CRITICAL: All three registers the same. R0 = 7 + 7 = 14. Maximum overlap safety.",
    },

    # =========================================================================
    # Category: Stack Operations (0x0C-0x0D, Format B)
    # =========================================================================
    {
        "name": "PUSH and POP preserve value",
        "bytecode": [0x18, 0, 99, 0x0C, 0, 0x0D, 1, 0x00],
        # MOVI R0,99; PUSH R0; POP R1; HALT  (PUSH=0x0C, POP=0x0D per unified ISA)
        "expected": {"register": 1, "value": 99},
        "category": "stack",
        "notes": "PUSH (0x0C) and POP (0x0D) should preserve values exactly. R1 should equal R0 after push/pop cycle.",
    },

    # =========================================================================
    # Category: Logic / Bitwise (0x25-0x27, 0x0A)
    # =========================================================================
    {
        "name": "AND bitwise",
        "bytecode": [0x18, 0, 0x0F, 0x18, 1, 0x03, 0x25, 2, 0, 1, 0x00],  # MOVI R0,15; MOVI R1,3; AND R2,R0,R1; HALT
        "expected": {"register": 2, "value": 3},
        "category": "logic",
        "notes": "AND (0x25): 15 (0b1111) & 3 (0b0011) = 3 (0b0011).",
    },
    {
        "name": "OR bitwise",
        "bytecode": [0x18, 0, 0x0A, 0x18, 1, 0x05, 0x26, 2, 0, 1, 0x00],  # MOVI R0,10; MOVI R1,5; OR R2,R0,R1; HALT
        "expected": {"register": 2, "value": 15},
        "category": "logic",
        "notes": "OR (0x26): 10 (0b1010) | 5 (0b0101) = 15 (0b1111).",
    },
    {
        "name": "XOR bitwise",
        "bytecode": [0x18, 0, 0x0F, 0x18, 1, 0x0F, 0x27, 2, 0, 1, 0x00],  # MOVI R0,15; MOVI R1,15; XOR R2,R0,R1; HALT
        "expected": {"register": 2, "value": 0},
        "category": "logic",
        "notes": "XOR (0x27): 15 ^ 15 = 0. Self-XOR always produces zero.",
    },

    # =========================================================================
    # Category: Increment / Decrement (0x08-0x09, Format B)
    # =========================================================================
    {
        "name": "INC increments register",
        "bytecode": [0x18, 0, 41, 0x08, 0, 0x00],  # MOVI R0,41; INC R0; HALT (INC=0x08 per unified ISA)
        "expected": {"register": 0, "value": 42},
        "category": "arithmetic",
        "notes": "INC (0x08): R0 = R0 + 1 = 41 + 1 = 42. Format B: opcode, rd.",
    },
    {
        "name": "DEC decrements register",
        "bytecode": [0x18, 0, 43, 0x09, 0, 0x00],  # MOVI R0,43; DEC R0; HALT (DEC=0x09 per unified ISA)
        "expected": {"register": 0, "value": 42},
        "category": "arithmetic",
        "notes": "DEC (0x09): R0 = R0 - 1 = 43 - 1 = 42.",
    },

    # =========================================================================
    # Category: Complex Programs
    # =========================================================================
    {
        "name": "GCD of 48 and 18 = 6 (Euclid's algorithm)",
        "bytecode": None,  # Too complex for inline bytecode; use source description
        "expected": {"register": 0, "value": 6},
        "category": "complex",
        "notes": "Classic GCD algorithm from Oracle1's dojo exercise. Tests: LOOP, CMP, conditional jump, modulo. This is the 'hello world' of FLUX conformance.",
        "source_description": """
        MOVI R0, 48      ; a = 48
        MOVI R1, 18      ; b = 18
        loop:
        CMP_EQ R2, R0, R1  ; if a == b, goto done
        JNZ R2, done
        CMP_GT R2, R0, R1  ; if a > b, goto a_sub
        JNZ R2, a_sub
        MOD R2, R1, R0     ; b = b mod a
        MOV R1, R2          ; (or assign to R1)
        JMP loop
        a_sub:
        MOD R2, R0, R1     ; a = a mod b
        MOV R0, R2
        JMP loop
        done:
        HALT
        """,
    },
    {
        "name": "Fibonacci(10) = 55",
        "bytecode": None,
        "expected": {"register": 0, "value": 55},
        "category": "complex",
        "notes": "Computes the 10th Fibonacci number. Tests: loop, MOV, ADD, decrement, conditional jump.",
        "source_description": """
        MOVI R0, 0       ; a = 0 (fib(0))
        MOVI R1, 1       ; b = 1 (fib(1))
        MOVI R2, 10      ; n = 10
        MOVI R3, 1       ; counter = 1
        loop:
        ADD R4, R0, R1   ; temp = a + b
        MOV R0, R1        ; a = b
        MOV R1, R4        ; b = temp
        INC R3            ; counter++
        CMP_LT R4, R3, R2  ; if counter < n
        JNZ R4, loop
        HALT              ; R1 = fib(10) = 55
        """,
    },
    {
        "name": "Sum of squares 1..5 = 55",
        "bytecode": None,
        "expected": {"register": 0, "value": 55},
        "category": "complex",
        "notes": "Computes 1^2 + 2^2 + 3^2 + 4^2 + 5^2 = 1+4+9+16+25 = 55. Tests: loop, MUL, ADD.",
        "source_description": """
        MOVI R0, 0       ; sum = 0
        MOVI R1, 1       ; i = 1
        MOVI R2, 5       ; n = 5
        loop:
        MUL R3, R1, R1   ; temp = i * i
        ADD R0, R0, R3   ; sum += temp
        INC R1            ; i++
        CMP_LT R3, R1, R2  ; if i <= n (i.e., i < n+1)
        JNZ R3, loop
        HALT              ; R0 = 55
        """,
    },
]


# ===========================================================================
# Runner Template (for VM implementers)
# ===========================================================================

def run_conformance_tests(runner_fn):
    """
    Run all conformance tests against a VM implementation.

    Args:
        runner_fn: callable(bytecode: list[int]) -> dict
            Takes a bytecode list, returns a dict with at minimum:
            - 'registers': dict[int, int] — register state after execution
            - 'crashed': bool — whether the VM crashed

    Returns:
        dict with 'passed', 'failed', 'results' keys.
    """
    results = {"passed": 0, "failed": 0, "results": []}

    for test in TEST_VECTORS:
        if test["bytecode"] is None:
            # Source-description tests need to be compiled first
            results["results"].append({
                "name": test["name"],
                "status": "SKIPPED",
                "reason": "Source description test — compile manually",
            })
            continue

        try:
            state = runner_fn(test["bytecode"])

            if test["expected"] == "no_crash":
                if not state.get("crashed", False):
                    results["results"].append({"name": test["name"], "status": "PASS"})
                    results["passed"] += 1
                else:
                    results["results"].append({"name": test["name"], "status": "FAIL", "reason": "VM crashed"})
                    results["failed"] += 1

            elif isinstance(test["expected"], dict):
                if "register" in test["expected"]:
                    reg = test["expected"]["register"]
                    reg_val = state.get("registers", {}).get(reg)
                    exp_val = test["expected"]["value"]

                    if "value_neq_zero" in test["expected"]:
                        if reg_val != 0:
                            results["results"].append({"name": test["name"], "status": "PASS"})
                            results["passed"] += 1
                        else:
                            results["results"].append({"name": test["name"], "status": "FAIL", "reason": f"R{reg}={reg_val}, expected nonzero"})
                            results["failed"] += 1
                    elif reg_val == exp_val:
                        results["results"].append({"name": test["name"], "status": "PASS"})
                        results["passed"] += 1
                    else:
                        results["results"].append({"name": test["name"], "status": "FAIL", "reason": f"R{reg}={reg_val}, expected {exp_val}"})
                        results["failed"] += 1

        except Exception as e:
            results["results"].append({"name": test["name"], "status": "ERROR", "reason": str(e)})
            results["failed"] += 1

    return results
