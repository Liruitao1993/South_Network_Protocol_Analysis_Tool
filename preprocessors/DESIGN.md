# CLI Preprocessor Framework — Design Document

## 1. Problem Statement

`main_gui.py` `parse_batch()` currently hardcodes three prefix-stripping methods
directly inside the `MainWindow` class:

| Method | Protocol | Logic |
|---|---|---|
| `_strip_csg_monitor_prefix` | CSG (idx 9) | Find `> 接收机 Has Get`, skip 15-byte monitor header |
| `_strip_gw_new_gen_prefix` | GW (idx 10) | Last colon → hex; optionally scan `0x11` for app-level |
| `_strip_csg_new_gen_frame_prefix` | CSG (idx 9) | Delegates to CSG monitor prefix or FC-header scan |

These are entangled with GUI state (`_csg_parse_level`, `_gw_parse_level`) and
inseparable from `MainWindow`. Every new log format requires editing `main_gui.py`.
The goal: **move all deterministic, non-LLM preprocessing into standalone CLI scripts
that the GUI invokes via subprocess**, achieving a plugin-like extensibility model.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  main_gui.py · parse_batch()                                   │
│                                                                 │
│  1. LLM Preprocess (optional, already exists)                  │
│  2. CLI Preprocess ──────┐                                     │
│  3. _clean_hex_input     │                                     │
│  4. _extract_frames_*    │                                     │
│  5. Per-frame parse_*    │                                     │
│                          ▼                                      │
│  ┌──────────────────────────────────────────────┐              │
│  │ PreprocessorRegistry.run(name, text, opts)   │              │
│  │   → subprocess.run([python, script, --flag])  │              │
│  │   → stdout = cleaned hex (one frame per line) │              │
│  └──────────────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

### Key Principles

1. **One script = one responsibility.** Each preprocessor does exactly one transformation.
2. **Unix pipe model.** stdin→stdout by default, `--file` option for direct file input.
3. **Self-describing.** Each script can print its own metadata (`--info`).
4. **Zero GUI dependency.** Scripts import only `re`, `sys`, `argparse` — no Qt.
5. **Composable.** Multiple preprocessors can be chained (GUI runs them sequentially).
6. **Future EXE-compatible.** Each script is a standalone entry point for PyInstaller.

---

## 3. Directory Structure

```
preprocessors/
├── __init__.py              # Registry + discovery
├── base.py                  # Shared constants & helpers (clean_hex, etc.)
├── extract_hex_frames.py    # Universal hex frame extractor
├── clean_csg_prefix.py      # CSG monitor prefix stripper (-> 接收机 Has Get)
├── clean_gw_prefix.py       # GW new gen prefix stripper (96..16 wrapper log)
├── extract_tcp_payload.py   # TCP application-layer payload extractor
├── classify_by_protocol.py  # Protocol classifier (output: tagged frames)
└── DESIGN.md                # This file
```

---

## 4. Metadata Convention

Every preprocessor script supports a `--info` flag that prints a JSON metadata
block. The registry uses this to build the GUI dropdown.

### `--info` Output Format

```json
{
  "name": "clean_csg_prefix",
  "display_name": "CSG 监控前缀剥离",
  "version": "1.0.0",
  "description": "剥离新一代载波协议监控日志前缀（-> 接收机 Has Get + 15字节监控头）",
  "input_format": "raw_log",
  "output_format": "hex_frames",
  "protocol_ids": [9],
  "cli_args": [
    {
      "name": "--parse-level",
      "type": "choice",
      "choices": ["auto", "fc_pb", "fc_only", "fc_efc", "app", "pb_only"],
      "default": "auto",
      "description": "解析级别（影响帧起始定位）"
    }
  ]
}
```

### Field Definitions

| Field | Values | Purpose |
|---|---|---|
| `input_format` | `raw_log` / `hex_clean` / `hex_frames` | What the script expects |
| `output_format` | `hex_clean` / `hex_frames` / `classified` | What it produces |
| `protocol_ids` | list of int | Which protocol indices this applies to (empty = universal) |
| `cli_args` | list | Extra CLI arguments the GUI should expose |

---

## 5. CLI Interface Spec

### Standard Invocation

```bash
# stdin mode (pipe)
echo "15:49:51 254 -> 接收机 Has Get ED A5 00 ..." | python preprocessors/clean_csg_prefix.py

# file mode
python preprocessors/clean_csg_prefix.py --file input.log

# with options
python preprocessors/clean_csg_prefix.py --parse-level app --file input.log

# metadata query
python preprocessors/clean_csg_prefix.py --info

# list all registered preprocessors (from __init__.py)
python -m preprocessors --list
```

### Standard Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Processing error (malformed input, etc.) |
| 2 | Usage error (bad args) |

### Standard Error Output

Errors go to stderr. stdout is **always** the cleaned output only — no banners,
no progress, no debug messages. This keeps pipe composition clean.

### Input/Output Contract

- **Input**: Raw log text, hex text, or pre-cleaned hex — depends on `input_format`.
- **Output**: Cleaned hex frames, **one frame per line**, uppercase hex, no separators.
  Each line is a complete frame ready for `_clean_hex_input` + protocol parsing.
- **Empty output** is valid (all input was noise). Exit code still 0.

---

## 6. Preprocessor Scripts — Detailed Design

### 6.1 `extract_hex_frames.py` — Universal Hex Extractor

**Purpose**: Extract all hex byte sequences from arbitrary log text. This is the
"catch-all" first pass that converts any log format into raw hex frames.

**Input**: `raw_log` — any text containing hex data mixed with timestamps, Chinese
text, metadata.

**Output**: `hex_frames` — one hex string per line, uppercase, even-length.

**Algorithm**:
1. For each input line, find contiguous hex-byte tokens (`[0-9A-Fa-f]{2}`).
2. Join tokens into a single hex string per line.
3. Drop lines with fewer than 4 hex characters (2 bytes — too short for any frame).
4. Ensure even byte alignment (trim trailing nibble if odd).

**Extra CLI args**: None.

**Key behavior**: This replaces the ad-hoc hex extraction scattered across
`_clean_hex_input` + `_extract_frames_for_protocol` for quick one-off use.
For protocol-specific extraction, use the dedicated preprocessors.

**Code logic** (mirrors existing `main_gui.py` patterns):
```python
import re, sys

def extract_hex_frames(text: str) -> str:
    out = []
    for line in text.splitlines():
        tokens = re.findall(r'[0-9A-Fa-f]{2}', line)
        if not tokens:
            continue
        hex_str = ''.join(tokens).upper()
        if len(hex_str) < 4:
            continue
        if len(hex_str) % 2 != 0:
            hex_str = hex_str[:-1]
        out.append(hex_str)
    return '\n'.join(out)
```

---

### 6.2 `clean_csg_prefix.py` — CSG Monitor Prefix Stripper

**Purpose**: Strip the CSG (南网新一代载波协议, index 9) monitor log prefix.
Extracts the real protocol frame from `-> 接收机 Has Get` formatted lines.

**Input**: `raw_log` — lines like:
```
15:49:51 254  -> 接收机 Has Get ED A5 00 00 02 EF 01 7E 4E 97 86 01 00 88 00 69 19 09 ...
```

**Output**: `hex_frames` — one hex string per line, starting from byte 16 onward
(real protocol data after 15-byte monitor header).

**Algorithm** (extracted from `MainWindow._strip_csg_monitor_prefix`):
1. Scan for `> 接收机 Has Get` marker in each line.
2. Skip lines without the marker (timestamps, test markers, Chinese text → discard).
3. After the marker, extract hex tokens.
4. Skip first 15 tokens (15-byte monitor header).
5. Join remaining tokens → protocol frame hex.

**Extra CLI args**: None (the CSG monitor prefix format is fixed).

**Critical invariant**: This must run BEFORE `_clean_hex_input` — the marker
contains Chinese characters and arrows that would be destroyed by hex cleaning.
The output of this script is still "log-ish" hex with spaces; `_clean_hex_input`
normalizes it downstream.

**Code logic**:
```python
import re, sys

CSG_MONITOR_PREFIX = "> 接收机 Has Get"
CSG_MONITOR_HEADER_BYTES = 15

def strip_csg_monitor_prefix(text: str) -> str:
    out_lines = []
    for line in text.splitlines():
        pos = line.find(CSG_MONITOR_PREFIX)
        if pos == -1:
            continue  # discard non-monitor lines
        after = line[pos + len(CSG_MONITOR_PREFIX):]
        tokens = re.findall(r'[0-9A-Fa-f]{1,2}', after)
        payload_tokens = tokens[CSG_MONITOR_HEADER_BYTES:]
        if payload_tokens:
            out_lines.append(' '.join(payload_tokens))
    return '\n'.join(out_lines)
```

---

### 6.3 `clean_gw_prefix.py` — GW New Gen Prefix Stripper

**Purpose**: Strip the GW (国网新一代双模协议, index 10) log prefix.
Extracts hex frames from `Line XXX: timestamp: metadata:hex_data` format.

**Input**: `raw_log` — lines like:
```
Line 339: 260718-111145-349: B1D[3] mrd:ar[75]:110300000132F303420D2305683D0043...
```

**Output**: `hex_frames` — one hex string per line.

**Algorithm** (extracted from `MainWindow._strip_gw_new_gen_prefix`):
1. Find last colon in each line → hex data follows.
2. Clean non-hex characters, uppercase.
3. If `--parse-level app`: scan for `0x11` byte to locate application layer start.
4. Drop lines shorter than 4 hex characters.

**Extra CLI args**:
| Arg | Type | Default | Description |
|---|---|---|---|
| `--parse-level` | choice | `auto` | `auto` / `app`. When `app`, scan for port byte `0x11` |

**Code logic**:
```python
import re, sys, argparse

def strip_gw_prefix(text: str, parse_level: str = "auto") -> str:
    out_lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        last_colon = line.rfind(':')
        hex_part = line[last_colon + 1:].strip() if last_colon >= 0 else line
        hex_clean = re.sub(r'[^0-9A-Fa-f]', '', hex_part).upper()
        if len(hex_clean) < 4:
            continue
        if parse_level == 'app':
            found = False
            i = 0
            while i < len(hex_clean) - 1:
                if hex_clean[i:i+2] == '11' and len(hex_clean) - i >= 8:
                    hex_clean = hex_clean[i:]
                    found = True
                    break
                i += 2
            if not found:
                continue
        out_lines.append(hex_clean)
    return '\n'.join(out_lines)
```

---

### 6.4 `extract_tcp_payload.py` — TCP Application Layer Payload Extractor

**Purpose**: Extract the TCP application-layer payload from TCP dump or TCP monitor
logs. Handles both raw TCP streams and the HPLC (96..16) wrapper format inside TCP.

**Input**: `raw_log` — TCP stream data, possibly with timestamps or TCP headers.

**Output**: `hex_frames` — extracted application-layer payloads, one per line.

**Algorithm**:
1. For each line, locate hex data (last colon or full line).
2. Clean to pure hex.
3. **96..16 wrapper detection**: If hex starts with `96` and ends with `16`,
   deframe: `96(1) + RSSI(1) + NTB(4) + LEN_META(2) + DATA(LEN) + CS(1) + 16(1)`.
   Extract DATA portion.
4. **EDA5 wrapper detection**: If hex starts with `EDA5`, extract the 15-byte TCP
   wrapper header, take the FC+payload from offset 30 hex chars onward.
5. **Plain TCP**: If hex starts with `68` (DL/T 645 family) or `ED` (PLC2.0),
   pass through as-is.
6. For each extracted payload, validate minimum length (≥8 hex chars = 4 bytes).

**Extra CLI args**:
| Arg | Type | Default | Description |
|---|---|---|---|
| `--wrapper` | choice | `auto` | `auto` / `hplc` (96..16) / `plc2` (ED..EE) / `none` |

**Code logic** (deframe 96..16):
```python
def deframe_hplc(hex_str: str) -> list:
    """Deframe 96..16 wrapper: 96(1)+RSSI(1)+NTB(4)+LEN_META(2)+DATA(LEN)+CS(1)+16(1)"""
    data = bytes.fromhex(hex_str)
    if data[0] != 0x96:
        return [hex_str]  # not wrapped, pass through
    i = 0
    frames = []
    while i < len(data):
        if data[i] != 0x96:
            break
        if i + 8 > len(data):
            break  # incomplete header
        rssi = data[i+1]
        # NTB is 4 bytes LE at offset 2-5 (not used for deframing)
        len_meta = data[i+6] | ((data[i+7] & 0x0F) << 8)  # 12-bit LEN
        total = 1 + 1 + 4 + 2 + len_meta + 1 + 1  # 96+RSSI+NTB+META+DATA+CS+16
        if i + total > len(data):
            break  # incomplete
        if data[i + total - 1] != 0x16:
            i += 1  # bad trailer, scan forward
            continue
        payload = data[i+8 : i+8+len_meta]
        frames.append(payload.hex().upper())
        i += total
    return frames
```

---

### 6.5 `classify_by_protocol.py` — Protocol Classifier

**Purpose**: Given a stream of extracted hex frames, classify each frame by its
likely protocol type. Useful when the input contains mixed protocols.

**Input**: `hex_frames` — one hex string per line (output of any earlier preprocessor).

**Output**: `classified` — each line is `PROTOCOL_NAME | hex_frame`:
```
CSG_NEW_GEN | 09A100000002017E4E9786010088006919...
GW_NEW_GEN  | 6811010101000168...
DLT645      | 6811010101000168...
UNKNOWN     | AABBCCDD...
```

**Algorithm** (signature-based classification):
| Signature | Protocol |
|---|---|
| Starts with `09`/`89` + low nibble ∈ {8,9,A,B} (FC header) | CSG_NEW_GEN |
| Starts with `68` + byte[1] ∈ typical DL/T length range | DLT645 / GDW / CSG |
| Starts with `7E` | HDLC |
| Starts with `ED` + frame_len at [1:3] LE + `EF` at [5] | PLC2_ED_EE |
| Starts with `96` | HPLC_MONITOR |
| Starts with `0001` (16-bit) | DLMS_WRAPPER |
| Starts with `11` (app layer port) | CSG_APP_LAYER |
| Byte[0] high nibble has MMTYPE match | GW_NEW_GEN |
| Otherwise | UNKNOWN |

**Extra CLI args**:
| Arg | Type | Default | Description |
|---|---|---|---|
| `--strict` | flag | false | Only output classified frames (drop UNKNOWN) |

---

## 7. Shared Helpers — `base.py`

Common utilities shared across preprocessors. Avoids duplication.

```python
# preprocessors/base.py
import re

def clean_hex(text: str) -> str:
    """Remove all non-hex chars, uppercase. Does NOT handle 0x prefix."""
    return re.sub(r'[^0-9A-Fa-f]', '', text).upper()

def clean_hex_keep_newlines(text: str) -> str:
    """Same but preserves newlines for multi-frame input."""
    return re.sub(r'[^0-9A-Fa-f\n]', '', text).upper()

def ensure_even(hex_str: str) -> str:
    """Trim trailing nibble if odd length."""
    return hex_str[:-1] if len(hex_str) % 2 != 0 else hex_str

def tokens_to_hex(tokens: list) -> str:
    """Join hex token list into a single uppercase hex string."""
    return ''.join(tokens).upper()
```

---

## 8. Registry — `__init__.py`

Discovers all `.py` files in the `preprocessors/` directory that have `--info`
support. Provides the GUI with a list of available preprocessors and their metadata.

```python
# preprocessors/__init__.py
import subprocess, json, sys
from pathlib import Path

PREPROCESSOR_DIR = Path(__file__).parent

def discover() -> list[dict]:
    """Run --info on each preprocessor script, return metadata list."""
    results = []
    for script in sorted(PREPROCESSOR_DIR.glob("clean_*.py")):
        # extract_hex_frames and classify_by_protocol also discovered
        if script.name.startswith("_") or script.name == "base.py":
            continue
        try:
            r = subprocess.run(
                [sys.executable, str(script), "--info"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                meta = json.loads(r.stdout)
                meta["_script"] = str(script)
                results.append(meta)
        except Exception:
            continue
    return results

def run_preprocessor(script_path: str, input_text: str,
                     extra_args: list[str] = None) -> str:
    """Run a preprocessor script with input_text on stdin, return stdout."""
    cmd = [sys.executable, script_path]
    if extra_args:
        cmd.extend(extra_args)
    r = subprocess.run(
        cmd, input=input_text, capture_output=True,
        text=True, timeout=30, encoding='utf-8'
    )
    if r.returncode != 0:
        raise RuntimeError(
            f"Preprocessor failed (exit {r.returncode}): {r.stderr.strip()}"
        )
    return r.stdout
```

### CLI Mode

```bash
# List all preprocessors
python -m preprocessors --list

# Output:
# clean_csg_prefix     CSG 监控前缀剥离     [protocol: 9]
# clean_gw_prefix      GW 新一代前缀剥离     [protocol: 10]
# extract_hex_frames   通用Hex帧提取         [all protocols]
# extract_tcp_payload  TCP载荷提取           [all protocols]
# classify_by_protocol 协议分类              [all protocols]
```

---

## 9. GUI Integration Plan

### 9.1 Preprocessor Selection Widget

Add a **collapsible preprocessor panel** to the batch parse tab, placed between
the input text area and the "开始批量解析" button. This panel mirrors the existing
LLM preprocess panel pattern (`llm_preprocess_widget.py`).

```
┌─ 预处理工具 ──────────────────────────────────────────────────┐
│  预处理步骤:                                                   │
│  ┌─────────────────────┐  ┌──────────┐  ┌──────────┐         │
│  │ CSG 监控前缀剥离    ▼│  │ + 添加   │  │ ▶ 执行   │         │
│  └─────────────────────┘  └──────────┘  └──────────┘         │
│                                                                │
│  ☑ L1: CSG 监控前缀剥离 (--parse-level auto)         [×]      │
│  ☑ L2: 通用Hex帧提取                                  [×]      │
│                                                                │
│  提示: 预处理按顺序执行，输出送入批量解析                      │
└────────────────────────────────────────────────────────────────┘
```

### 9.2 Widget Class

```python
class PreprocessStepWidget(QWidget):
    """A single preprocessor step in the pipeline."""

    def __init__(self, meta: dict, parent=None):
        super().__init__(parent)
        self.meta = meta
        self.enabled = QCheckBox(meta["display_name"])
        self.enabled.setChecked(True)

        # Dynamic arg controls based on meta["cli_args"]
        self.arg_widgets = {}
        for arg_spec in meta.get("cli_args", []):
            if arg_spec["type"] == "choice":
                combo = QComboBox()
                combo.addItems(arg_spec["choices"])
                combo.setCurrentText(arg_spec.get("default", ""))
                self.arg_widgets[arg_spec["name"]] = combo

        # Remove button
        self.remove_btn = QPushButton("×")
        self.remove_btn.setFixedSize(24, 24)


class PreprocessPipelineWidget(QWidget):
    """Collapsible panel managing a pipeline of preprocessor steps."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.steps: list[PreprocessStepWidget] = []
        self._available = discover()  # from registry
        self._build_ui()

    def run_pipeline(self, input_text: str) -> str:
        """Execute all enabled preprocessors in order."""
        current = input_text
        for step in self.steps:
            if not step.enabled.isChecked():
                continue
            script = step.meta["_script"]
            extra_args = []
            for name, widget in step.arg_widgets.items():
                extra_args.extend([name, widget.currentText()])
            current = run_preprocessor(script, current, extra_args)
        return current
```

### 9.3 Integration into `parse_batch()`

The change to `parse_batch()` is minimal — insert one call before the existing
preprocessing:

```python
def parse_batch(self):
    input_text = self.batch_input.toPlainText().strip()

    # ── NEW: CLI preprocessor pipeline ──
    if hasattr(self, 'preprocess_pipeline'):
        try:
            input_text = self.preprocess_pipeline.run_pipeline(input_text)
        except RuntimeError as e:
            QMessageBox.warning(self, "预处理错误", str(e))
            return
    # ── END NEW ──

    # Existing LLM preprocess (if enabled) ...
    # Existing protocol-specific prefix stripping ...
    # Existing _clean_hex_input ...
```

### 9.4 Backward Compatibility

**Existing hardcoded prefix stripping is NOT removed immediately.** Instead:

1. The new `clean_csg_prefix.py` and `clean_gw_prefix.py` produce **identical
   output** to the existing `_strip_csg_monitor_prefix` / `_strip_gw_new_gen_prefix`.
2. When a CLI preprocessor step is added for a protocol, the corresponding
   hardcoded path in `parse_batch()` is skipped (guarded by a flag).
3. The hardcoded paths remain as fallback for users who don't add any preprocessor
   step.

### 9.5 Config Persistence

Pipeline configuration (which preprocessors are enabled, their arg values) is
stored in `config.json` under a new `preprocess` section:

```json
{
  "preprocess": {
    "pipeline": [
      {
        "name": "clean_csg_prefix",
        "enabled": true,
        "args": {"--parse-level": "auto"}
      },
      {
        "name": "extract_hex_frames",
        "enabled": true,
        "args": {}
      }
    ]
  }
}
```

---

## 10. Error Handling

| Scenario | Behavior |
|---|---|
| Script not found | Registry skips it; dropdown omits it |
| Script crashes (exit 1) | GUI shows error dialog with stderr content |
| Script timeout (>30s) | `subprocess.run` raises `TimeoutExpired`; GUI shows "预处理超时" |
| Empty output | Treated as "all frames filtered out"; GUI shows warning |
| Script not installed | `--info` fails silently; script not in dropdown |

---

## 11. Migration Path

### Phase 1: Framework + First Scripts (this design)
- Create `preprocessors/` with `__init__.py`, `base.py`, and all 5 scripts.
- Each script passes `--info` and works standalone.
- GUI: add `PreprocessPipelineWidget` to batch parse tab.

### Phase 2: GUI Integration
- Wire `PreprocessPipelineWidget.run_pipeline()` into `parse_batch()`.
- Add config persistence.
- Test: existing batch parse behavior is unchanged when pipeline is empty.

### Phase 3: Decommission Hardcoded Paths
- When all protocol-specific prefix stripping has a matching preprocessor script,
  remove `_strip_csg_monitor_prefix`, `_strip_gw_new_gen_prefix`,
  `_strip_csg_new_gen_frame_prefix` from `MainWindow`.
- Keep `_clean_hex_input` (it's a general utility, not protocol-specific).

### Phase 4: User-Extensible Plugins
- Document the `--info` contract so users can write their own preprocessors.
- Auto-discover any `.py` file in `preprocessors/` that responds to `--info`.

---

## 12. Testing Strategy

Each preprocessor script should be testable standalone:

```bash
# Test CSG prefix stripping
echo "15:49:51 254 -> 接收机 Has Get ED A5 00 00 02 EF 01 7E 4E 97 86 01 00 88 00 69 19 09" \
  | python preprocessors/clean_csg_prefix.py
# Expected: "69 19 09" or the remaining bytes after skipping 15 monitor header bytes

# Test registry
python -m preprocessors --list

# Test pipeline
echo "raw log text" | python -m preprocessors --pipeline clean_csg_prefix,extract_hex_frames
```

Unit tests go in `tests/test_preprocessors.py` (or `test_preprocessors.py` in
project root per existing convention). Each test feeds known input and asserts
exact hex output.

---

## 13. Summary: File List

| File | Purpose | LOC (est.) |
|---|---|---|
| `preprocessors/__init__.py` | Registry + discover + run | ~60 |
| `preprocessors/base.py` | Shared hex helpers | ~25 |
| `preprocessors/extract_hex_frames.py` | Universal hex extraction | ~50 |
| `preprocessors/clean_csg_prefix.py` | CSG monitor prefix strip | ~60 |
| `preprocessors/clean_gw_prefix.py` | GW new gen prefix strip | ~70 |
| `preprocessors/extract_tcp_payload.py` | TCP payload + 96..16 deframe | ~100 |
| `preprocessors/classify_by_protocol.py` | Protocol signature classifier | ~80 |
| **Total** | | **~445** |
