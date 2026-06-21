"""Thin wrapper over the (complete) ``rigol-ds1000z`` library.

Hard rule: **no raw-SCPI escape hatch.** Every method here calls a clean,
named method on the library object — never a raw command string. Where the
library subsystem is still a Part 2 gap (``MEASure``, ``ACQuire``, and the
remainder of ``TRIGger``), the method is **stubbed** and raises
``NotImplementedError`` with a ``# TODO: Part 2`` note. We do *not* reach around
the library with raw SCPI to "make it work" — the fix is in the library.

The library is an optional dependency in Part 1 (the ``hardware`` extra). It is
imported lazily so the package imports cleanly with zero hardware; only
*constructing* a ``RigolDS1000Z`` requires it. Part 1 tests exercise the mock,
not this backend.

Transport (``transport/``) resolves the VISA resource string and passes it in.
The library accepts a VISA resource and only self-searches when none is given —
so discovery stays entirely in our transport layer.
"""

from __future__ import annotations

from ..capabilities import DS1104Z_BASE, Capabilities
from .base import (
    Instrument,
    InstrumentIdentity,
    Measurement,
    MeasurementKind,
    TriggerConfig,
    Waveform,
)

_PART2 = "TODO: Part 2 — implement in the forked rigol-ds1000z library, then wire here."


def _load_library():
    """Import the library lazily; give an actionable error if it's absent."""
    try:
        import rigol_ds1000z  # type: ignore  # noqa: F401

        return rigol_ds1000z
    except ImportError as exc:  # pragma: no cover - exercised only with hardware extra
        raise ImportError(
            "the 'rigol-ds1000z' library is not installed. It is delivered in "
            "Part 2; install the 'hardware' extra (`uv sync --extra hardware`) "
            "once the fork is available. Part 1 uses the mock backend instead."
        ) from exc


class RigolDS1000Z(Instrument):
    """DS1000Z-series backend.

    Part 1 scaffolds the structure; the methods that depend on Part 2 library
    subsystems are stubbed. Hardware wiring + validation happen in Part 3.
    """

    def __init__(
        self,
        resource: str,
        *,
        capabilities: Capabilities = DS1104Z_BASE,
    ) -> None:
        self.resource = resource
        self.capabilities = capabilities
        self._lib = _load_library()
        # The library accepts the VISA resource string we resolved in transport
        # and only self-searches when given none — so we keep discovery ours.
        # TODO: Part 3 — confirm the exact constructor/method names against the
        # completed fork's public API and adjust the calls below to match.
        self._dev = self._lib.Rigol_DS1000Z(resource)  # type: ignore[attr-defined]

    # -- identity ----------------------------------------------------------
    def identify(self) -> InstrumentIdentity:
        idn = self._dev.idn  # clean library property over *IDN?
        return InstrumentIdentity(
            vendor=idn.vendor,
            model=idn.model,
            serial=idn.serial,
            firmware=idn.firmware,
        )

    def close(self) -> None:
        self._dev.close()

    # -- measurement (MEASure — Part 2 gap, highest priority) -------------
    def measure(self, channel: int, kind: MeasurementKind) -> Measurement:
        # The :MEASure subsystem is not yet implemented in the library.
        raise NotImplementedError(f"measure() — {_PART2}")

    # -- capture -----------------------------------------------------------
    def capture_screen(self, channel: int) -> Waveform:
        # :WAVeform is implemented in the upstream library; mapping its return
        # onto our Waveform type is Part 3 wiring (needs a live read to verify).
        raise NotImplementedError("capture_screen() — wiring deferred to Part 3")

    def capture_memory(self, channel: int, points: int | None = None) -> Waveform:
        raise NotImplementedError("capture_memory() — wiring deferred to Part 3")

    # -- channel / timebase / trigger -------------------------------------
    def set_channel(
        self,
        channel: int,
        *,
        enabled: bool | None = None,
        scale: float | None = None,
        offset: float | None = None,
        coupling: str | None = None,
    ) -> None:
        # :CHANnel exists upstream; wiring/verification is Part 3.
        raise NotImplementedError("set_channel() — wiring deferred to Part 3")

    def set_timebase(
        self,
        *,
        scale: float | None = None,
        offset: float | None = None,
    ) -> None:
        # :TIMebase exists upstream; wiring/verification is Part 3.
        raise NotImplementedError("set_timebase() — wiring deferred to Part 3")

    def set_trigger(self, config: TriggerConfig) -> None:
        # :TRIGger is only PARTIAL in the library today.
        raise NotImplementedError(f"set_trigger() — {_PART2}")

    # -- acquisition control (ACQuire — Part 2 gap) -----------------------
    def run(self) -> None:
        raise NotImplementedError(f"run() — {_PART2}")

    def stop(self) -> None:
        raise NotImplementedError(f"stop() — {_PART2}")

    def single(self) -> None:
        raise NotImplementedError(f"single() — {_PART2}")

    def force_trigger(self) -> None:
        raise NotImplementedError(f"force_trigger() — {_PART2}")

    def set_acquisition(
        self,
        *,
        acq_type: str | None = None,
        memory_depth: int | None = None,
    ) -> None:
        # The :ACQuire subsystem is not yet implemented in the library.
        raise NotImplementedError(f"set_acquisition() — {_PART2}")

    # -- settle ------------------------------------------------------------
    def settle(self, seconds: float) -> None:
        # The library already inserts sleeps on reset/autoscale; this adds the
        # extra post-config settle the flagship loop needs. Real wait in Part 3.
        # TODO: Part 3 — back this with the library's own wait/opc helper.
        import time

        time.sleep(seconds)
