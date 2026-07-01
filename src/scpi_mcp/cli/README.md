# scpictl

Command-line interface for the SCPI instrument layer. Shares the same
Session / transport / instrument stack as the MCP server — no duplicated logic.

## Installation

```bash
uv pip install -e .
scpictl --help
```

## Global Options

```
scpictl [--mock] [--help] COMMAND [ARGS]...
```

| Option | Description |
|--------|-------------|
| `--mock` | Use `MockInstrument` — no real scope required. Also activated by `SCPI_MCP_MOCK=1` env var. |

`--mock` must come **before** the subcommand:
```bash
scpictl --mock capture        # correct
scpictl capture --mock        # wrong
```

---

## Commands

### `connect`

Connect to an instrument and report its identity and VISA resource string.

```bash
scpictl connect [--host IP]
```

```
RIGOL TECHNOLOGIES DS1104Z  SN:DS1ZA123456789  fw:00.04.04.SP4
Resource: TCPIP::192.168.2.2::INSTR
```

---

### `identify`

Report instrument identity. Same as `connect` but supports `--format json`.

```bash
scpictl identify [--host IP] [--format text|json]
```

---

### `caps`

Report instrument capabilities: channel count, bandwidth, installed options.

```bash
scpictl caps [--host IP]
```

```json
{
  "ok": true,
  "model": "DS1104Z",
  "analog_channels": 4,
  "channels": [1, 2, 3, 4],
  "bandwidth_mhz": 100,
  "has_source": false,
  "has_logic": false
}
```

---

### `capture`

Capture a measurement snapshot for one or more channels. **This is the primary
launchd target for `scope-monitor`.**

```bash
scpictl capture [CHANNELS...] [OPTIONS]
```

Each invocation: connects → takes a snapshot → writes output → exits.

**Arguments**

| Argument | Description |
|----------|-------------|
| `CHANNELS` | Channel numbers to capture (default: all channels the instrument reports) |

**Options**

| Option | Default | Description |
|--------|---------|-------------|
| `--host`, `-h` | — | Instrument IP or hostname |
| `--output`, `-o` | — | CSV file path; appends rows, writes header only on first run |
| `--session-id`, `-s` | `YYYYMMDD-HHMMSS` | Tag to group related captures in the log |
| `--format`, `-f` | `rows` (stdout) / `csv` (file) | Output format: `rows`, `csv`, or `json` |
| `--header` | off | Print column labels before the first row (rows format only) |

**Output formats**

`rows` — default for stdout. SI-scaled, right-aligned columns, no header noise:
```
2026-06-27T02:20:58Z      ch1    1.000kHz     1.000ms    2.000V   707.1mV    50.0%
2026-06-27T02:20:58Z      ch2    2.000kHz   500.000µs    2.000V   707.1mV    50.0%
```

With `--header`:
```
timestamp                  ch        freq      period       vpp      vrms     duty
2026-06-27T02:20:58Z      ch1    1.000kHz     1.000ms    2.000V   707.1mV    50.0%
```

`csv` — default when `--output` is given. Machine-readable, full precision:
```
timestamp,session_id,channel,frequency,period,vpp,vrms,duty
2026-06-27T02:20:58.766+00:00,20260627-022058,1,1000.0,0.001,2.0,0.707,50.0
```

`json` — pipe-friendly:
```bash
scpictl capture -f json | jq '.[].frequency'
scpictl capture -f json | jq '.[] | select(.channel == 2)'
scpictl capture -f json | jq '[.[] | {ch: .channel, vpp: .vpp}]'
```

**Measurements captured**

| Column | Unit | Description |
|--------|------|-------------|
| `frequency` | Hz | Signal frequency |
| `period` | s | Signal period |
| `vpp` | V | Peak-to-peak voltage |
| `vrms` | V | RMS voltage |
| `duty` | % | Duty cycle |

Unavailable measurements (instrument sentinel `9.9e37`) appear as `—` in rows
format, empty in CSV, and `null` in JSON.

**Examples**

```bash
# Watch all channels scroll — bench monitoring
scpictl capture

# Channels 1 and 2, with column labels on first line
scpictl capture 1 2 --header

# Log to CSV file indefinitely (launchd fires this every N seconds)
scpictl capture --output ~/Documents/Claude/scope-monitor.csv

# Two tagged sessions appended to the same file
scpictl capture -o log.csv -s SESSION-A
scpictl capture -o log.csv -s SESSION-B

# Pipe to jq
scpictl capture -f json | jq '.[].vpp'
```

---

### `measure`

Take a single measurement on one channel.

```bash
scpictl measure CHANNEL KIND [--host IP] [--format text|json]
```

Valid kinds: `vpp`, `vrms`, `frequency`, `period`, `duty`, `rise_time`, `fall_time`

```bash
scpictl measure 1 vpp
# ch1  vpp: 3.300 V

scpictl measure 2 frequency --format json
```

---

### `snapshot`

Take a full measurement snapshot (freq, period, vpp, vrms, duty) on one channel.

```bash
scpictl snapshot CHANNEL [--host IP] [--format text|json]
```

```
Channel 1:
  frequency       1.000kHz  Hz
  period          1.000ms   s
  vpp             2.000V    V
  vrms            707.1mV   V
  duty            50.0%     %
```

---

### `characterize`

Full signal characterization: probe → vertical fit → horizontal fit →
trigger hunt → measure. Returns a structured result.

```bash
scpictl characterize CHANNEL [--host IP]
```

> **Note:** `characterize_signal` is stubbed in Part 1 of the server build and
> fully implemented in Part 3 once the `rigol-ds1000z` hardware backend is wired
> up. It currently validates the channel and returns the stage plan.

---

## Connecting to a Real Scope

By default, `scpictl` runs the discovery cascade: USB enumerate → LAN broadcast
→ fail. Pass `--host` to target a specific instrument:

```bash
scpictl --host 192.168.2.2 capture
scpictl --host 192.168.2.2 capture 1 2 --output ~/scope.csv
```

The `--host` option is per-command (not global), since each invocation is
self-contained.

---

## launchd Integration (scope-monitor)

`scpictl capture --output FILE` is designed to be the atomic unit fired by a
launchd plist on a schedule. Each invocation is stateless — connect, capture,
append, exit. The `/scope-monitor` slash command generates the plist.

Example plist fragment:
```xml
<key>ProgramArguments</key>
<array>
  <string>/path/to/scpictl</string>
  <string>--host</string>
  <string>192.168.2.2</string>
  <string>capture</string>
  <string>--output</string>
  <string>/Users/you/Documents/Claude/scope-monitor.csv</string>
  <string>--session-id</string>
  <string>MY-SESSION</string>
</array>
<key>StartInterval</key>
<integer>5</integer>
```

---

## Development / CI (No Hardware)

```bash
# Env var — useful in scripts
SCPI_MCP_MOCK=1 scpictl capture

# Flag — explicit
scpictl --mock capture
scpictl --mock capture 1 2 --header
scpictl --mock capture -f json | jq '.[].frequency'
```
