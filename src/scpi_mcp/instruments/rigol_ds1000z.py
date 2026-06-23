"""Thin wrapper over the ``rigol-ds1000z`` library.

Hard rule: **no raw-SCPI escape hatch.** Every method here calls a clean,
named method on the library object (``measure``, ``acquire``, ``channel``,
``timebase``, ``trigger``, ``waveform``, ``ieee``, ``run/stop/single/tforce``)
— never a raw command string. All SCPI knowledge lives in the library; this
file only maps the vendor-neutral :class:`Instrument` interface onto those
named calls and translates value types.

The library is an optional dependency (the ``hardware`` extra), imported lazily
so the package imports cleanly with zero hardware; only *constructing* a
``RigolDS1000Z`` requires it. The mock backend covers everything else.

Transport (``transport/``) resolves the VISA resource string and passes it in;
discovery stays entirely in our transport layer.
"""

from __future__ import annotations

import math
import time

from ..capabilities import DS1104Z_BASE, Capabilities
from .base import (
    Instrument,
    InstrumentIdentity,
    Measurement,
    MeasurementKind,
    TriggerConfig,
    Waveform,
)

# Rigol returns this sentinel (~9.9e37) when a measurement is invalid — e.g. the
# signal is off-screen or the channel is not displayed. We surface it as NaN at
# this vendor-neutral boundary so the tools layer never sees the raw sentinel.
_RIGOL_INVALID = 9.9e37

# DS1000Z automatic-measurement item mnemonics for each neutral MeasurementKind.
_MEASURE_ITEM: dict[MeasurementKind, str] = {
    MeasurementKind.VPP: "VPP",
    MeasurementKind.VRMS: "VRMS",
    MeasurementKind.FREQUENCY: "FREQuency",
    MeasurementKind.PERIOD: "PERiod",
    MeasurementKind.DUTY: "PDUTy",
    MeasurementKind.RISE_TIME: "RTIMe",
    MeasurementKind.FALL_TIME: "FTIMe",
}

# Unit per measurement kind (vendor-neutral). DS1000Z reports duty as a percent.
_MEASURE_UNIT: dict[MeasurementKind, str] = {
    MeasurementKind.VPP: "V",
    MeasurementKind.VRMS: "V",
    MeasurementKind.FREQUENCY: "Hz",
    MeasurementKind.PERIOD: "s",
    MeasurementKind.DUTY: "%",
    MeasurementKind.RISE_TIME: "s",
    MeasurementKind.FALL_TIME: "s",
}

# Neutral acquisition-type names → DS1000Z :ACQuire:TYPE tokens.
_ACQ_TYPE: dict[str, str] = {
    "normal": "NORM",
    "average": "AVER",
    "peak": "PEAK",
    "high_resolution": "HRES",
    "hres": "HRES",
}

# DS1000Z reads at most this many points per :WAVeform:DATA? transfer.
_RAW_CHUNK = 250_000

# LAN VXI-11 can be flaky / high-latency; open with retries and a generous I/O
# timeout. Mirrors the behavior the bench V&V harness relies on.
_OPEN_RETRIES = 5
_VISA_TIMEOUT_MS = 20_000


def _load_library():
    """Import the library lazily; give an actionable error if it's absent."""
    try:
        import rigol_ds1000z  # type: ignore  # noqa: F401

        return rigol_ds1000z
    except ImportError as exc:  # pragma: no cover - exercised only with hardware extra
        raise ImportError(
            "the 'rigol-ds1000z' library is not installed. Install the "
            "'hardware' extra: `uv pip install -e \".[hardware]\"`. The mock "
            "backend works without it."
        ) from exc


class RigolDS1000Z(Instrument):
    """DS1000Z-series backend over the forked ``rigol-ds1000z`` library."""

    def __init__(
        self,
        resource: str,
        *,
        capabilities: Capabilities = DS1104Z_BASE,
    ) -> None:
        self.resource = resource
        self.capabilities = capabilities
        self._lib = _load_library()
        self._dev = self._connect(resource)

    def _connect(self, resource: str):
        """Construct the library device for ``resource`` and open the link.

        The library's constructor self-discovers a VISA backend by matching the
        resource against ``find_visas()``; a LAN/TCPIP resource often isn't
        enumerated there, which would leave ``visa_backend`` unset. We pin the
        resource and a sensible backend explicitly, then open with retries.
        """
        dev = self._lib.Rigol_DS1000Z(resource)  # type: ignore[attr-defined]
        dev.visa_name = resource
        if getattr(dev, "visa_backend", None) is None:
            dev.visa_backend = "@py"

        last: Exception | None = None
        for attempt in range(_OPEN_RETRIES):
            try:
                dev.open()
                dev.visa_rsrc.timeout = _VISA_TIMEOUT_MS
                return dev
            except Exception as exc:  # noqa: BLE001 - retry any transport error
                last = exc
                time.sleep(1.0 + attempt)
        raise ConnectionError(
            f"failed to open VISA resource {resource!r} after {_OPEN_RETRIES} "
            f"attempts: {last}"
        ) from last

    # -- identity ----------------------------------------------------------
    def identify(self) -> InstrumentIdentity:
        # Clean library path over *IDN? (the ``ieee`` helper always queries it).
        raw = self._dev.ieee().idn
        vendor, model, serial, firmware = (
            part.strip() for part in (raw.split(",", 3) + ["", "", "", ""])[:4]
        )
        return InstrumentIdentity(
            vendor=vendor, model=model, serial=serial, firmware=firmware
        )

    def close(self) -> None:
        self._dev.close()

    # -- measurement -------------------------------------------------------
    def measure(self, channel: int, kind: MeasurementKind) -> Measurement:
        self._require_channel(channel)
        item = _MEASURE_ITEM[kind]
        value = self._dev.measure(source=channel, item=item).value
        if value is None or math.isnan(value) or abs(value) >= _RIGOL_INVALID:
            value = math.nan  # invalid / unavailable measurement
        elif kind is MeasurementKind.DUTY:
            # The scope reports duty as a 0–1 ratio; surface it as a percent to
            # match the "%" unit (and the mock backend).
            value *= 100.0
        return Measurement(
            channel=channel, kind=kind, value=float(value), unit=_MEASURE_UNIT[kind]
        )

    # -- capture -----------------------------------------------------------
    def capture_screen(self, channel: int) -> Waveform:
        self._require_channel(channel)
        wf = self._dev.waveform(source=channel, mode="NORM", format="BYTE")
        x, y = self._lib.process_waveform(wf)
        return self._to_waveform(channel, wf, x, y, source="screen")

    def capture_memory(self, channel: int, points: int | None = None) -> Waveform:
        self._require_channel(channel)
        # Deep-memory (RAW) reads require the scope to be stopped.
        self._dev.stop()
        # Read the full acquisition memory unless a point count is requested.
        if points is None:
            depth = self._dev.acquire().memdepth  # :ACQ:MDEP? — int or "AUTO"
            try:
                points = int(depth)
            except (TypeError, ValueError):
                points = 12_000  # MDEP == AUTO / unknown — a sane default depth

        volts: list[float] = []
        xinc = 0.0
        xorigin = 0.0
        start = 1
        # Chunk the read: the scope caps a single :WAVeform:DATA? transfer. An
        # explicit start/stop per chunk avoids relying on a stale :WAV:STOP.
        while len(volts) < points:
            stop = min(start + _RAW_CHUNK - 1, points)
            chunk = self._dev.waveform(
                source=channel, mode="RAW", format="BYTE", start=start, stop=stop
            )
            _, yc = self._lib.process_waveform(chunk)
            if len(yc) == 0:
                break  # instrument returned nothing further; stop cleanly
            if not volts:
                xinc, xorigin = chunk.xincrement, chunk.xorigin
            volts.extend(float(v) for v in yc)
            start = len(volts) + 1

        time_axis = [i * xinc + xorigin for i in range(len(volts))]
        sample_rate = 1.0 / xinc if xinc else 0.0
        return Waveform(
            channel=channel,
            time=time_axis,
            volts=volts,
            sample_rate=sample_rate,
            source="memory",
        )

    def _to_waveform(self, channel: int, wf, x, y, *, source: str) -> Waveform:
        sample_rate = 1.0 / wf.xincrement if wf.xincrement else 0.0
        return Waveform(
            channel=channel,
            time=[float(t) for t in x],
            volts=[float(v) for v in y],
            sample_rate=sample_rate,
            source=source,
        )

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
        self._require_channel(channel)
        kwargs: dict[str, object] = {}
        if enabled is not None:
            kwargs["display"] = enabled
        if scale is not None:
            kwargs["scale"] = scale
        if offset is not None:
            kwargs["offset"] = offset
        if coupling is not None:
            kwargs["coupling"] = coupling
        self._dev.channel(channel, **kwargs)

    def set_timebase(
        self,
        *,
        scale: float | None = None,
        offset: float | None = None,
    ) -> None:
        kwargs: dict[str, object] = {}
        if scale is not None:
            kwargs["main_scale"] = scale
        if offset is not None:
            kwargs["main_offset"] = offset
        self._dev.timebase(**kwargs)

    def set_trigger(self, config: TriggerConfig) -> None:
        slope = "POS" if config.slope == "rising" else "NEG"
        # AUTO sweep keeps the scope acquiring/measuring even if the edge isn't
        # found, which the (measurement-based) verify steps depend on.
        self._dev.trigger(
            mode="EDGE",
            source=config.source,
            slope=slope,
            level=config.level,
            sweep="AUTO",
        )

    # -- acquisition control ----------------------------------------------
    def run(self) -> None:
        self._dev.run()

    def stop(self) -> None:
        self._dev.stop()

    def single(self) -> None:
        self._dev.single()

    def force_trigger(self) -> None:
        self._dev.tforce()

    def set_acquisition(
        self,
        *,
        acq_type: str | None = None,
        memory_depth: int | None = None,
    ) -> None:
        kwargs: dict[str, object] = {}
        if acq_type is not None:
            kwargs["type"] = _ACQ_TYPE.get(acq_type.lower(), acq_type.upper())
        if memory_depth is not None:
            kwargs["memdepth"] = memory_depth
        self._dev.acquire(**kwargs)

    # -- settle ------------------------------------------------------------
    def settle(self, seconds: float) -> None:
        # Synchronize on operation-complete rather than blind-sleeping: the
        # library's query() appends ;*WAI and *OPC? returns only once pending
        # operations finish. Fall back to a sleep if the link hiccups.
        try:
            self._dev.query("*OPC?")
        except Exception:  # noqa: BLE001 - settle must never raise
            time.sleep(seconds)

    # -- helpers -----------------------------------------------------------
    def _require_channel(self, channel: int) -> None:
        if channel not in self.capabilities.channel_ids():
            valid = ", ".join(str(c) for c in self.capabilities.channel_ids())
            raise ValueError(f"channel {channel} out of range (have: {valid})")
