# -*- coding: utf-8 -*-
"""
测试路径引导（test/ 目录共享）。

所有 test/ 下的独立脚本（`python test/test_xxx.py`）在文件头 import 本模块，
即可让测试脚本无论从项目根还是 test/ 目录启动，都能：

1. 把项目根目录插入 sys.path[0] —— 从而 `from protocol_parser import ...` 等
   根目录模块导入成功；
2. 把项目根设为当前工作目录 —— 部分测试依赖 cwd 读取 custom_di.json /
   dlt645_di.json / *.json 数据文件；
3. 把项目根下的 reflex_web/ 也加入 sys.path —— 供 Reflex Web 相关测试
   （test_web_frame_gen_utils.py 等）直接 import reflex_web 模块。

用法（放在测试文件 docstring / 编码声明之后、业务 import 之前）：

    import _path_setup  # noqa: E402

约定：新测试文件一律放入 test/ 目录并保持此 import；项目根目录不再新增
test_*.py。参见 AGENTS.md「测试」章节。
"""
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent  # 项目根目录
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_REFLEX = _ROOT / "reflex_web"
if str(_REFLEX) not in sys.path:
    sys.path.insert(0, str(_REFLEX))
try:
    os.chdir(_ROOT)
except OSError:
    pass
