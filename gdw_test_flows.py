# -*- coding: utf-8 -*-
"""国网协议测试页（协议7）—— **流程测试**用例与执行引擎（纯逻辑，零 Qt）。

依据
----
- `协议文档/7.国网本地接口协议/互换性协议一致性测试用例-本地通信单元(能源控制器(专变)-双模)-SGCM010720240329.xlsx`
  「流程测试」70~78 行（8 个流程 + 抄表测试）。
- `协议文档/7.国网本地接口协议/关于能源控制器.docx` 2.2.x 各流程的分步描述。

角色约定
--------
本工具扮演 **能源控制器（CCO/集中器）侧**：主动下发 1376.2 命令、接收模块上行；
需要从节点配合的步骤（06H F4 上报、13H F1 回数据、14H F1 路由请求等），
由「协议8 虚拟表」页模拟电能表/从节点完成 —— 引擎把这些步骤标成
``needs_slave=True``，界面会提示去虚拟表页操作。

步骤类型
--------
``send``   下发一条命令（可带字段覆盖），等应答；
``wait``   被动等待模块上行某 AFN/Fn（模块/路由主动发起的流程）；
``serve``  服务路由请求：收到 14H F1 就回抄读内容、收到 14H F2 就回系统时间（可多次），
           直到 ``until`` 指定的上行（默认 06H F2 抄读数据）或超时；
``sleep``  固定延时（协议规定的等待窗口）；
``manual`` 需要现场/虚拟表配合的人工动作，不计入自动判定；
``note``   纯说明，不停留。

引擎只产出「动作」，不碰 Qt、不碰串口 —— 便于单测。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

KIND_SEND = "send"
KIND_WAIT = "wait"
KIND_SLEEP = "sleep"
KIND_MANUAL = "manual"
KIND_NOTE = "note"
KIND_RESET_STA = "reset_sta"      # 下发 STA 硬件初始化（645 广播），让 STA 重新入网并上报
KIND_POLL = "poll"                # 轮询：重复下发同一条命令直到校验通过或超时
KIND_SERVE = "serve"              # 服务路由请求：14H F1 回抄读内容、14H F2 回系统时间，直到 until 命中

#: 只有「主动上报类」才需要测试系统回 00H F1 确认。
#: **不要包含 14H F1**（路由请求抄读内容）：它要的是回抄读内容（14H F1 下行），
#: 不是确认；回确认会让被测以为请求被拒、继续重发或干脆不抄表。
CONFIRM_AFNS = {0x06, 0x56}
CONFIRM_UPLINK = {
    (0x03, 0x10),     # 本地通信模块上报信息（识别流程会主动发）
    (0x03, 0x11),     # 通信模块事件上报
    (0x14, 0x03),     # 请求依通信延时修正通信数据（确认后再回 14H F3 下行）
}


def needs_confirm(afn: int, fn: int) -> bool:
    """这条上行是否需要测试系统回确认帧（避免被测反复重发）。"""
    return afn in CONFIRM_AFNS or (afn, fn) in CONFIRM_UPLINK

# ── 步骤内容校验 ────────────────────────────────────────────────────────
CHECK_ARCHIVE = "archive_contains"      # 10H F2：返回的档案要包含组网参数里的地址
CHECK_TOPOLOGY = "topology_joined"      # 10H F20：拓扑里档案节点角色有效
CHECK_ACK = "acked"                     # 只要确认/否认可判即可
CHECK_DELAY = "broadcast_delay"         # 03H F9：广播通信延迟时间 > 0
CHECK_BROADCAST_ACK = "broadcast_ack"   # 05H F3：确认帧带等待时间 T2 > 0
CHECK_ROUTE_STATE = "route_state"       # 10H F4：工作标志=停止、路由完成=完成
CHECK_READ_MATCH = "read_match"         # 抄读结果须与虚拟表应答的数据内容一致



@dataclass
class FlowStep:
    """流程中的一步。"""

    kind: str
    title: str
    key: str = ""                                  # send 用：命令 key（如 "13-1"）
    afn: int = -1                                   # wait 用：期望上行的 AFN
    fn: int = -1                                    # wait 用：期望上行的 Fn
    timeout: float = 6.0                            # 等待秒数（send 应答 / wait 上行 / sleep）
    values: Dict[str, Any] = field(default_factory=dict)   # send 用的字段覆盖
    needs_slave: bool = False                       # 需要虚拟表/从节点配合
    optional: bool = False                          # 失败不算用例失败（仅提示）
    check: str = ""                                 # 收到数据帧后的内容校验（见 run_check）
    accept: Tuple[Tuple[int, int], ...] = ()         # 额外接受的应答 (afn, fn)；fn<0 表示任意 Fn
    #: ``KIND_SERVE`` 用：要自动应答的上行（默认路由抄读请求 + 时钟请求）
    serve: Tuple[Tuple[int, int], ...] = ((0x14, 0x01), (0x14, 0x02))
    #: ``KIND_SERVE`` 用：收到这条上行即认为本步完成（(afn, fn)）；空 = 只在超时结束
    until: Tuple[int, int] = (-1, -1)
    #: 发完就算完成、不等任何应答（如 `14H F3 下行` 回完延时修正后，被测直接继续抄表并
    #: 上报 `13H F1`；干等确认只会白超时判失败）
    no_reply: bool = False
    hint: str = ""

    def expect_afn_fn(self) -> Optional[Tuple[int, int]]:
        return (self.afn, self.fn) if self.afn >= 0 else None


@dataclass
class FlowCase:
    """一个流程用例。"""

    fid: str
    name: str
    desc: str
    steps: List[FlowStep] = field(default_factory=list)
    source: str = ""                                # 出处（xlsx 行号/文档章节）

    @property
    def needs_slave(self) -> bool:
        return any(s.needs_slave for s in self.steps)


# ── 通用片段 ────────────────────────────────────────────────────────────

def _init_params() -> FlowStep:
    return FlowStep(KIND_SEND, "参数区初始化（清空模块内已有档案）", key="01-2", timeout=6.0,
                    hint="不先初始化，随后 11H F1 会回「错误状态字=6 表号重复」")


def _power_on() -> FlowStep:
    """用「硬件初始化」触发 CCO 上电/重启动作（用户口径）。"""
    return FlowStep(KIND_SEND, "硬件初始化 (01H F1)：触发 CCO 上电/重启动作", key="01-1",
                    timeout=6.0,
                    hint="模块会重启并重新走识别流程，随后应主动上报 03H F10；"
                         "不先触发就没法验证「上电后能源控制器识别」这条链路")


def read_round_steps(label: str = "抄表") -> List[FlowStep]:
    """两轮抄读：第一轮「延时不相关」直接收 13H F1，第二轮「延时相关」走 14H F3 修正。

    判据（用户口径）：不是只看 AFN/Fn 对上，而是**CCO 上报的数据内容必须与虚拟表
    实际发出的应答逐字节一致**才判抄读通过（`CHECK_READ_MATCH`）。
    """
    return [
        FlowStep(KIND_NOTE, f"{label}第一轮：延时不相关（通信延时相关性标志=00H）"),
        FlowStep(KIND_SEND, f"{label}① 监控从节点 13H F1（延时无关），直接等 CCO 上报抄读结果",
                 key="13-1", timeout=90.0, values={"通信延时相关性标志": 0},
                 check=CHECK_READ_MATCH,
                 hint="延时无关：模块应用 13H F1 上报抄读数据；数据须与虚拟表应答一致"),
        FlowStep(KIND_NOTE, f"{label}第二轮：延时相关（通信延时相关性标志=01H）"),
        FlowStep(KIND_SEND, f"{label}② 监控从节点 13H F1（延时相关）", key="13-1", timeout=30.0,
                 values={"通信延时相关性标志": 1},
                 accept=((0x14, 0x03), (0x14, 0x01)),
                 hint="延时相关：模块会先回 14H F3 上行请求按延时修正通信数据"),
        FlowStep(KIND_WAIT, f"{label}③ 等待模块上行 14H F3（请求依延时修正通信数据）",
                 afn=0x14, fn=3, timeout=30.0, needs_slave=True),
        FlowStep(KIND_SEND, f"{label}④ 回复 14H F3 下行（按时延修正后的通信数据）",
                 key="14-3", timeout=6.0, no_reply=True,
                 hint="回完就继续，**不等应答**：被测收到后会直接继续抄表并上报 13H F1 "
                      "（干等确认只会白超时判失败）"),
        FlowStep(KIND_WAIT, f"{label}⑤ 等待模块上报 13H F1（修正后的抄读结果）",
                 afn=0x13, fn=1, timeout=90.0, needs_slave=True,
                 check=CHECK_READ_MATCH,
                 hint="数据须与虚拟表应答一致才算抄读通过"),
    ]


def _add_nodes() -> FlowStep:
    return FlowStep(KIND_SEND, "添加从节点档案（组网参数里的从节点）", key="11-1", timeout=6.0,
                    hint="列表与数量由「组网参数」自动填，地址低字节在前")


def _query_archive(count_note: str = "") -> FlowStep:
    return FlowStep(KIND_SEND, "读取从节点信息（核对档案）" + count_note, key="10-2", timeout=6.0,
                    check=CHECK_ARCHIVE,
                    hint="只核对档案是否加对；是否入网看 10H F20 拓扑")


def _topology() -> FlowStep:
    return FlowStep(KIND_SEND, "查询双模网络拓扑（入网判据）", key="10-20", timeout=6.0,
                    check=CHECK_TOPOLOGY,
                    hint="拓扑里角色有效才算在网")


#: 组网等待窗口（协议/现场经验：广播复位后约 5 分钟完成组网）
JOIN_WINDOW = 300.0
#: 组网期间轮询拓扑的间隔
JOIN_POLL_INTERVAL = 15.0


def prerequisite_steps(window: float = JOIN_WINDOW) -> List[FlowStep]:
    """「重新执行一次建档 + 组网」的完整前置序列。

    用户口径（2026-10-27）：用例里写的「档案已建、组网已启动」只是省略写法，
    实际要按下面的过程真跑一遍，**组网是需要时间的**：

    1. 参数区初始化（清旧档案）
    2. 添加从节点档案
    3. 查询从节点数量
    4. 查询从节点信息（核对档案）
    5. 控制 STA 复位（645 广播，让 STA 重新入网并上报）
    6. 启动组网（11H F102）
    7. 预留 5 分钟组网时间：轮询 10H F20 拓扑，直到档案节点全部入网或超时
    """
    return [
        _init_params(),
        _add_nodes(),
        FlowStep(KIND_SEND, "查询从节点数量 (10H F1)", key="10-1", timeout=6.0),
        _query_archive(),
        FlowStep(KIND_RESET_STA, "控制 STA 复位（645 广播）：让从节点重新入网并主动上报",
                 timeout=6.0, needs_slave=True,
                 hint="虚拟表侧复位 STA，之后 STA 会重新入网并上报「从节点信息」"),
        FlowStep(KIND_SEND, "启动组网 (11H F102)", key="11-102", timeout=6.0),
        FlowStep(KIND_POLL, f"预留组网时间：轮询拓扑直到入网完成（最长 {window / 60:.0f} 分钟）",
                 key="10-20", timeout=window, check=CHECK_TOPOLOGY,
                 needs_slave=True,
                 hint=f"每 {JOIN_POLL_INTERVAL:.0f}s 查一次 10H F20；档案节点全部在网即通过"),
    ]


# ── 8 个流程 + 抄表测试 ─────────────────────────────────────────────────

FLOW_CASES: List[FlowCase] = [
    FlowCase(
        "identify", "识别流程",
        "模块上电后能源控制器的识别动作：等待模块上报→查询运行模式→查/设主节点地址。",
        source="xlsx 第 70 行 / word 2.2.2 识别流程",
        steps=[
            _power_on(),
            FlowStep(KIND_WAIT, "等待模块主动上报「通信单元上报信息」(03H F10 上行)，超时 60s",
                     afn=0x03, fn=10, timeout=60.0,
                     hint="硬件初始化后模块几乎立刻上报；本步先查「已收到的上行缓存」，"
                          "早到的帧也会被认到，不会因为等早了/等晚了而漏掉"),
            FlowStep(KIND_SEND, "主动查询「本地通信模块运行模式信息」(03H F10)", key="03-10",
                     timeout=6.0, optional=True,
                     hint="word 要求：模块未主动上报时，能源控制器应在 1min 内主动下发本命令"),
            FlowStep(KIND_SEND, "查询主节点地址 (03H F4)", key="03-4", timeout=6.0,
                     hint="应答里的主节点地址应与终端地址不一致（word 第 113 行）"),
            FlowStep(KIND_SEND, "设置主节点地址 (05H F1)", key="05-1", timeout=6.0,
                     hint="主节点地址取「组网参数」里的 CCO 地址；期望确认帧"),
        ],
    ),
    FlowCase(
        "archive", "档案同步流程",
        "能源控制器把表档案同步到模块：初始化/删除→添加从节点→回读核对。",
        source="xlsx 第 71 行 / word 2.2.3 档案同步流程",
        steps=[
            _init_params(),
            _add_nodes(),
            FlowStep(KIND_SEND, "读取从节点数量 (10H F1)", key="10-1", timeout=6.0),
            _query_archive(),
            FlowStep(KIND_NOTE, "判定：10H F2 返回的档案地址应包含组网参数里的全部从节点地址"),
        ],
    ),
    FlowCase(
        "spot_read", "点抄流程",
        "能源控制器点抄某块表：监控从节点→（必要时依延时修正）→拿到表数据。",
        source="xlsx 第 72 行 / word 2.2.4 点抄流程",
        steps=prerequisite_steps() + [
            FlowStep(KIND_NOTE, "前置完成（档案已建、组网已就绪）后，点抄由能源控制器发起；"
                               "本工具直接下发 13H F1 模拟该动作"),
            *read_round_steps("点抄"),
        ],
    ),
    FlowCase(
        "register", "从节点主动注册流程",
        "启动搜表→模块激活主动注册→新节点上报→空闲后查路由运行状态。",
        source="xlsx 第 73 行 / word 2.2.5 从节点主动注册流程",
        steps=prerequisite_steps() + [
            FlowStep(KIND_SEND, "激活从节点主动注册 (11H F5)", key="11-5", timeout=6.0,
                     hint="期望确认帧；word 第 134 行超时 5min"),
            FlowStep(KIND_SLEEP, "等待 10s 后由从节点上报", timeout=10.0, needs_slave=True),
            FlowStep(KIND_WAIT, "等待模块上报「从节点信息及设备类型」(06H F4 上行)", afn=0x06, fn=0x04,
                     timeout=300.0, needs_slave=True,
                     accept=((0x06, 0x01),),
                     hint="新标准要求 CCO 用 06H F4（上报从节点信息及设备类型）上报，"
                          "06H F1 是 09 版标准的旧报文（仍接受但会告警提示）"),
            FlowStep(KIND_SLEEP, "空闲 10min（协议要求此时能源控制器不应下发其它命令）",
                     timeout=600.0, needs_slave=True),
            FlowStep(KIND_SEND, "空闲后查询路由运行状态 (10H F4)", key="10-4", timeout=6.0,
                     check=CHECK_ROUTE_STATE,
                     hint="判定：运行状态字「工作标志=停止工作」、「路由完成标志=完成」"),
        ],
    ),
    FlowCase(
        "master_read", "能源控制器主动方式抄表",
        "能源控制器主动发起抄表：建档→组网→逐节点监控抄读→回读档案确认。",
        source="xlsx 第 74 行",
        steps=prerequisite_steps() + [
            *read_round_steps("主动抄表"),
        ],
    ),
    FlowCase(
        "route_read", "路由模块主动方式抄表",
        "组网后先下发「重启」让路由开始主动抄表：路由上行 14H F1 请求抄读内容 → "
        "按档案/序号回对应电表协议的正向有功总电能 → 路由抄回后上报 06H F2 抄读数据。",
        source="xlsx 第 75 行 / 对照 12H 路由控制 + 14H 路由数据抄读 / word A.5 之后的路由主动抄表",
        steps=prerequisite_steps() + [
            FlowStep(KIND_NOTE, "路由主动抄表由 CCO 内部路由模块发起，必须先让它跑起来："
                               "下发 12H F1「重启」后路由才会上行 14H F1 请求抄读内容"),
            FlowStep(KIND_SEND, "路由重启 (12H F1)：启动路由主动抄表", key="12-1", timeout=6.0,
                     hint="不发这一步，CCO 不会主动上行 14H F1 请求抄读内容（步骤 7 与 8 之间缺的就是它）"),
            FlowStep(KIND_SERVE,
                     "服务路由请求：14H F1 → 回抄读内容；14H F2 → 回系统时间（直到收到 06H F2）",
                     key="14-1", timeout=120.0, needs_slave=True,
                     until=(0x06, 0x02), check=CHECK_READ_MATCH,
                     hint="路由每请求一次就按该从节点协议回一次正向有功总电能读报文（可多次）；"
                          "收到 06H F2 上报抄读数据即完成，随后用 12H F2 暂停路由"),
            FlowStep(KIND_SEND, "路由暂停 (12H F2)：让 CCO 停止请求抄读内容", key="12-2",
                     timeout=6.0,
                     hint="测试完成后必须暂停，否则 CCO 会一直上行 14H F1 要抄读内容"),
        ],
    ),
    FlowCase(
        "broadcast", "广播流程（通信时延相关报文机制）",
        "广播对时：查从节点通信延时→启动广播（645 帧按 T1 修正）→按确认帧 T2 静默。",
        source="xlsx 第 76 行 / word 2.2.6 广播流程",
        steps=[
            FlowStep(KIND_NOTE, "前提：能源控制器侧下发透明转发广播对时（OAD=F2090201 或 F2097F00）"
                               "触发广播流程；本工具直接验证后续 1376.2 交互"),
            FlowStep(KIND_SEND, "查询从节点通信延时 (03H F9)", key="03-9", timeout=120.0,
                     check=CHECK_DELAY,
                     hint="应答里「广播通信延迟时间」应为 >0 的数值 T1（word 第 141 行，超时 2min）"),
            FlowStep(KIND_SEND, "启动广播 (05H F3)：645 帧按 T1 修正后下发", key="05-3", timeout=6.0,
                     check=CHECK_BROADCAST_ACK,
                     hint="word 第 145 行：645 帧未按 T1 修正判不合格"),
            FlowStep(KIND_SLEEP, "按确认帧里的等待时间 T2 静默观察（本例取 5s，实际按应答 T2 调整）",
                     timeout=5.0),
            FlowStep(KIND_NOTE, "判定：T2 内不应收到模块的任何报文；超时未收到 05H F3 应答亦判不合格"),
        ],
    ),
    FlowCase(
        "broadband", "宽带增补协议测试流程",
        "宽带增补三查：网络拓扑(10H F21)、多网信息(10H F111)、宽带载波芯片(10H F112)。",
        source="xlsx 第 77 行 / word 2.2.7 宽带增补内容测试",
        steps=[
            FlowStep(KIND_NOTE, "前提：能源控制器侧已下发「更新周期」(OAD=F2090600) 与「日期时间」"
                               "(OAD=40000200) 触发周期更新；本工具验证 1376.2 侧三查"),
            FlowStep(KIND_SEND, "查询网络拓扑信息 (10H F21)", key="10-21", timeout=240.0,
                     hint="超时 4min 未收到判超时失败"),
            FlowStep(KIND_SEND, "查询多网络信息 (10H F111)", key="10-111", timeout=240.0),
            FlowStep(KIND_SEND, "查询宽带载波芯片信息 (10H F112)", key="10-112", timeout=240.0),
        ],
    ),
    FlowCase(
        "meter_read", "抄表测试",
        "进行能源控制器本地模块的抄表测试：建档→组网→逐表抄读正向有功总电能。",
        source="xlsx 第 78 行",
        steps=prerequisite_steps() + [
            *read_round_steps("抄表"),
        ],
    ),
]

FLOW_BY_ID: Dict[str, FlowCase] = {c.fid: c for c in FLOW_CASES}


def flow_case(fid: str) -> Optional[FlowCase]:
    return FLOW_BY_ID.get(fid)


# ── 执行引擎 ────────────────────────────────────────────────────────────

#: 一步的结果
STEP_PENDING = "pending"
STEP_RUNNING = "running"
STEP_OK = "ok"
STEP_FAIL = "fail"
STEP_SKIP = "skip"


@dataclass
class Action:
    """引擎产出的「下一个动作」。"""

    kind: str                  # send / wait / sleep / manual / note / done
    step: Optional[FlowStep] = None
    index: int = -1
    reason: str = ""


class FlowRunner:
    """把 ``FlowCase`` 跑成动作序列。

    调用方（界面）负责真正发帧与计时：

    - ``start()`` → 取第一个 ``Action``；
    - 就 ``send``/``wait`` 完成后调 ``advance(ok=True/False, note=...)``；
    - ``sleep`` 由界面用定时器等 ``action.step.timeout`` 秒后 ``advance(True)``；
    - 超时/否认 → ``advance(False, "原因")``。
    """

    def __init__(self, case: FlowCase, overrides: Optional[Dict[str, Dict[str, Any]]] = None):
        self.case = case
        self.overrides = overrides or {}
        self.index = -1
        self.states: List[str] = [STEP_PENDING] * len(case.steps)
        self.notes: List[str] = [""] * len(case.steps)
        self.finished = False
        self.failed = False
        self.stopped = False

    # ── 生命周期 ────────────────────────────────────────────────────
    def start(self) -> Action:
        if not self.case.steps:
            self.finished = True
            return Action("done")
        self.index = -1
        return self._next(starting=True)

    def advance(self, ok: bool, note: str = "") -> Action:
        """上一步结束（ok=是否通过），返回下一步动作。"""
        if self.finished:
            return Action("done")
        if 0 <= self.index < len(self.states):
            step = self.case.steps[self.index]
            if ok:
                self.states[self.index] = STEP_OK
            elif step.optional or step.kind in (KIND_NOTE, KIND_MANUAL):
                # 可选项/人工步骤失败不影响用例结论
                self.states[self.index] = STEP_SKIP if step.kind != KIND_NOTE else STEP_OK
            else:
                self.states[self.index] = STEP_FAIL
                self.failed = True
            if note:
                self.notes[self.index] = note
        return self._next()

    def stop(self, reason: str = "用户停止") -> None:
        if 0 <= self.index < len(self.states) and self.states[self.index] == STEP_RUNNING:
            self.states[self.index] = STEP_SKIP
            self.notes[self.index] = reason
        self.stopped = True
        self.finished = True

    # ── 内部 ────────────────────────────────────────────────────────
    def _next(self, starting: bool = False) -> Action:
        while True:
            self.index += 1
            if self.index >= len(self.case.steps):
                self.finished = True
                return Action("done")
            step = self.case.steps[self.index]
            if step.kind == KIND_NOTE:
                self.states[self.index] = STEP_OK
                self.notes[self.index] = "说明"
                continue
            self.states[self.index] = STEP_RUNNING
            return Action(step.kind, step=step, index=self.index)

    @property
    def passed(self) -> bool:
        return self.finished and not self.failed and not self.stopped

    def summary(self) -> Tuple[int, int, int]:
        """(通过步数, 失败步数, 跳过步数)。"""
        return (self.states.count(STEP_OK), self.states.count(STEP_FAIL),
                self.states.count(STEP_SKIP))

    def values_for(self, step: FlowStep) -> Dict[str, Any]:
        """某步的字段覆盖（流程级覆盖 + 步骤级覆盖）。"""
        merged = dict(self.overrides.get(step.key, {}))
        merged.update(step.values)
        return merged


def step_accepts(step: Optional[FlowStep], afn: int, fn: int) -> bool:
    """这条上行是否满足 ``step`` 的等待：主判据 ``afn``/``fn`` 或 ``accept`` 里的兼容项。

    ``accept`` 里的 ``fn < 0`` 表示该 AFN 任意 Fn 都算。
    """
    if step is None:
        return False
    for a, f in ((step.afn, step.fn),) + tuple(step.accept or ()):
        if a < 0:
            continue
        if afn == a and (f < 0 or fn == f):
            return True
    return False


def is_primary_uplink(step: Optional[FlowStep], afn: int, fn: int) -> bool:
    """是否命中的是主判据（而非 ``accept`` 里声明的兼容帧）。"""
    if step is None or step.afn < 0:
        return False
    return afn == step.afn and (step.fn < 0 or fn == step.fn)


def match_uplink(action: Action, afn: int, fn: int) -> bool:
    """收到的上行帧是否正是 ``wait`` 步骤在等的那条（含 ``accept`` 兼容项）。"""
    step = action.step if action else None
    if step is None or action.kind != KIND_WAIT:
        return False
    return step_accepts(step, afn, fn)


def flow_titles(case: FlowCase) -> List[str]:
    return [s.title for s in case.steps]


def cases_needing_slave() -> List[str]:
    return [c.name for c in FLOW_CASES if c.needs_slave]


def _rows_map(rows: Sequence[Tuple]) -> Dict[str, Tuple]:
    return {str(r[0]).strip(): r for r in rows if r}


def _row_text(rows: Dict[str, Tuple], name: str) -> str:
    row = rows.get(name)
    return str(row[2]) if row else ""


def run_check(name: str, rows: Sequence[Tuple], archive: Sequence[str] = (),
              expected: Sequence[bytes] = ()
              ) -> Tuple[bool, str]:
    """按 ``FlowStep.check`` 校验收到的数据帧内容。返回 (是否通过, 说明)。"""
    if not name:
        return True, ""
    table = _rows_map(rows)
    if not table:
        return False, "未解析出字段"

    if name == CHECK_ARCHIVE:
        seen: List[str] = []
        for key in table:
            if "地址" in key and "从节点" in key:
                text = str(table[key][2] or "").strip().upper()
                if len(text) == 12 and text.isdigit():
                    seen.append(text)
        missing = [a for a in archive if a.upper() not in set(seen)]
        if not archive:
            return bool(seen), f"模块档案 {len(seen)} 个（组网参数未填从节点，无法比对）"
        return (not missing), (f"档案 {len(seen)} 个，缺 {('、'.join(missing))}" if missing
                               else f"档案已含全部 {len(archive)} 个组网从节点")

    if name == CHECK_TOPOLOGY:
        addrs: Dict[str, str] = {}      # 序号 → 地址
        roles: Dict[str, str] = {}      # 序号 → 角色
        for key, row in table.items():
            if key.startswith("节点") and key.endswith("地址"):
                addrs[key[len("节点"):-len("地址")]] = str(row[2] or "").strip().upper()
            elif key.startswith("节点") and key.endswith("节点角色"):
                roles[key[len("节点"):-len("节点角色")]] = str(row[2] or "").strip()
        valid = [a for idx, a in addrs.items()
                 if len(a) == 12 and "无效" not in roles.get(idx, "无效")]
        if not archive:
            return bool(valid), f"拓扑内有效节点 {len(valid)} 个（组网参数未填从节点，无法比对）"
        seen = {x.upper() for x in valid}
        missing = [a for a in archive if a.upper() not in seen]
        joined = [a for a in archive if a.upper() in seen]
        return (not missing), (f"拓扑内 {len(joined)}/{len(archive)}"
                               + (f"，未入网 {'、'.join(missing)}" if missing else ""))

    if name == CHECK_DELAY:
        text = ""
        for key, row in table.items():
            if "延迟" in key or "延时" in key:
                text = str(row[2] or "")
                break
        try:
            value = float(text.split("(")[0])
        except (TypeError, ValueError):
            return False, f"未解析出广播通信延迟时间（{text or '无该字段'}）"
        return value > 0, f"广播通信延迟时间 T1={value:g}"

    if name == CHECK_BROADCAST_ACK:
        for key, row in table.items():
            if "等待时间" in key:
                try:
                    t2 = float(str(row[2] or "").split("(")[0])
                except (TypeError, ValueError):
                    continue
                return t2 > 0, f"确认帧等待时间 T2={t2:g}"
        return True, "确认帧未带等待时间字段（按确认通过）"

    if name == CHECK_ROUTE_STATE:
        status = _row_text(table, "工作标志(D1)") or _row_text(table, "运行状态字")
        route = _row_text(table, "运行状态字")
        ok = ("停止" in status) and ("完成" in route or not route)
        return ok, f"工作标志={status or '?'}；{route or ''}".strip("；")

    if name == CHECK_READ_MATCH:
        payload = b""
        for key, row in table.items():
            if key.endswith("报文内容") or "报文内容" in key or "抄读数据内容" in key:
                try:
                    payload = bytes.fromhex(str(row[1]).replace(" ", ""))
                except (TypeError, ValueError):
                    payload = b""
                break
        if not payload:
            # 没解出字段时退一步：数据单元行本身就是抄读数据
            for key, row in table.items():
                if key == "数据单元":
                    try:
                        payload = bytes.fromhex(str(row[1]).replace(" ", ""))
                    except (TypeError, ValueError):
                        payload = b""
                    break
        if not payload:
            return False, "上报里没有抄读数据内容"
        nested = extract_meter_frames(payload)
        if not nested:
            return False, f"上报数据里没有可识别的 645/698 报文（{payload.hex(' ')[:40]}）"
        # 严格判定：与虚拟表实际发出的应答逐字节一致才算抄读通过
        expected_set = {bytes(x) for x in (expected or ())}
        if expected_set:
            for frame in nested:
                if frame in expected_set:
                    return True, f"数据与虚拟表应答一致（{len(frame)}B）"
            return False, (f"数据与虚拟表应答不一致：上报 {nested[0].hex(' ')[:48]}…"
                           f"｜应答 {next(iter(expected_set)).hex(' ')[:48]}…")
        # 没有应答记录时至少要求是「正常应答帧且数据非空」，不能只看 AFN/Fn
        frame = nested[0]
        if is_valid_meter_response(frame):
            return True, f"是有效抄读应答（{len(frame)}B，未比对虚拟表记录）"
        return False, f"不是有效的抄读应答帧（{frame.hex(' ')[:48]}）"

    # acked：只要不是否认就算过（否认在 widget 里已单独判失败）
    return True, ""


def extract_meter_frames(payload: bytes) -> List[bytes]:
    """从 13H F1 上报的数据单元里把内嵌的 645 / 698 报文整帧摘出来。"""
    frames: List[bytes] = []
    buf = bytes(payload or b"")
    # 645：68 <6B 地址> 68 ... 16
    i = 0
    while i < len(buf):
        if buf[i] != 0x68:
            i += 1
            continue
        if i + 8 < len(buf) and buf[i + 7] == 0x68:
            # 数据长度在 i+9
            if i + 9 < len(buf):
                length = buf[i + 9]
                end = i + 10 + length + 2      # 数据 + CS + 16
                if end <= len(buf) and buf[end - 1] == 0x16:
                    frames.append(buf[i:end])
                    i = end
                    continue
        # 698：68 <L 2B> ... 16。注意 698 的 L 是「用户数据长度」，
        # 总长 = L + 2（68 与 L 两字节之外还有 CS/16）；外层 376.2 帧才是 L = 总长。
        # 两种解释都试，取能被 16 正常收尾的那个，避免把 53B 的应答截成 51B 后匹配不上。
        if i + 3 <= len(buf):
            declared = int.from_bytes(buf[i + 1:i + 3], "little")
            for total in (declared + 2, declared):
                end = i + total
                if 5 <= total <= len(buf) - i and end <= len(buf) and buf[end - 1] == 0x16:
                    frames.append(buf[i:end])
                    i = end
                    break
            else:
                i += 1
            continue
        i += 1
    return frames


def is_valid_meter_response(frame: bytes) -> bool:
    """粗判：645 的 91H 应答（数据长度>0）或 698 的 GET-Response。"""
    if len(frame) < 14:
        return False
    if frame[0] != 0x68:
        return False
    # 645：68 addr(6) 68 C L data... CS 16
    if len(frame) > 10 and frame[7] == 0x68:
        ctrl = frame[8]
        length = frame[9]
        # D7=1 表示从站发出（91H = 从站正确应答），且数据非空
        return (ctrl & 0x80) == 0x80 and length > 0
    # 698：GET-Response 的 APDU 标签 0x85
    return 0x85 in frame[8:14]


def default_archive_addrs(net) -> List[str]:
    """组网参数里启用的从节点地址（用于档案/拓扑内容校验）。"""
    try:
        return [n.addr for n in net.active_slaves() if n.addr]
    except Exception:
        return []
