"""FLAGSHIP tool: goal-level ``characterize_signal(channel)``.

This is the headline capability — hand it a channel and it figures out the
signal: find a stable trigger, scale the display to fit, then report a full
measurement set with confidence. It is the reason ``scpi-mcp`` is "oscilloscope
expertise" and not just "a SCPI wire."

**Part 1 stubs the loop.** The control flow and the settle-and-verify intent are
written out below so Part 3 can fill in the body against real hardware; the tool
itself returns a structured "not implemented" result so the scaffold stays
honest and testable. No measurement/trigger logic actually runs here yet.

The loop (to be implemented in Part 3)
--------------------------------------
1. **Probe** — capture a screen waveform; rough-estimate amplitude & frequency.
2. **Vertical fit** — set channel scale/offset so the signal fills ~6 divisions.
       → settle, then re-capture and VERIFY it actually fits (clipping? too
         small?). Adjust and repeat, bounded, before trusting any reading.
3. **Horizontal fit** — set the time base to show a handful of periods.
       → settle, re-measure frequency, VERIFY stability across a couple reads.
4. **Trigger hunt** — set an edge trigger near mid-amplitude; if unstable, walk
       the level / flip the slope / nudge the time base (trigger-hunting tactics
       completed in the library's TRIGger subsystem, Part 2).
       → settle, VERIFY the trigger holds before measuring.
5. **Characterize** — take the full measurement snapshot (Vpp, Vrms, freq,
       period, duty, rise/fall), each settled-and-verified, and report with a
       confidence flag.

Settle-and-verify is the spine of every step: the library inserts sleeps on some
commands (reset, autoscale) and config changes need extra settle time before a
measurement is valid. The loop must ``instrument.settle(...)`` and re-read to
confirm the change took effect rather than assuming an instant response.
"""

from __future__ import annotations

from typing import Any

from ..config import PermissionTier, Session, requires
from . import guarded

# Bound on the adjust→settle→verify iterations per stage (used in Part 3).
MAX_SETTLE_ITERATIONS = 5
# Default settle window after a config change before re-measuring (seconds).
DEFAULT_SETTLE_S = 0.2


@requires(PermissionTier.READ_CONFIG)
def characterize_signal_impl(session: Session, channel: int) -> dict[str, Any]:
    """Characterize the signal on ``channel`` (FLAGSHIP — stubbed in Part 1).

    Validates the channel against the connected instrument so the scaffold is
    exercised end-to-end, then returns a structured not-implemented result that
    names the stages and the settle-and-verify contract. The real loop is wired
    in Part 3 once the library's MEASure/ACQuire/TRIGger subsystems exist.
    """
    inst = session.require_instrument()
    # Touch the instrument so the channel range is validated even in the stub.
    inst.capture_screen(channel)

    # TODO: Part 3 — implement the probe → vertical fit → horizontal fit →
    # trigger hunt → characterize loop described in this module's docstring,
    # with inst.settle(DEFAULT_SETTLE_S) + re-verify after each adjustment,
    # bounded by MAX_SETTLE_ITERATIONS.
    return {
        "ok": True,
        "implemented": False,
        "channel": channel,
        "stages": [
            "probe",
            "vertical_fit",
            "horizontal_fit",
            "trigger_hunt",
            "characterize",
        ],
        "settle_and_verify": {
            "default_settle_s": DEFAULT_SETTLE_S,
            "max_iterations": MAX_SETTLE_ITERATIONS,
            "contract": "settle, then re-measure to verify each adjustment took",
        },
        "note": "characterize_signal loop is stubbed in Part 1; wired in Part 3.",
    }


def register(mcp: Any, session: Session) -> None:
    mcp.tool(name="characterize_signal")(guarded(session, characterize_signal_impl))
