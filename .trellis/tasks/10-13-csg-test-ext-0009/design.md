# 技术设计：协议9 2.0 测试扩展 0x0009

## 1. 边界

**在范围内**：协议9（南网新一代载波 / 通感一体）应用层测试帧（业务标识 `0xF0`）的
2.0 测试扩展 `0x0009` 在四条链路的表现：解析 → 组帧 → 仿照回填 → 批量摘要。

**不在范围内**：Web 侧（无副本）、链路层组帧（`csg_link_frame_gen.py` 不感知扩展 ID，载荷是黑盒）、
模板存档格式（`csg_frame_templates.py` 存的是 `mode.key` + `params`，新增模式零改动即被支持）。

## 2. 契约（唯一来源，禁止第二份）

| 语义 | 唯一来源 | 消费者 |
|---|---|---|
| 扩展 ID → 名称 | `csg_new_gen_cmd_payloads._TEST_EXT_ID_MAP` 与 `csg_new_gen_frame_gen.TEST_EXT_ID_MAP`（本仓库既有**成对**约定，两份必须同值） | 解析表格、组帧模式名、仿照回填候选名 |
| 扩展数据字节口径 | **`ext_data[x] = 文档字节 x+3`**（`_parse_test_ext_0005` docstring 已明文固化） | 解析 / 组帧 / 反解三处 |
| 模式清单（组帧页下拉 + 反解候选） | `csg_new_gen_frame_gen.test_modes()` | GUI 模式下拉、`mode_by_key`、`csg_frame_reverse._fill_ext` 候选 |
| 模式参数默认值 | `ModeField(name, label, kind, default)` | 组帧页表单默认值 + 回填时的兜底 |
| 摘要片段 | `batch_core.extract_test_mode_content`（桌面一行转发、Web 直接 import） | 批量摘要列、单帧摘要 |

新增字段名（`报文聚合数目` / 模式 key `ext_agg` / 参数 `agg_count`）必须三处同名，
否则「摘要 grep 字段名」「回填候选匹配」这类按名匹配的既有逻辑会静默失效。

## 3. 数据流

```
组帧页（mode_combo 由 test_modes() 生成）
  └─ build_frame_from_mode("ext_agg", {"agg_count": N})
       └─ build_test_pdu(0x04, ext_id=0x0009, agg_count=N)
            └─ 测试数据区 = 协商版本号(1) | 文件长度(1) | 扩展ID(2,LE) | 扩展数据(1B)
                 └─ 业务报文头 → 应用层帧 →（可选）链路层 MPDU / ED 封装

解析：CSGNewGenParser.parse_to_table
  └─ _parse_cmd_test_frame（测试ID=0x04 分支）
       └─ _parse_test_ext_payload(0x0009) → _parse_test_ext_0009
            └─ 行：扩展ID（说明=名称） + 报文聚合数目（原始 0xNN / 解析 N） + _remaining

回填：csg_frame_reverse.reverse_frame（应用层帧/MPDU/ED 三种输入都收敛到 _fill_ext）
  └─ _fill_ext：ext_id==0x0009 → params["agg_count"] = ext_data[0]
       └─ state = {"mode": {"key": "ext_agg", "params": {...}}} → GUI apply_frame_state
```

## 4. 关键决策与取舍

1. **不做第二套映射表**：只往既有成对表追加一行 + 一个 `_parse_test_ext_0009` / `build_ext_0009`。
   理由：AGENTS 的反复教训（陷阱 31/55/61/75）——同一份「清单」写两处必然漂移。
2. **默认 `agg_count = 1`**：文档未规定默认值。取 1 而不是 0，是因为「聚合 0 个 MAC 帧」无意义，
   而 1 是「等价于不聚合」的最小合法值；真正的取值由用户填写。**不臆造业务取值范围**（只按 8bit 校验）。
3. **字段只 1 字节，不做位域拆分**：文档为「字节3 比特0-7 8bit」整字节；
   与 `_parse_test_ext_0008`（单 bit + 保留）不同，这里没有保留位，故用 `pack_bits` 或直接 `bytes([v])` 皆可
   —— 选用 `bytes([...])`（无位域语义时更直观，与 `build_ext_0003` 同风格）。
4. **组帧器暴露在 `test_modes()`**：这是「组帧页 + 仿照回填 + `mode_by_key`」三处的共同入口，
   只加映射表不加 `test_modes()` 会导致「能解析不能组帧、回填报『无对应模式』」的割裂。
5. **过期文案改为动态取值**：`csg_test_frame_gen_widget.py` 里 26 / 24 / 26 三个数字互不相同且都错，
   改为 `len(fg.test_modes())` 单一来源（模块级算一次），从此与真实模式数联动。
6. **不改 `_fill_ext` 的 `unmapped` 逻辑**：`file_len != len(ext_data)` 的既有提示保留（其它模式同口径）。

## 5. 兼容性与回归风险

| 风险 | 判据 / 处置 |
|---|---|
| 新增模式使 `test_modes()` 由 24 → 25，破坏数量断言 | 已核实 `test_csg_frame_gen_gui.py` 是 `total >= 24`、`test_csg_frame_reverse.py` 是 `checked >= 20` ⇒ 不破坏；新增模式本身必须能组帧 + 能反解，否则这两套变红（正是我们要的护栏） |
| 解析侧新增分支影响既有扩展 ID | 只在 `parsers` 字典新增键；既有分支代码不动 ⇒ 输出逐行不变 |
| 摘要片段变化波及非 0x0009 帧 | `extract_test_mode_content` 的 gate（业务标识 0xF0 + 无 `测试模式/配置操作`）不变 ⇒ 其它帧不受影响；用 `test_csg_summary.py` 回归 |
| 组帧页表单自动生成新行导致布局/宽度问题 | 单行 `QFormLayout` 文本字段，无固定宽度；用 offscreen GUI 测试（`test_csg_frame_gen_gui.py`）覆盖 |
| 并发会话正在改 `main_gui.py` / `reflex_web.py` | 提交时只挑本任务 hunk（AGENTS/记忆：禁止 `git add -A`） |

## 6. 回滚

- 纯新增分支 + 一行映射 + 一行 `test_modes()` 项 + 一个 `_fill_ext` 分支；
  **无持久化格式变更、无配置迁移**。
- 回滚 = 反向删除上述四处 + `git checkout` 受影响的测试/文档文件；不需要清理运行时数据。
