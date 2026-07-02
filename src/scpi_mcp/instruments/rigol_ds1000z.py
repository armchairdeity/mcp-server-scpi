"""RigolDS1000Z backend — the live DS1000Z-series oscilloscope.

Wires the vendor-neutral :class:`Instrument` interface onto the forked
``rigol-ds1000z`` library's subsystem functions (``ieee``, ``measure``,
``acquire``, ``channel``, ``timebase``, ``trigger``, ``waveform``).

Hard rule preserved: **no raw-SCPI escape hatch in a tool method.** Every
capability calls a named library subsystem function. The only raw strings live
in the tiny transport adapter below (``_SocketOscope``), which is the transport
seam — the equivalent of the library's own ``Rigol_DS1000Z.write/query`` — not
the tool layer.

Transport is a raw TCP socket (``TCPIP::<ip>::5555::SOCKET``) opened via the
pure-python VISA backend. On the bench link VXI-11/``INSTR`` proved unreliable
(RPC handshake stalls); the socket is fast and stable. See
``transport/connect.py`` for construction.
"""

from __future__ import annotations

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

# Our vendor-neutral measurement kinds → (DS1000Z :MEASure item mnemonic, unit).
_ITEM: dict[MeasurementKind, tuple[str, str]] = {
    MeasurementKind.VPP: ("VPP", "V"),
    MeasurementKind.VRMS: ("VRMS", "V"),
    MeasurementKind.FREQUENCY: ("FREQuency", "Hz"),
    MeasurementKind.PERIOD: ("PERiod", "s"),
    MeasurementKind.DUTY: ("PDUTy", "%"),
    MeasurementKind.RISE_TIME: ("RTIMe", "s"),
    MeasurementKind.FALL_TIME: ("FTIMe", "s"),
}

# Our slope names → the library/scope tokens.
_SLOPE = {"rising": "POS", "falling": "NEG"}

# Our free-text acquisition types → :ACQuire:TYPE tokens.
_ACQ_TYPE = {
    "normal": "NORM",
    "average": "AVER",
    "peak": "PEAK",
    "hres": "HRES",
    "high_resolution": "HRES",
}


class _SocketOscope:
    """Duck-typed device the library subsystem functions expect.

    Provides ``write``/``query``/``read`` over an injected pyvisa resource plus
    the acquisition-control verbs (``run``/``stop``/``single``/``tforce``) the
    library binds on its own device class. This is the transport primitive; it
    is the only place raw command strings appear.
    """

    def __init__(self, visa_rsrc) -> None:
        self.visa_rsrc = visa_rsrc

    def write(self, cmd: str) -> None:
        # Append *WAI so a subsequent read-back reflects the completed command,
        # and pace commands: the raw socket desyncs (a query reads one response
        # behind) under rapid write/query sequences without a small beat.
        self.visa_rsrc.write(cmd + ";*WAI")
        time.sleep(0.01)

    def read(self) -> str:
        return str(self.visa_rsrc.read()).strip()

    def query(self, cmd: str, delay=None) -> str:
        # Resync before querying: on the raw socket a rapid config loop can leave
        # a stale reply buffered, which would make the next query read one
        # response behind (empty/garbled). Discard anything pending (fast, via a
        # short timeout), then issue our query with a small write→read delay.
        rsrc = self.visa_rsrc
        saved = rsrc.timeout
        try:
            rsrc.timeout = 15
            while True:
                try:
                    rsrc.read()
                except Exception:
                    break
        finally:
            rsrc.timeout = saved
        return str(rsrc.query(cmd, delay=0.02 if delay is None else delay)).strip()

    # -- acquisition-control device verbs ---------------------------------
    def run(self) -> None:
        self.write(":RUN")

    def stop(self) -> None:
        self.write(":STOP")

    def single(self) -> None:
        self.write(":SING")

    def tforce(self) -> None:
        self.write(":TFOR")

    def close(self) -> None:
        self.visa_rsrc.close()


class RigolDS1000Z(Instrument):
    """Live backend for a DS1000Z-series scope over the forked library."""

    def __init__(
        self,
        device: _SocketOscope,
        *,
        capabilities: Capabilities = DS1104Z_BASE,
    ) -> None:
        # ``device`` is an opened, duck-typed transport (see transport layer).
        # Injected rather than opened here so this class is unit-testable with a
        # fake device and holds no pyvisa import itself.
        self._dev = device
        self.capabilities = capabilities
        # Bind the library subsystem functions lazily — importing the library is
        # only required when a live backend is actually constructed.
        from rigol_ds1000z.src.acquire import acquire
        from rigol_ds1000z.src.channel import channel
        from rigol_ds1000z.src.ieee import ieee
        from rigol_ds1000z.src.measure import measure
        from rigol_ds1000z.src.timebase import timebase
        from rigol_ds1000z.src.trigger import trigger
        from rigol_ds1000z.src.waveform import waveform

        self._ieee = ieee
        self._measure = measure
        self._acquire = acquire
        self._channel = channel
        self._timebase = timebase
        self._trigger = trigger
        self._waveform = waveform

    # -- identity ----------------------------------------------------------
    def identify(self) -> InstrumentIdentity:
        idn = self._ieee(self._dev).idn  # "RIGOL TECHNOLOGIES,DS1104Z,<sn>,<fw>"
        parts = [p.strip() for p in str(idn).split(",")]
        parts += [""] * (4 - len(parts))
        return InstrumentIdentity(
            vendor=parts[0],
            model=parts[1],
            serial=parts[2],
            firmware=parts[3],
        )

    def close(self) -> None:
        try:
            self._dev.close()
        except Exception:  # pragma: no cover - best effort
            pass

    # -- measurement -------------------------------------------------------
    def measure(self, channel: int, kind: MeasurementKind) -> Measurement:
        item, unit = _ITEM[kind]
        result = self._measure(self._dev, source=channel, item=item)
        value = float(result.value)
        # The DS1000Z returns duty as a fraction (0.505 = 50.5%); our interface
        # and the mock use percent. Scale valid readings to percent; leave the
        # NaN / 9.9e37 "no measurement" sentinels untouched.
        if kind is MeasurementKind.DUTY and value == value and abs(value) < 9e37:
            value *= 100.0
        return Measurement(channel=channel, kind=kind, value=value, unit=unit)

    # -- capture -----------------------------------------------------------
    def _read_waveform(
        self, channel: int, mode: str, label: str, *, stop: int | None = None
    ) -> Waveform:
        wf = self._waveform(
            self._dev,
            source=channel,
            mode=mode,
            format="BYTE",
            start=1 if stop else None,
            stop=stop,
        )
        raw = list(wf.data or [])
        # DS1000Z BYTE → volts: (raw - yorigin - yreference) * yincrement.
        yinc, yorig, yref = wf.yincrement, wf.yorigin, wf.yreference
        volts = [(b - yorig - yref) * yinc for b in raw]
        xinc, xorig, xref = wf.xincrement, wf.xorigin, wf.xreference
        times = [(i - xref) * xinc + xorig for i in range(len(raw))]
        sample_rate = (1.0 / xinc) if xinc else 0.0
        return Waveform(
            channel=channel,
            time=times,
            volts=volts,
            sample_rate=sample_rate,
            source=label,
        )

    def capture_screen(self, channel: int) -> Waveform:
        return self._read_waveform(channel, mode="NORM", label="screen")

    def capture_memory(self, channel: int, points: int | None = None) -> Waveform:
        # Deep-memory reads require a stopped acquisition on the DS1000Z.
        self._dev.stop()
        return self._read_waveform(channel, mode="RAW", label="memory", stop=points)

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
        self._channel(
            self._dev,
            channel,
            display=enabled,
            scale=scale,
            offset=offset,
            coupling=coupling,
        )

    def set_timebase(
        self,
        *,
        scale: float | None = None,
        offset: float | None = None,
    ) -> None:
        self._timebase(self._dev, main_scale=scale, main_offset=offset)

    def set_trigger(self, config: TriggerConfig) -> None:
        self._trigger(
            self._dev,
            mode="EDGE",
            source=config.source,
            slope=_SLOPE.get(config.slope, "POS"),
            level=config.level,
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
        token = None
        if acq_type is not None:
            token = _ACQ_TYPE.get(acq_type.lower(), acq_type.upper()[:4])
        self._acquire(self._dev, type=token, memdepth=memory_depth)

    # -- settle ------------------------------------------------------------
    def settle(self, seconds: float) -> None:
        time.sleep(seconds)
