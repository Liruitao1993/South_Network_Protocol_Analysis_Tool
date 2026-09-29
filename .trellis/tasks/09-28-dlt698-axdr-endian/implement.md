# 执行计划：协议8 A-XDR 数据域大端化

> 顺序执行；每步做完先跑该步的验证命令，红了就停下修，不要继续往下堆。
> 全程遵守：**链路层小端不动**，只改 APDU/A-XDR 层。

## Step 0 · 基线（先留证据）

- [ ] 跑一遍现状，记录「改前」输出（用于 commit 说明）：

```powershell
python -c 'import dl_t698_45_parser as p, json; f="681F00C32602313104000090017F8D850109200402010105FFFF9ED00000 6D1716".replace(" ",""); print(p.DLT69845Parser().parse(bytes.fromhex(f))["链路用户数据"]["APDU"]["数据"])'
```

预期：`解析值 = -794886145`，`说明` 含「(小端)」。

验证：输出与 PRD 中「本工具」列一致。

## Step 1 · A-XDR 解码大端化（`dl_t698_45_axdr.py`）

- [ ] W1 表格逐行改 `'little'` → `'big'`：L132/L139/L146/L153/L160/L167（整型）、
      L266/L285（年）、L273（毫秒拼接）、L326/L334/L348（OI）、L360（TI 间隔）。
- [ ] L181/L188 浮点 `'<f'/'<d'` → `'>f'/'>d'`。
- [ ] 同步改说明文字：把「N字节…整数(小端)」改为「(大端)」；日期/享秒注释与 L310 现有大端注释统一。
- [ ] 单字节处（L118 `_decode_integer`、L394 scaler）保留但加注释：单字节无端序。

验证（自洽往返 + 目标帧）：

```powershell
python -c 'from dl_t698_45_axdr import AXDRCoder; c=AXDRCoder();
import itertools
bad=[]
for tag,val in [(0x10,-2),(0x11,2),(0x05,-24880),(0x06,4294934224),(0x12,-3),(0x13,3),(0x15,1.5),(0x16,2.5)]:
    d=c.decode(c.encode(val,tag),0)[0]["解析值"]
    ok = abs(d-val)<1e-6 if isinstance(val,float) else d==val
    bad.append((tag,val,d,ok))
print(bad)'
```

预期：全部 `ok=True`（tag 取值以 `get_tag_name` 表为准，若 tag 别名不同按实际调整）。

## Step 2 · A-XDR 编码大端化（同文件 L413-474）

- [ ] `_encode_long/…/long64_unsigned/float32/float64/OI/OAD/OMD` 的 `'<…'` → `'>…'`。
- [ ] 复跑 Step 1 的往返脚本（此时编码改了，仍须自洽）。

验证：往返脚本全 `ok=True`；且 `c.encode(180, 0x11).hex() == '1100b4'`（心跳周期大端）。

## Step 3 · 组帧侧（`dl_t698_45_frame_gen.py`）

- [ ] L54/L62 心跳周期、L174/L178/L182/L184 → `'>H'`；L18/L34（FCS/长度域）保持 `'<'`。

验证：

```powershell
python -c 'from dl_t698_45_frame_gen import DLT69845FrameGenerator as G; g=G();
f=g.generate_link_request(bytes([0x01,0x07,0x08]), ca=0x09, piid=0x00, req_type=0x00, heartbeat=180);
print(f.hex().upper(), f.find(bytes.fromhex("00B4"))>0)'
```

预期：帧内出现 `00 B4`（大端心跳周期）。

## Step 4 · LINK 预连接不带 tag（`dl_t698_45_apdu_parser.py` L1204-1260）

- [ ] `_parse_link_request`：`01 | PIID(1B) | 请求类型(1B, ENUMERATED 0/1/2) | 心跳周期(2B, 大端) |
      [请求时间 date_time(10B)]`，不再对前 4 个字段调用 `self.axdr.decode()`。
- [ ] `_parse_link_response`：`81 | PIID(1B) | 结果(1B, bit0~2) | 请求时间 | 收到时间 | 响应时间 |
      时钟可信标志(1B, bit7)`。
- [ ] 时间字段复用 `_decode_date_time` 的**语义**（10 字节定长，不带 tag/长度域）。

验证（标准示例，AC2/AC3）：

```powershell
python -c 'import dl_t698_45_apdu_parser as ap, json;
r=ap.DLT69845APDUParser().parse(bytes.fromhex("01000000B407E005130408050000A4")); print(json.dumps(r,ensure_ascii=False,default=str)[:1200])'
```

预期：`解析状态=成功`，请求类型=登录，心跳周期=180，时间 2016-05-19 08:05:00.164。

## Step 5 · 相邻层核查（只查，除同类小端硬编码外不改）

- [ ] `Select-String -Path dl_t698_45_data_decode.py -Pattern "'little'"` → 若有，判断是否 A-XDR 层（是则改）。
- [ ] 确认 `dl_t698_45_parser.py` L62/L214/L239 仍是小端（链路层，**不得改**）。
- [ ] 读 `meter_sim/archive.py` + `meter_sim_data.json` 说明，记录 A-XDR 原始值来源结论（写入 task notes / journal）。
- [ ] `git grep -n "'little'" -- dl_t698_45_*.py meter_sim` 复核剩余命中均为链路层或单字节。

## Step 6 · 测试

- [ ] 新增 `test/test_dl_t698_45_endian.py`：文档 H.1.1 三个 oracle（180s / 2016-05-19 三段时间 /
      164·607·730 ms）+ 用户实测帧 `-24880` + 编码往返（8 整型 + 2 浮点）+ 链路层小端回归
      （长度域 `1F 00`→31、HCS/FCS 校验通过）。
- [ ] 修正被小端写死的既有期望：`test/test_dl_t698_45.py` L35-45（`bytes([0x12,0x34,0x12])==0x1234`
      → 大端写法）、以及跑挂的其它断言；`test_dl_t698_45_data_decode.py`、`test_dlt698_preset.py` 按实际报错修正。
- [ ] 全跑：

```powershell
python test/test_dl_t698_45_endian.py
python test/test_dl_t698_45.py
python test/test_dl_t698_45_data_decode.py
python test/test_dl_t698_45_fujian.py
python test/test_dlt698_preset.py
```

验证：全绿；`test_dl_t698_45_fujian.py`（EB 大端已正确路径）不得回退。

## Step 7 · 未触及协议的防误伤回归（抽查）

- [ ] `python test/test_gdw_fujian.py`（协议7 扩展）、以及协议12 的
      `python test/test_modular_iface_axdr.py` 各跑一次，确认无连带影响。

## Step 8 · 文档与版本

- [ ] `AGENTS.md`：§1 表格协议8 行 → 「小端（链路层 L/HCS/FCS）/大端（A-XDR 数据）」；
      §5.6 增补两层字节序说明 + oracle 引用；陷阱清单新增「协议8 A-XDR 必须大端」条目。
- [ ] `main_gui.py`：`CHANGELOG` 新增条目（bug 修复 + 影响面说明），`APP_VERSION` bump（PATCH）。
- [ ] `python release_check.py` 按需（若 bump 版本）。

## Step 9 · 收尾

- [ ] `python ./.trellis/scripts/task.py finish`（3.4 前先跑 `trellis-check` 口径自检：
      变更文件清单 vs PRD 的 AC 逐条对照）。
- [ ] commit（中文规范）：`fix(协议8): 698.45 A-XDR 数据域改为大端（含组帧与预连接不带 tag）`，
      正文列出「改前 -794886145 / 改后 -24880」与 oracle 来源。

## 回滚点

- 每个 Step 结束即为回滚点（`git stash`/`git checkout -- <file>` 单文件回退）。
- Step 1+2 必须成对提交语义（只回退其一会导致组帧↔解析不自洽）。

## Step 8 记录 · 待核查发现（不改代码）

- **`dl_t698_45_apdu_parser.py:247` 的 `v.to_bytes(max(1, (v.bit_length() + 7) // 8), "little")`（待核查）**：
  该行位于 `_decode_eb_data_content`，是「解析值 list → 原始字节」的**回退分支**。该分支仅在 EB 数据为
  array / structure（值已解成 list）时命中；EB 数据绝大多数是 octet-string，走 str 分支，故影响面很小。
  经核实属**本次改动前的既有代码**（commit `a857867`），且**不在 design W1/W3 范围内**（W1=A-XDR 编解码端序、
  W3=LINK 预连接不带 tag），故本次**未修改**，仅记录待核查。
  待核查理由：若该回退分支按小端拼字节，与 A-XDR 大端契约（陷阱 61 / 新版陷阱 64）不一致；但其代码路径
  覆盖度低、无现场案例触发，需真实 array/structure 型 EB 报文才能定论 —— 属独立任务，避免在本次端序修复里
  混入无法验证的行为变更（陷阱 23 同精神：不臆造、不凭推测改）。
