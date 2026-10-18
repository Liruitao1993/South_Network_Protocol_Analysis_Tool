# -*- coding: utf-8 -*-
"""
工具脚本路径引导（tools/ 目录共享）。

所有 tools/ 下的独立维护脚本（`python tools/xxx.py`）在文件头 import 本模块，
即可让脚本无论从项目根还是 tools/ 目录启动，都能：

1. 把项目根目录插入 sys.path[0] —— 从而 `import frame_generator_schema` /
   `import release_check` 等根目录模块导入成功（脚本自身的 sys.path[0] 是
   tools/，不含项目根）；
2. 把项目根设为当前工作目录 —— 部分脚本依赖 cwd 读写仓库根下的数据文件
   （如 oi_to_class.json / dlt645_di.json），此前必须先 `cd` 到项目根才能运行。

用法（放在脚本 docstring / 编码声明之后、业务 import 之前）：

    import _path_setup  # noqa: E402

约定：新脚本一律放入 tools/ 目录并保持此 import；需要中间产物时用
`Path(__file__).resolve().parent` 定位 tools/，不要写回仓库根。
参见 AGENTS.md 与 test/_path_setup.py。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # 项目根目录
TOOLS_DIR = Path(__file__).resolve().parent        # tools/ 目录

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    os.chdir(ROOT)
except OSError:
    pass
