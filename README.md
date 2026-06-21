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

Part 1 (this scaffold) runs entirely against a `MockInstrument` — no hardware,
no live VISA. Library completion (Part 2) and hardware-in-the-loop wiring
(Part 3) are bench tasks. See `SCAFFOLD_TASK.md`.

## Quickstart

```bash
uv sync
uv run pytest          # all green against the mock, zero hardware
uv run scpi-mcp        # start the MCP server (mock backend by default)
```

## License

MIT
