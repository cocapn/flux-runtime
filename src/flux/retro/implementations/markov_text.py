"""Markov chain text generator — hybrid FLUX bytecode approach.

Training phase (Python):
  - Parse input text into words
  - Build bigram frequency table: {word → [(next_word, count), ...]}

Generation phase (bytecode + Python):
  - Python builds a per-word bytecode program for cumulative-frequency
    word selection
  - Each bytecode program takes a target value and scans through
    the follower frequencies using CMP + JL/JE conditional branches
    to select the next word
  - Python manages the text generation loop and dead-end recovery

The bytecode for each word selection demonstrates:
  - MOVI (load target value)
  - CMP + JL/JE (cumulative frequency comparison)
  - MOVI + HALT (output selected word index)
"""

from __future__ import annotations

from flux.bytecode.opcodes import Op
from flux.vm.interpreter import Interpreter
from ._asm import Assembler


class MarkovChainText:
    """Markov chain text generator with bytecode word-selection engine."""

    SAMPLE_TEXT = (
        "the cat sat on the mat the cat ate the rat "
        "the rat sat on the hat the dog ran in the park "
        "the dog ate the bone the cat ran to the dog "
        "the mat was on the floor the hat was red "
        "the bone was big the park was green "
        "the cat and the dog played in the park "
    )

    @classmethod
    def _build_markov_table(cls) -> tuple[dict, list[str]]:
        """Build bigram frequency table from sample text.

        Returns (table, vocabulary) where:
          table = {word_idx: [(follower_idx, freq), ...]}
          vocabulary = [word0, word1, ...]
        """
        words = cls.SAMPLE_TEXT.lower().split()
        vocab = list(dict.fromkeys(words))  # unique, order-preserving
        word_to_idx = {w: i for i, w in enumerate(vocab)}

        bigrams: dict[int, dict[int, int]] = {}
        for i in range(len(words) - 1):
            w1 = word_to_idx[words[i]]
            w2 = word_to_idx[words[i + 1]]
            if w1 not in bigrams:
                bigrams[w1] = {}
            bigrams[w1][w2] = bigrams[w1].get(w2, 0) + 1

        table = {}
        for w1, followers in bigrams.items():
            table[w1] = [(w2, count) for w2, count in followers.items()]

        return table, vocab

    @classmethod
    def _build_selection_bytecode(
        cls, followers: list[tuple[int, int]], target: int
    ) -> bytes:
        """Build a bytecode program that selects a follower word.

        The bytecode scans cumulative frequencies using CMP + JL/JE
        and outputs the selected word index in R5.

        Args:
            followers: list of (word_idx, frequency) pairs
            target: target value in [0, total_freq)
        """
        a = Assembler()

        # R0 = target value
        a.movi(0, target)

        # Scan cumulative frequencies
        cumul = 0
        for i, (f_idx, freq) in enumerate(followers):
            cumul += freq
            # If target < cumul → select this word
            a.movi(3, cumul)
            a.cmp(0, 3)       # CMP target, cumul
            a.jl("found")     # target < cumul
            a.je("found")     # target == cumul

        # Fallback (safety)
        a.movi(5, followers[-1][0])
        a.jmp("done")

        a.label("found")
        a.movi(5, f_idx)

        a.label("done")
        a.halt()

        return a.to_bytes()

    @classmethod
    def _select_next_word(
        cls, vm: Interpreter, word_idx: int, table: dict,
        rand_counter: int
    ) -> int:
        """Select next word using bytecode cumulative-frequency scan."""
        if word_idx not in table:
            return 0

        followers = table[word_idx]
        total_freq = sum(f for _, f in followers)
        target = rand_counter % total_freq

        bytecode = cls._build_selection_bytecode(followers, target)
        vm.bytecode = bytecode
        vm.pc = 0
        vm.halted = False
        vm.running = False
        vm._flag_zero = False
        vm._flag_sign = False
        vm._flag_carry = False
        vm._flag_overflow = False
        vm.execute()

        return vm.regs.read_gp(5)

    @classmethod
    def generate_text(cls, length: int = 30, seed_word: str = "the") -> str:
        """Generate text using the Markov chain with bytecode selection.

        Returns the generated text string.
        """
        table, vocab = cls._build_markov_table()

        if seed_word.lower() not in vocab:
            seed_word = vocab[0]

        word_idx = vocab.index(seed_word.lower())
        rand_counter = 42

        vm = Interpreter(bytes([Op.HALT]), memory_size=65536)

        generated = [vocab[word_idx]]

        for _ in range(length - 1):
            if word_idx not in table:
                word_idx = list(table.keys())[rand_counter % len(table)]
                rand_counter += 1
                generated.append(vocab[word_idx])
                continue

            next_idx = cls._select_next_word(vm, word_idx, table, rand_counter)
            rand_counter += 1
            word_idx = next_idx
            generated.append(vocab[word_idx])

        return " ".join(generated)

    @classmethod
    def demonstrate(cls) -> None:
        """Run Markov chain text generation demonstration."""
        print("=" * 64)
        print("  FLUX BYTECODE MARKOV CHAIN TEXT GENERATOR")
        print("=" * 64)

        table, vocab = cls._build_markov_table()
        print(f"  Training text: {len(cls.SAMPLE_TEXT.split())} words")
        print(f"  Vocabulary: {len(vocab)} unique words")
        print(f"  Bigram entries: {sum(len(f) for f in table.values())}")

        print(f"\n  Vocabulary: {', '.join(vocab)}")

        print(f"\n  Bigram table:")
        for word_idx in sorted(table.keys()):
            word = vocab[word_idx]
            followers = ", ".join(
                f"{vocab[f_idx]}({freq})" for f_idx, freq in table[word_idx]
            )
            print(f"    {word} → {followers}")

        print(f"\n  --- Generation (bytecode-powered word selection) ---\n")

        seeds = ["the", "cat", "dog"]
        for seed in seeds:
            if seed.lower() in vocab:
                text = cls.generate_text(length=20, seed_word=seed)
                print(f"  Seed \"{seed}\" ({len(text.split())} words):")
                print(f"    \"{text}\"")

                # Show bytecode size for this seed word
                seed_idx = vocab.index(seed.lower())
                followers = table[seed_idx]
                total_freq = sum(f for _, f in followers)
                bc = cls._build_selection_bytecode(followers, 0)
                print(f"    Selection bytecode: {len(bc)} bytes "
                      f"({len(followers)} followers, total freq={total_freq})")
                print()

        # Demonstrate bytecode for most-connected word
        best_word = max(table, key=lambda w: len(table[w]))
        best_name = vocab[best_word]
        best_followers = table[best_word]
        total = sum(f for _, f in best_followers)

        print(f"  --- Bytecode detail for \"{best_name}\" "
              f"({len(best_followers)} followers, freq={total}) ---")
        bc = cls._build_selection_bytecode(best_followers, 5)
        print(f"  Bytecode size: {len(bc)} bytes")
        print(f"  Instructions: {len(bc) // 4} (all 4-byte Format D)")
        print(f"  Pattern: MOVI + CMP + JL + JE per follower")
        print()


if __name__ == "__main__":
    MarkovChainText.demonstrate()
