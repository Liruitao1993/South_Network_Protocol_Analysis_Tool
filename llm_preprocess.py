# -*- coding: utf-8 -*-
"""LLM 日志预处理模块

提供 OpenAI 兼容 API 客户端、大文件分块器和异步工作线程。
用于在批量解析前对原始日志文件进行智能预处理。
"""
import json
import urllib.request
import urllib.error
from typing import List, Optional, Callable


# ═══════════════════════════════════════════════════════════
# 默认 Prompt 模板
# ═══════════════════════════════════════════════════════════

DEFAULT_PROMPT_TEMPLATES = [
    {
        "name": "提取所有 hex 报文帧",
        "prompt": (
            "你是一个电力通信协议日志分析专家。请从以下日志内容中提取所有有效的十六进制报文帧。\n"
            "规则：\n"
            "1. 每行只输出一个完整的 hex 报文帧（空格分隔的大写十六进制）\n"
            "2. 去除所有时间戳、序号、中文注释、调试信息等非 hex 内容\n"
            "3. 如果一行包含多个帧，分行输出\n"
            "4. 跳过明显不是报文的行（纯文本、空行、分隔线等）\n"
            "5. 保持帧的完整性，不要截断或修改 hex 数据\n"
            "直接输出提取的 hex 帧，每行一个，不要添加解释。"
        )
    },
    {
        "name": "清理日志前缀",
        "prompt": (
            "你是日志清洗专家。请清理以下日志的前缀和无关内容，只保留 hex 报文数据。\n"
            "规则：\n"
            "1. 去除时间戳（如 15:48:16、2026-08-01 10:30:00 等格式）\n"
            "2. 去除行号、序号\n"
            "3. 去除中文注释、调试标记、分隔线\n"
            "4. 保留 hex 数据（空格分隔的大写十六进制字节）\n"
            "5. 每行输出一个干净的 hex 帧\n"
            "直接输出结果，不要解释。"
        )
    },
    {
        "name": "提取 TCP 报文",
        "prompt": (
            "你是网络协议分析专家。请从以下日志中提取所有 TCP 相关的报文数据。\n"
            "规则：\n"
            "1. 识别包含 TCP/IP 协议数据的行\n"
            "2. 提取其中的 hex 载荷数据\n"
            "3. 每行输出一个完整的 hex 报文\n"
            "4. 去除 TCP 头部信息，只保留应用层载荷\n"
            "5. 如果无法确定应用层边界，保留整个 TCP 载荷\n"
            "直接输出 hex 帧，每行一个。"
        )
    },
    {
        "name": "按协议分类提取",
        "prompt": (
            "你是电力通信协议专家。请分析以下日志中的报文，并按协议类型分类。\n"
            "识别以下协议特征：\n"
            "- 南网协议：以 68 开头，含 AFN/DI 字段\n"
            "- 国网协议：以 68 开头，含 AFN+Fn\n"
            "- DLT645：以 68 开头，地址域 6 字节，含 DI\n"
            "- HDLC/DLMS：以 7E 开头\n"
            "- 新一代载波：以 FC 字节开头（低4位 8/9/A/B）\n"
            "- TCP 报文：含 IP/TCP 头部\n"
            "每行输出格式：[协议类型] hex报文\n"
            "例如：[南网] 68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16"
        )
    },
    {
        "name": "修复 hex 格式",
        "prompt": (
            "你是数据清洗专家。请修复以下内容中的 hex 格式问题。\n"
            "规则：\n"
            "1. 统一为大写十六进制，空格分隔\n"
            "2. 修复常见问题：小写转大写、冒号分隔转空格、逗号去除\n"
            "3. 合并被换行打断的帧\n"
            "4. 去除非 hex 字符（保留空格和换行）\n"
            "5. 每行一个完整的 hex 帧\n"
            "直接输出修复后的结果。"
        )
    },
]


# ═══════════════════════════════════════════════════════════
# LLM API 客户端
# ═══════════════════════════════════════════════════════════

class LLMAPIClient:
    """OpenAI 兼容 API 客户端

    支持任何兼容 OpenAI /chat/completions 接口的服务：
    - OpenAI (api.openai.com)
    - Azure OpenAI
    - 本地 Ollama (localhost:11434/v1)
    - 其他兼容 API
    """

    def __init__(self, endpoint: str, api_key: str, model: str,
                 timeout: int = 120):
        """
        Args:
            endpoint: API 基础 URL，如 "https://api.openai.com/v1"
            api_key: API 密钥
            model: 模型名称，如 "gpt-4o"
            timeout: 请求超时秒数
        """
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def chat(self, system_prompt: str, user_content: str,
             temperature: float = 0.0) -> str:
        """发送聊天请求，返回纯文本响应

        Args:
            system_prompt: 系统提示词（预处理指令）
            user_content: 用户内容（日志文本）
            temperature: 温度参数，0.0 = 确定性输出

        Returns:
            LLM 响应的纯文本内容

        Raises:
            ConnectionError: 网络连接失败
            TimeoutError: 请求超时
            ValueError: API 返回错误或格式异常
        """
        url = self._chat_url()

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": temperature,
            "reasoning_effort": "none",  # 关闭大模型思考，直接输出结果
        }

        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "LLMPreprocess/1.0",
        }

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise ConnectionError(f"API 连接失败: {e}") from e
        except TimeoutError:
            raise TimeoutError(f"API 请求超时 ({self.timeout}s)")
        except json.JSONDecodeError:
            raise ValueError("API 响应格式错误（非 JSON）")

        # 提取响应内容
        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            raise ValueError(f"API 响应结构异常: {json.dumps(body, ensure_ascii=False)[:200]}")

    def _chat_url(self) -> str:
        """拼接 chat completions URL，自动处理 endpoint 尾部重复路径"""
        base = self.endpoint.rstrip("/")
        # 如果用户把 /chat/completions 也填进了 endpoint，不要再拼一次
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def test_connection(self) -> str:
        """测试 API 连接，发送一条轻量级请求验证连通性

        Returns:
            成功时返回确认信息

        Raises:
            连接/认证失败时抛出异常
        """
        url = self._chat_url()
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "LLMPreprocess/1.0",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                model_used = body.get("model", self.model)
                return f"连接成功，模型: {model_used}"
        except urllib.error.HTTPError as e:
            code = e.code
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                err_body = ""
            if code == 401:
                raise ValueError("API key 无效（401 Unauthorized）")
            elif code == 403:
                # 检测 Cloudflare 1010 错误（域名被拦截）
                hint = ""
                if "1010" in err_body:
                    hint = (
                        "\n\nCloudflare error 1010: 域名所有者禁止了浏览器访问。\n"
                        "如果你用的是 opencode.ai 等服务，请确认：\n"
                        "1) API 地址是否正确（通常应填 https://xxx.xxx.com/v1）\n"
                        "2) 该服务是否支持直接 API 调用（而非仅限浏览器/客户端）"
                    )
                raise ValueError(
                    f"API 返回 403 Forbidden：权限不足或模型不可用\n"
                    f"请检查：1) API key 是否正确  2) 模型名称 '{self.model}' 是否存在  "
                    f"3) 账户是否有该模型的访问权限\n"
                    f"4) Endpoint URL 是否正确（当前: {self.endpoint}）\n"
                    f"详情: {err_body}{hint}"
                )
            elif code == 404:
                raise ValueError(
                    f"API 返回 404：端点不存在，请检查 URL '{self.endpoint}'\n"
                    f"详情: {err_body}"
                )
            else:
                raise ConnectionError(f"HTTP {code}: {e.reason}\n{err_body}")
        except urllib.error.URLError as e:
            raise ConnectionError(f"连接失败: {e}")


# ═══════════════════════════════════════════════════════════
# 大文件分块器
# ═══════════════════════════════════════════════════════════

class LLMChunker:
    """按行数自动分块，适配 LLM token 限制"""

    def __init__(self, chunk_lines: int = 200):
        """
        Args:
            chunk_lines: 每块最大行数
        """
        self.chunk_lines = max(1, chunk_lines)

    def chunk(self, text: str) -> List[str]:
        """将文本按行数分块

        Args:
            text: 输入文本

        Returns:
            分块后的文本列表
        """
        lines = text.splitlines(keepends=True)
        if not lines:
            return []
        return [
            "".join(lines[i:i + self.chunk_lines])
            for i in range(0, len(lines), self.chunk_lines)
        ]


# ═══════════════════════════════════════════════════════════
# 异步工作线程（Qt）
# ═══════════════════════════════════════════════════════════

try:
    from PySide6.QtCore import QThread, Signal as QtSignal
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

if _HAS_QT:
    class LLMWorker(QThread):
        """异步 LLM 调用工作线程

        Signals:
            progress(str): 处理进度信息
            finished(str): 最终合并结果
            error(str): 错误信息
        """
        progress = QtSignal(str)
        finished = QtSignal(str)
        error = QtSignal(str)

        def __init__(self, client: LLMAPIClient, chunker: LLMChunker,
                     prompt: str, content: str, parent=None):
            super().__init__(parent)
            self.client = client
            self.chunker = chunker
            self.prompt = prompt
            self.content = content
            self._cancelled = False

        def cancel(self):
            """取消执行"""
            self._cancelled = True

        def run(self):
            try:
                chunks = self.chunker.chunk(self.content)
                if not chunks:
                    self.error.emit("输入内容为空")
                    return

                results = []
                total = len(chunks)
                for i, chunk in enumerate(chunks):
                    if self._cancelled:
                        self.finished.emit("\n".join(results))
                        return

                    self.progress.emit(f"处理中... ({i + 1}/{total})")
                    result = self.client.chat(self.prompt, chunk)
                    results.append(result)

                self.finished.emit("\n".join(results))
            except Exception as e:
                self.error.emit(str(e))
