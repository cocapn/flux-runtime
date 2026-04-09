"""Correctness Validator — ensures mutations don't break system correctness.

The validator maintains a suite of test cases with known expected outputs,
captures baselines, and detects regressions when mutations are applied.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Any, Callable

from .genome import Genome


# ── Types ─────────────────────────────────────────────────────────────────────

@dataclass
class TestCase:
    """A single test case with a known expected output."""
    name: str
    fn: Callable[[], Any]
    expected: Any = None
    tolerance: float = 0.0  # for float comparisons
    is_baseline: bool = False  # True if expected was captured from baseline

    def __repr__(self) -> str:
        return f"TestCase({self.name!r})"


@dataclass
class TestResult:
    """Result of running a single test case."""
    name: str
    passed: bool
    expected: Any = None
    actual: Any = None
    error: str = ""
    elapsed_ns: int = 0

    def __repr__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"TestResult({status}, {self.name!r})"


@dataclass
class ValidationResult:
    """Result of validating all test cases."""
    all_pass: bool
    num_passed: int
    num_failed: int
    num_total: int
    failure_details: list[TestResult] = field(default_factory=list)
    elapsed_ns: int = 0

    @property
    def pass_rate(self) -> float:
        """Fraction of tests that passed (0.0 to 1.0)."""
        if self.num_total == 0:
            return 1.0
        return self.num_passed / self.num_total

    def __repr__(self) -> str:
        return (
            f"ValidationResult("
            f"{self.num_passed}/{self.num_total} passed"
            f"{'' if self.all_pass else f', {self.num_failed} FAILED'})"
        )


@dataclass
class RegressionReport:
    """Report comparing before/after genomes for correctness."""
    genome_before_checksum: str = ""
    genome_after_checksum: str = ""
    tests_before: int = 0
    tests_after: int = 0
    regressions: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    all_pass: bool = True

    @property
    def has_regressions(self) -> bool:
        return len(self.regressions) > 0

    def __repr__(self) -> str:
        if self.all_pass:
            return "RegressionReport(NO REGRESSIONS)"
        return (
            f"RegressionReport({len(self.regressions)} regressions: "
            f"{', '.join(self.regressions[:3])})"
        )


# ── Correctness Validator ─────────────────────────────────────────────────────

class CorrectnessValidator:
    """Validates that mutations don't break system correctness.

    The validator maintains a suite of test cases and can:
    - Register tests with known expected outputs
    - Capture baselines from the current system
    - Validate the system against baselines
    - Detect regressions between genome versions
    """

    def __init__(self) -> None:
        self._test_cases: list[TestCase] = []
        self._baseline_outputs: dict[str, Any] = {}
        self._validation_history: list[ValidationResult] = []

    # ── Test Registration ───────────────────────────────────────────────

    def register_test(
        self,
        name: str,
        fn: Callable[[], Any],
        expected: Any = None,
        tolerance: float = 0.0,
    ) -> None:
        """Register a test case with known expected output.

        Args:
            name: Unique test case name.
            fn: Callable that produces a result.
            expected: Expected result. If None, must capture baseline first.
            tolerance: For float comparisons, allowed difference.
        """
        # Remove existing test with same name
        self._test_cases = [
            t for t in self._test_cases if t.name != name
        ]
        self._test_cases.append(TestCase(
            name=name,
            fn=fn,
            expected=expected,
            tolerance=tolerance,
        ))

    def unregister_test(self, name: str) -> bool:
        """Remove a test case by name.

        Args:
            name: Name of the test to remove.

        Returns:
            True if the test was found and removed.
        """
        before = len(self._test_cases)
        self._test_cases = [
            t for t in self._test_cases if t.name != name
        ]
        self._baseline_outputs.pop(name, None)
        return len(self._test_cases) < before

    def register_tests(self, tests: list[tuple[str, Callable[[], Any], Any]]) -> None:
        """Register multiple test cases at once.

        Args:
            tests: List of (name, fn, expected) tuples.
        """
        for name, fn, expected in tests:
            self.register_test(name, fn, expected)

    # ── Baseline ────────────────────────────────────────────────────────

    def capture_baseline(self) -> None:
        """Run all tests and capture current outputs as baseline.

        Tests without explicit expected values will have their
        current output recorded as the baseline.
        """
        for test in self._test_cases:
            try:
                result = test.fn()
                self._baseline_outputs[test.name] = result
                test.expected = result
                test.is_baseline = True
            except Exception:
                # Tests that error during baseline capture get None
                self._baseline_outputs[test.name] = None

    def clear_baseline(self) -> None:
        """Clear all captured baselines."""
        self._baseline_outputs.clear()
        for test in self._test_cases:
            if test.is_baseline:
                test.expected = None
                test.is_baseline = False

    def get_baseline(self, name: str) -> Any:
        """Get the baseline output for a test case.

        Args:
            name: Test case name.

        Returns:
            Baseline output, or None if not captured.
        """
        return self._baseline_outputs.get(name)

    # ── Validation ──────────────────────────────────────────────────────

    def validate(self) -> ValidationResult:
        """Run all tests against baseline and report any regressions.

        Returns:
            ValidationResult with pass/fail details.
        """
        start = time.monotonic_ns()
        passed = 0
        failed = 0
        failures: list[TestResult] = []

        for test in self._test_cases:
            t_start = time.monotonic_ns()
            try:
                actual = test.fn()
                expected = test.expected

                if expected is None:
                    # No baseline — auto-pass
                    result = TestResult(
                        name=test.name,
                        passed=True,
                        expected=expected,
                        actual=actual,
                        elapsed_ns=time.monotonic_ns() - t_start,
                    )
                    passed += 1
                elif self._compare(actual, expected, test.tolerance):
                    result = TestResult(
                        name=test.name,
                        passed=True,
                        expected=expected,
                        actual=actual,
                        elapsed_ns=time.monotonic_ns() - t_start,
                    )
                    passed += 1
                else:
                    result = TestResult(
                        name=test.name,
                        passed=False,
                        expected=expected,
                        actual=actual,
                        error=f"Expected {expected!r}, got {actual!r}",
                        elapsed_ns=time.monotonic_ns() - t_start,
                    )
                    failed += 1
                    failures.append(result)
            except Exception as exc:
                result = TestResult(
                    name=test.name,
                    passed=False,
                    error=str(exc),
                    elapsed_ns=time.monotonic_ns() - t_start,
                )
                failed += 1
                failures.append(result)

        total = passed + failed
        elapsed = time.monotonic_ns() - start

        validation_result = ValidationResult(
            all_pass=failed == 0,
            num_passed=passed,
            num_failed=failed,
            num_total=total,
            failure_details=failures,
            elapsed_ns=elapsed,
        )
        self._validation_history.append(validation_result)
        return validation_result

    def validate_genome(self, genome: Genome) -> bool:
        """Validate a genome by running all test cases.

        The genome parameter is provided for future use (checking
        genome-specific correctness invariants).

        Args:
            genome: The genome to validate.

        Returns:
            True if all tests pass.
        """
        result = self.validate()
        return result.all_pass

    def regression_check(
        self,
        genome_before: Genome,
        genome_after: Genome,
    ) -> RegressionReport:
        """Compare before/after genomes for correctness regressions.

        Runs validation on the current system and reports any differences
        from the known baseline.

        Args:
            genome_before: The genome before the mutation.
            genome_after: The genome after the mutation.

        Returns:
            RegressionReport with details.
        """
        # Run validation
        result = self.validate()

        # Check for genome-level regressions
        diff = genome_before.diff(genome_after)
        regressions: list[str] = []
        improvements: list[str] = []

        # Track language changes for HEAT/HOT modules going to slower languages
        for path, (old_lang, new_lang) in diff.language_changes.items():
            lang_speed = {
                "python": 1, "typescript": 2, "csharp": 4,
                "rust": 10, "c": 8, "c_simd": 16,
            }
            old_speed = lang_speed.get(old_lang, 1)
            new_speed = lang_speed.get(new_lang, 1)
            if new_speed < old_speed:
                regressions.append(
                    f"{path}: language slowdown ({old_lang} → {new_lang})"
                )
            elif new_speed > old_speed:
                improvements.append(
                    f"{path}: language speedup ({old_lang} → {new_lang})"
                )

        # Check fitness regression
        if diff.fitness_delta < -0.01:
            regressions.append(
                f"Fitness regression: {diff.fitness_before:.4f} → {diff.fitness_after:.4f}"
            )

        # Check validation failures
        if not result.all_pass:
            for failure in result.failure_details:
                regressions.append(f"Test failure: {failure.name} — {failure.error}")

        return RegressionReport(
            genome_before_checksum=genome_before.checksum,
            genome_after_checksum=genome_after.checksum,
            tests_before=len(self._test_cases),
            tests_after=result.num_total,
            regressions=regressions,
            improvements=improvements,
            all_pass=len(regressions) == 0,
        )

    # ── Queries ─────────────────────────────────────────────────────────

    @property
    def test_count(self) -> int:
        """Number of registered test cases."""
        return len(self._test_cases)

    @property
    def test_names(self) -> list[str]:
        """Names of all registered test cases."""
        return [t.name for t in self._test_cases]

    def get_history(self) -> list[ValidationResult]:
        """Get validation history."""
        return list(self._validation_history)

    def clear_history(self) -> None:
        """Clear validation history."""
        self._validation_history.clear()

    def clear_all(self) -> None:
        """Clear everything — tests, baselines, and history."""
        self._test_cases.clear()
        self._baseline_outputs.clear()
        self._validation_history.clear()

    # ── Internal ────────────────────────────────────────────────────────

    @staticmethod
    def _compare(actual: Any, expected: Any, tolerance: float = 0.0) -> bool:
        """Compare actual vs expected with tolerance."""
        if tolerance > 0:
            if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
                return abs(actual - expected) <= tolerance
        return actual == expected

    def __repr__(self) -> str:
        return (
            f"CorrectnessValidator("
            f"tests={self.test_count}, "
            f"baselines={len(self._baseline_outputs)})"
        )
