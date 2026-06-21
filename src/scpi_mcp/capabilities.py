"""Capability detection — what can this instrument actually do?

On real hardware the DS1000Z reports installed options via ``*OPT?`` (bandwidth
unlock, MSO/logic, function-gen, etc.). Part 1 stubs that out and returns the
DS1054Z-unlocked-to-DS1104Z-base profile: 4 analog channels, 100 MHz, and
**no** ``:SOURce`` (function gen) or ``:LA`` (logic analyzer).

Part 2/3 will replace :func:`detect_capabilities` with a real ``*OPT?`` parse
sourced through the instrument library (never a raw SCPI string here).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .instruments.base import Instrument


@dataclass(frozen=True)
class Capabilities:
    """Static description of an instrument's reachable feature set."""

    model: str
    analog_channels: int
    bandwidth_mhz: int
    has_source: bool = False  # :SOURce / function generator — out of scope
    has_logic: bool = False  # :LA / logic analyzer — out of scope
    max_memory_depth: int = 24_000_000  # DS1104Z base deep memory (1 ch)
    options: tuple[str, ...] = field(default_factory=tuple)

    def channel_ids(self) -> tuple[int, ...]:
        return tuple(range(1, self.analog_channels + 1))


# The base profile we assume for the bench unit until *OPT? is wired up.
DS1104Z_BASE = Capabilities(
    model="DS1104Z",
    analog_channels=4,
    bandwidth_mhz=100,
    has_source=False,
    has_logic=False,
)


def detect_capabilities(instrument: "Instrument") -> Capabilities:
    """Return the instrument's capabilities.

    Part 1 stub: trusts whatever profile the backend advertises (the mock and
    the rigol wrapper both expose :attr:`Instrument.capabilities`) and otherwise
    falls back to :data:`DS1104Z_BASE`.

    TODO: Part 2 — replace with a real ``*OPT?`` query routed through the
    library and parse installed options into :attr:`Capabilities.options`.
    """

    caps = getattr(instrument, "capabilities", None)
    if isinstance(caps, Capabilities):
        return caps
    return DS1104Z_BASE
