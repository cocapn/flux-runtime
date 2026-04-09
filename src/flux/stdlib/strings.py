"""String operations for the FLUX standard library.

Each string function emits FIR instructions that delegate to runtime
string primitives.  Strings are modeled as opaque values of ``StringType``
with operations performed via runtime calls.
"""

from __future__ import annotations

from typing import Optional

from flux.fir.types import FIRType, TypeContext, IntType, StringType
from flux.fir.values import Value
from flux.fir.builder import FIRBuilder


# ── Base ────────────────────────────────────────────────────────────────────


class StringFunction:
    """Base class for string standard library functions."""

    name: str = ""
    description: str = ""

    def emit(self, builder: FIRBuilder, args: list[Value]) -> Optional[Value]:
        """Emit FIR instructions for this string function."""
        raise NotImplementedError


# ── concat(a, b) → string ──────────────────────────────────────────────────


class ConcatFn(StringFunction):
    """Concatenate two strings."""

    name = "concat"
    description = "Concatenate two strings into a new string."

    def emit(self, builder: FIRBuilder, args: list[Value]) -> Value:
        if len(args) < 2:
            raise ValueError("concat() requires 2 string arguments")
        string_t = builder._ctx.get_string()
        result = builder.call("flux.str_concat", args, return_type=string_t)
        return result


# ── substring(s, start, end) → string ──────────────────────────────────────


class SubstringFn(StringFunction):
    """Extract a substring from start (inclusive) to end (exclusive)."""

    name = "substring"
    description = "Extract a substring [start, end) from a string."

    def emit(self, builder: FIRBuilder, args: list[Value]) -> Value:
        if len(args) < 3:
            raise ValueError("substring() requires 3 arguments: s, start, end")
        s, start, end = args[0], args[1], args[2]
        string_t = builder._ctx.get_string()
        result = builder.call("flux.str_substring", [s, start, end], return_type=string_t)
        return result


# ── split(s, delimiter) → list<string> ─────────────────────────────────────


class SplitFn(StringFunction):
    """Split a string by a delimiter, returning a list of substrings."""

    name = "split"
    description = "Split a string by a delimiter into a list of substrings."

    def emit(self, builder: FIRBuilder, args: list[Value]) -> Value:
        if len(args) < 2:
            raise ValueError("split() requires 2 arguments: s, delimiter")
        s, delim = args[0], args[1]
        # Returns a ref to a list struct
        list_type = builder._ctx.get_ref(builder._ctx.get_int(32))
        result = builder.call("flux.str_split", [s, delim], return_type=list_type)
        return result


# ── join(parts, separator) → string ────────────────────────────────────────


class JoinFn(StringFunction):
    """Join a list of strings with a separator."""

    name = "join"
    description = "Join a list of strings with a separator."

    def emit(self, builder: FIRBuilder, args: list[Value]) -> Value:
        if len(args) < 2:
            raise ValueError("join() requires 2 arguments: parts, separator")
        parts, sep = args[0], args[1]
        string_t = builder._ctx.get_string()
        result = builder.call("flux.str_join", [parts, sep], return_type=string_t)
        return result


# ── length(s) → i32 ────────────────────────────────────────────────────────


class LengthFn(StringFunction):
    """Return the length of a string in bytes."""

    name = "length"
    description = "Return the byte length of a string."

    def emit(self, builder: FIRBuilder, args: list[Value]) -> Value:
        if len(args) < 1:
            raise ValueError("length() requires 1 string argument")
        s = args[0]
        i32 = builder._ctx.get_int(32)
        result = builder.call("flux.str_length", [s], return_type=i32)
        return result


# ── format(template, *args) → string ───────────────────────────────────────


class FormatFn(StringFunction):
    """Format a string template with positional arguments.

    Uses ``{0}``, ``{1}``, etc. as placeholders.
    """

    name = "format"
    description = "Format a string template with positional arguments."

    def emit(self, builder: FIRBuilder, args: list[Value]) -> Value:
        if len(args) < 1:
            raise ValueError("format() requires at least a template string")
        string_t = builder._ctx.get_string()
        result = builder.call("flux.str_format", args, return_type=string_t)
        return result

    def emit_parse_template(self, template: str) -> list[str]:
        """Parse a format template and return the placeholder types.

        Returns a list of placeholder indices found in the template.
        """
        import re
        placeholders = re.findall(r'\{(\d+)\}', template)
        return placeholders


# ── Registry of all string functions ────────────────────────────────────────

STDLIB_STRINGS: dict[str, StringFunction] = {
    "concat": ConcatFn(),
    "substring": SubstringFn(),
    "split": SplitFn(),
    "join": JoinFn(),
    "length": LengthFn(),
    "format": FormatFn(),
}
