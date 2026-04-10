"""
Open-Flux-Interpreter — The Crown Jewel

Markdown/Text → Vocabulary Match → Assembly → Bytecode → Sandboxed Execution

Agents pass markdown and get compute results back. Users teach it new words
by dropping .fluxvocab files in vocabulary folders.

CLI: flux open
API: OpenFluxInterpreter().run("factorial of 7") → 5040
"""

import os
import re
import sys
from typing import Optional, Dict, List

from .vocabulary import Vocabulary, VocabEntry
from .assembler import assemble_text
from .sandbox import SandboxVM, SandboxResult


class OpenFluxInterpreter:
    """
    The Open-Flux-Interpreter.
    
    Converts markdown/natural language to FLUX bytecode via vocabulary matching,
    then executes in a sandbox. Agents can load custom vocabularies to teach
    it domain-specific words.
    """
    
    def __init__(self, vocab_paths: Optional[List[str]] = None):
        self.vocab = Vocabulary()
        self.verbose = False
        
        # Load core vocabularies
        core_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'vocabularies', 'core')
        math_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'vocabularies', 'math')
        loops_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'vocabularies', 'loops')
        
        for p in [core_path, math_path, loops_path]:
            if os.path.isdir(p):
                self.vocab.load_folder(p)
        
        # Load additional paths
        if vocab_paths:
            for p in vocab_paths:
                self.vocab.load_folder(p)
    
    def load_vocabulary(self, path: str):
        """Load a vocabulary folder. Agents call this to teach new words."""
        self.vocab.load_folder(path)
    
    def run(self, text: str, result_reg: int = 0, max_cycles: int = 1_000_000) -> SandboxResult:
        """
        Main entry point: text → bytecode → execution → result.
        
        Args:
            text: Natural language, markdown, or FLUX assembly
            result_reg: Which register to read as the result
            max_cycles: Safety limit for execution
            
        Returns:
            SandboxResult with registers, cycles, and any errors
        """
        # Step 1: Try vocabulary match
        match = self.vocab.find_match(text)
        
        if match:
            entry, groups = match
            # Substitute captured groups into the assembly template
            assembly = entry.bytecode_template
            for key, val in groups.items():
                assembly = assembly.replace(f'${{{key}}}', val)
            
            result_reg = entry.result_reg
            
            if self.verbose:
                print(f"[vocab] matched: {entry.name}")
                print(f"[vocab] groups: {groups}")
                print(f"[vocab] assembly:\n{assembly}")
        
        elif self._is_assembly(text):
            # Direct assembly text
            assembly = text
            if self.verbose:
                print(f"[asm] direct assembly mode")
        
        elif self._is_hex_bytecode(text):
            # Direct hex bytecode
            hex_str = text.strip().replace(' ', '').replace('0x', '')
            bytecode = bytes.fromhex(hex_str)
            if self.verbose:
                print(f"[hex] direct bytecode mode ({len(bytecode)} bytes)")
            return self._execute(bytecode, result_reg, max_cycles)
        
        else:
            # Try inline math
            math_result = self._try_inline_math(text)
            if math_result is not None:
                return SandboxResult(
                    success=True,
                    registers=[0]*16,
                    cycles=1,
                    result_value=math_result,
                    result_reg=0,
                )
            
            return SandboxResult(
                success=False,
                error=f"No vocabulary match for: {text[:100]}",
            )
        
        # Step 2: Assemble
        try:
            bytecode = assemble_text(assembly)
        except Exception as e:
            return SandboxResult(success=False, error=f"Assembly error: {e}")
        
        # Step 3: Execute in sandbox
        return self._execute(bytecode, result_reg, max_cycles)
    
    def _execute(self, bytecode: bytes, result_reg: int, max_cycles: int) -> SandboxResult:
        """Execute bytecode in sandbox."""
        vm = SandboxVM(bytecode, max_cycles)
        vm.execute()
        result = vm.result(result_reg)
        result.bytecode_hex = ' '.join(f'{b:02X}' for b in bytecode)
        return result
    
    def _is_assembly(self, text: str) -> bool:
        """Check if text looks like FLUX assembly."""
        lines = text.strip().split('\n')
        mnemonics = {'MOVI', 'MOV', 'IADD', 'ISUB', 'IMUL', 'IDIV', 'INC', 'DEC',
                     'JNZ', 'JZ', 'JMP', 'HALT', 'PUSH', 'POP', 'CMP', 'NOP'}
        for line in lines[:3]:
            first_word = line.strip().split()[0].upper() if line.strip() else ''
            if first_word in mnemonics:
                return True
        return False
    
    def _is_hex_bytecode(self, text: str) -> bool:
        """Check if text is hex bytecode like '2B 00 07 00 80'."""
        cleaned = text.strip().replace(' ', '').replace('0x', '').replace(',', '')
        return bool(re.match(r'^[0-9a-fA-F]+$', cleaned)) and len(cleaned) % 2 == 0 and len(cleaned) >= 4
    
    def _try_inline_math(self, text: str) -> Optional[int]:
        """Try to evaluate simple inline math like '3 + 4' or '10 * 5'."""
        # "what is X op Y"
        m = re.search(r'(\d+)\s*([+\-*/×÷])\s*(\d+)', text)
        if m:
            a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
            if op in ('+',): return a + b
            if op in ('-',): return a - b
            if op in ('*', '×'): return a * b
            if op in ('/', '÷') and b != 0: return int(a / b)
        return None
    
    def list_vocabulary(self) -> List[str]:
        """List all loaded vocabulary patterns."""
        return self.vocab.list_words()
    
    def interactive(self):
        """Start interactive mode (like OpenInterpreter)."""
        print("╔══════════════════════════════════════════════════╗")
        print("║   Open-Flux-Interpreter                         ║")
        print("║   Markdown → Bytecode → Execution                ║")
        print("║   Type 'help' for commands, 'quit' to exit       ║")
        print("╚══════════════════════════════════════════════════╝")
        print(f"\n  Loaded {len(self.vocab.entries)} vocabulary patterns")
        print(f"  Loaded {len(self.vocab.templates)} templates\n")
        
        while True:
            try:
                text = input("flux> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nbye")
                break
            
            if not text:
                continue
            if text in ('quit', 'exit', 'q'):
                print("bye")
                break
            if text == 'help':
                self._print_help()
                continue
            if text == 'vocab':
                for p in self.list_vocabulary():
                    print(f"  {p}")
                continue
            if text.startswith('load '):
                path = text[5:].strip()
                self.load_vocabulary(path)
                print(f"  Loaded vocabulary from {path}")
                continue
            
            # Execute
            result = self.run(text)
            
            if result.success:
                print(f"  ✓ Result: R{result.result_reg} = {result.result_value}")
                print(f"    Cycles: {result.cycles} | Bytes: {len(result.bytecode_hex.split())}")
                if result.bytecode_hex:
                    print(f"    Bytecode: {result.bytecode_hex}")
                # Show non-zero registers
                for i in range(16):
                    if result.registers[i] != 0 and i != result.result_reg:
                        print(f"    R{i} = {result.registers[i]}")
            else:
                print(f"  ✗ {result.error}")
            print()
    
    def _print_help(self):
        print("""
  Commands:
    <text>     — interpret text as bytecode and execute
    vocab      — list loaded vocabulary patterns
    load <dir> — load vocabulary from a folder
    help       — show this help
    quit       — exit
    
  Examples:
    flux> compute 3 + 4
    flux> factorial of 7
    flux> sum 1 to 100
    flux> MOVI R0, 42\nHALT
    flux> 2B 00 07 00 80
""")


def main():
    """CLI entry point: flux open"""
    import argparse
    parser = argparse.ArgumentParser(description='Open-Flux-Interpreter')
    parser.add_argument('input', nargs='?', help='Text to interpret')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('--vocab', action='append', help='Additional vocabulary folder')
    parser.add_argument('-i', '--interactive', action='store_true')
    args = parser.parse_args()
    
    interp = OpenFluxInterpreter(vocab_paths=args.vocab or [])
    interp.verbose = args.verbose
    
    if args.input:
        result = interp.run(args.input)
        if result.success:
            print(result.result_value)
        else:
            print(f"Error: {result.error}", file=sys.stderr)
            sys.exit(1)
    elif args.interactive or not args.input:
        interp.interactive()


if __name__ == '__main__':
    main()
