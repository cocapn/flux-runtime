# Custom Vocabularies

**This folder is yours.** Drop `.fluxvocab` files here to teach the Open-Flux-Interpreter new words.

## How to Create a Vocabulary File

Create a file ending in `.fluxvocab` (e.g., `autopilot.fluxvocab`):

```
---
pattern: "steer to heading $degrees"
expand: |
    MOVI R0, ${degrees}
    MOVI R1, 270
    CMP R0, R1
    JNZ R0, safe
    MOVI R2, 1
    JNZ R2, done
    safe:
    MOVI R2, 0
    done:
    HALT
result: R2
name: steer-heading
description: Check if heading matches target
tags: autopilot, navigation
---
pattern: "check depth $depth against minimum $min"
expand: |
    MOVI R0, ${depth}
    MOVI R1, ${min}
    CMP R0, R1
    HALT
result: R13
name: depth-check
description: Compare depth against minimum
tags: autopilot, safety
```

## Pattern Syntax

- `$var` — captures a number from the input text
- `${var}` — substitutes the captured value in the assembly template
- Patterns are matched case-insensitively
- First match wins — order your patterns from specific to general

## Assembly Syntax

```
MOVI R0, 42       # Load immediate
MOV R0, R1        # Copy register
IADD R0, R1, R2   # R0 = R1 + R2
ISUB R0, R1, R2   # R0 = R1 - R2
IMUL R0, R1, R2   # R0 = R1 * R2
IDIV R0, R1, R2   # R0 = R1 / R2
INC R0             # R0++
DEC R0             # R0--
CMP R0, R1         # Compare → R13
JNZ R0, offset     # Jump if not zero
JZ R0, offset      # Jump if zero
HALT               # Stop execution
```

## Tips for Agents

1. **Start specific, end general.** Put "factorial of 7" before "factorial of $n"
2. **Use result_reg to specify which register holds the answer**
3. **Tag your vocabularies** so other agents can discover them
4. **Test in the sandbox** before deploying — the interpreter catches infinite loops
5. **Share vocabularies via I2I** — push your .fluxvocab files to other agents' repos

## Loading Custom Vocabularies

```python
from flux.open_interp import OpenFluxInterpreter

interp = OpenFluxInterpreter()
interp.load_vocabulary("vocabularies/custom")  # Your folder
interp.load_vocabulary("/path/to/other/agent/vocab")  # Another agent's vocab

result = interp.run("steer to heading 270")
print(result.result_value)
```

Or in CLI:
```bash
flux open --vocab vocabularies/custom --vocab /other/agent/vocab
```
