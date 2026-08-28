# 设计：协议9 通道自动识别

## 改动点

### 1. `csg_new_gen_parser.py`：新增 `_detect_channel(frame_bytes, frame_len) -> str`

只读 FC 前 16 字节，无表副作用，返回 `"plc"` / `"hrf"`：

```python
def _detect_channel(self, frame_bytes: bytes, frame_len: int) -> str:
    """MPDU 通道自动识别（plc/hrf）。
    依据: SOF 帧可变区域在 PLC/HRF 下字段布局不同 -> 各假设预测的帧长与实际帧长比对。
    强信号: PB大小=40 -> HRF(表44独有); 物理块个数>1 -> PLC(无线仅1PB)。
    """
    if frame_len < 16:
        return 'plc'
    delim = frame_bytes[0] & 0x07
    if delim != 1:  # 非SOF: 信标/SACK/NET 默认plc（无载荷的帧影响小）
        return 'plc'
    var = frame_bytes[1:12]
    std_version = (frame_bytes[12] >> 4) & 0x0F
    # HRF 假设（表45 / 表44）
    hrf_pb = HRF_PB_SIZE_TABLE.get((var[5] >> 4) & 0x0F, 136)
    if hrf_pb == 40:      # 40B PB 仅 HRF 有
        return 'hrf'
    hrf_len = 16 + hrf_pb
    # PLC 假设
    plc_len = None
    if std_version == 1:  # BPLC（表20）
        cnt = var[6] & 0x0F
        tmi = (var[6] >> 4) & 0x0F
        pb = 520 if tmi in (0xD, 15) else 136
        plc_len = 16 + cnt * pb
        if cnt > 1:       # 无线仅支持1个PB
            return 'plc'
    else:                 # ISAC-PLC（表23 数据帧）
        cnt = (var[3] >> 2) & 0x0F
        tmi = (var[5] >> 1) & 0x1F
        pb = {0: 136, 1: 520, 2: 72, 3: 264}.get(tmi, 136)
        plc_len = 16 + cnt * pb
        if cnt > 1:
            return 'plc'
    hr_m = (hrf_len == frame_len)
    pl_m = (plc_len == frame_len)
    if hr_m and not pl_m:
        return 'hrf'
    return 'plc'  # 平局/仅PLC命中/都不命中 -> 默认plc
```

### 2. `parse_to_table`：`channel="auto"` 分支

签名 `channel: str = "auto"`（默认值改为 auto，GUI 显式传 plc/hrf 时行为不变——注意现调用方 `CSGGenGuiParser` 默认传 `'plc'`，需同步）：

```python
self._channel = channel
if channel == "auto" and frame_len >= 2:
    # 仅 MPDU 级输入（接入指示=1）做通道判别
    if ((frame_bytes[0] >> 3) & 0x01) == 1:
        self._channel = self._detect_channel(frame_bytes, frame_len)
```

在 `parse_to_table` 开头（`self._channel = channel` 之后）执行。判别结果记录：`self._detected_channel = self._channel`，在 `_parse_mpdu_frame` 的 FC 解析末尾追加一行「通道判定」。

### 3. `main_gui.py`：下拉加「自动识别」默认项

- `csg_channel_combo.addItem("自动识别", "auto")` 放首位，`addItem("PLC 载波", "plc")`、`addItem("HRF 无线", "hrf")` 随后
- 默认 index 0（auto）；`_load_app_config` 缺省 `"auto"`（`parse_cfg.get("csg_channel", "auto")`）
- `_on_csg_channel_changed` 不变（读 currentData）

## 兼容性

- 显式 plc/hrf 调用（测试、监控器、弹窗）不受影响——auto 只在调用方传 `"auto"` 时触发。
- `CSGGenGuiParser`（main_gui.py L2948-2950）读 `_csg_channel`，默认值改为 auto 后 GUI 解析自动判别。
- 判别函数对非 SOF 帧默认 plc，与现行为一致（无回归风险）。

## 风险 / 边界

- 合成帧/异常帧可能三假设都不命中 → 默认 plc（与现状一致）。
- 平局（hrf_len == plc_len == 实际）：默认 plc；解析后 MAC 版本2 天然走单跳（`_parse_mac_frame` 按版本判定，与 channel 无关），实际影响可忽略。
- 信标帧判定未纳入（默认 plc）：如需可后续扩展（PLC 信标 PB 仅 136/520）。

## 回滚

单文件改动；`git checkout -- csg_new_gen_parser.py main_gui.py`（注意 main_gui.py 有其它未提交改动，回滚前先 stash）。