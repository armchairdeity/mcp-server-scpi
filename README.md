# scpi-mcp

**LabLink gives agents a SCPI wire; scpi-mcp gives agents oscilloscope expertise.**

`scpi-mcp` is a [Model Context Protocol](https://modelcontextprotocol.io) server
that lets an agent *operate an oscilloscope* — not just push SCPI strings at one.
It exposes goal-level tools (capture this signal, measure that, characterize a
channel) backed by a clean, instrument-agnostic interface. All vendor SCPI lives
in the underlying instrument library; the MCP layer stays a thin, uniform wrapper
with **no raw-SCPI escape hatch**.

```
        .-"""-. 
       / .===. \      Skippi  🧚‍♂️
       \/ 6 6 \/      the artistic scope gremlin
       ( \___/ )      "every waveform is a portrait of the magic pixies"
    ___ooo___ooo___
```

> **Skippi** is the mascot — the artistic gremlin who lives in the scope and
> paints pictures of the magic pixies (the ones who carry every electron down
> the probe). When you see a clean trace, that's Skippi's latest masterpiece.

## Scope

First instrument: **Rigol DS1054Z** (unlocked to DS1104Z base) — 4 analog
channels, 100 MHz. No `:SOURce` (function generator) or `:LA` (logic analyzer)
support. Reachable over USB or LAN (`TCPIP::<ip>::INSTR`).

## Architecture

- **`transport/`** — owns discovery. Enumerates USB, falls back to best-effort
  LAN auto-discovery, then to an IP prompt; resolves a single VISA *resource
  string* and hands it to the instrument layer. Discovery never leaks upward.
- **`instruments/`** — vendor-specific backends behind one abstract `base.py`
  interface. `rigol_ds1000z.py` is a thin wrapper over the (complete) library;
  `mock.py` implements the same interface with zero hardware. Adding an
  instrument is one new file here and **zero** changes to `tools/`.
- **`tools/`** — instrument-agnostic MCP tools that call only `base.py`.
- **`config.py`** — permission tiers (`read_only` / `read_config` / `full`),
  enforced at the tool layer. The *server* refuses; the model never decides.

## Status

**Live hardware, active bench use.** The Rigol DS1054Z is connected and
scpi-mcp is driving real measurements — see [Skippi in the Wild](#skippi-in-the-wild)
for captures. The mock backend remains available for development and CI.

## Quickstart

```bash
uv sync
uv run pytest          # all green against the mock, zero hardware
uv run scpi-mcp        # start the MCP server (mock backend by default)
```

## Skippi in the Wild

Real captures from the bench, analyzed live via scpi-mcp.

### Power-off — relay coil with freewheel diode

**The setup:** A 24 V relay coil (with freewheel diode installed) powered from a
bench supply. Probed at the moment of power-off to observe inductive kickback.
CH1 watches the supply rail; CH2 sits across the freewheel diode.

**Prompts used:**

```
Grab the scope screen.
What are the min and max voltages on each channel?
Is that spike on CH2 actually 60 V, or is the scale messing with me?
```

scpi-mcp called `capture_screen` and `measure_snapshot`, then explained the
visual illusion: CH2 is set to 1 V/div, so its 5.36 V kickback spike fills
5+ of the 8 vertical divisions and *looks* enormous. CH1 is at 8 V/div, so
the 24 V rail only occupies ~3 divisions despite being far larger in absolute
terms. No 60 V spike — the freewheel diode clamped it cleanly to
V_supply + V_f ≈ 24.7 V, right where it should be.

![Power-off capture — relay coil, freewheel diode installed](docs/images/scope_poweroff_long.png)

*500 ms/div (5 s full sweep). CH1 yellow, 8 V/div: 24 V supply decaying from
26.9 V → 2.24 V. CH2 cyan, 1 V/div: freewheel diode kickback, max 5.36 V,
min −2.08 V.*

---

### Power-off — bare coil, no freewheel diode

**The setup:** The same 24 V relay coil, but with the freewheel diode *removed* —
a bare inductor. Powered from a bench supply (100 nF across the rail to tame
switch-mode ripple). Two 10x probes straddle the disconnect on the high side:
CH1 on the supply side, CH2 on the coil side. Power is cut by pulling the +
lead, and a single-shot trigger catches the unclamped kickback.

**Prompts used:**

```
Prime the scope for a single-shot on CH2 falling — I'll pull the + lead.
We didn't clear the clipping — reset V/div on CH2 and re-arm for another one-shot.
Got it — grab the screencap and give me the true peak.
```

scpi-mcp armed a single-shot falling-edge trigger on CH2, watched the trigger
status, and grabbed the screen plus both channel waveforms the instant it fired.
This time the *scale fought back the other way*: the kick kept overflowing the
window — it railed at ±130 V, then again at −304 V — so scpi-mcp stepped CH2
coarser to 100 V/div until the whole transient fit. With no freewheel diode to
absorb it, the collapsing field threw a **−436 V** spike with a **+240 V**
overshoot — a ~676 Vpp ring, roughly **18x** the 24 V rail — then bled off
exponentially back toward the rail over ~1 ms. Compare the clamped case above,
where the diode held the same coil to ≈24.7 V.

![Power-off capture — bare coil, freewheel diode removed](docs/images/scope_poweroff_bare_coil.png)

*200 µs/div. CH1 yellow, 20 V/div: supply side holds ~24 V with a small coupled
ring at the break. CH2 cyan, 100 V/div: bare-coil kickback — peak −436 V,
+240 V overshoot (~676 Vpp), then exponential bleed-back. No freewheel diode;
contrast the ≈24.7 V clamped result above.*

## License

MIT
