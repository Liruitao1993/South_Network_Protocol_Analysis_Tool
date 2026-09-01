# 项目图标资源（icons/）

## 目录结构

| 路径 | 内容 |
| --- | --- |
| `lucide/` | Lucide 图标库全量 SVG（2049 枚）+ LICENSE |
| `refresh.svg` | 项目原有图标（保留） |

## lucide/ 来源与许可

- 来源：Lucide Icons — https://lucide.dev （仓库 https://github.com/lucide-icons/lucide ）
- 获取方式：npm 包 `lucide-static@1.38.0` tarball（registry.npmjs.org），
  取包内 `icons/*.svg` 与 `LICENSE`
- 版本：**1.38.0**（2026-09-01 下载）
- 许可：**ISC License**（见 `lucide/LICENSE`）——可商用、可修改、可再分发，
  唯一义务是保留版权声明，因此 `LICENSE` 文件不可删除
- 图标命名：kebab-case，如 `file-text.svg`、`refresh-cw.svg`
- 全部 2049 个文件已通过 XML 解析校验（根元素为 `<svg>`）

## GUI 使用方式（后续集成）

PySide6 的 QIcon 原生支持 SVG（依赖 QtSvg）：

```python
from PySide6.QtGui import QIcon
QIcon(str(Path("icons/lucide") / "settings.svg"))
```

按场景候选图标：

| 场景 | 图标文件（去 .svg） |
| --- | --- |
| 文件 打开/保存/导出 | `file` `folder` `save` `download` `upload` `file-text` |
| 编辑 复制/粘贴/清空 | `copy` `clipboard-paste` `clipboard-list` `trash-2` `eraser` |
| 解析/执行/停止 | `play` `square-stop` `zap` `cpu` |
| 搜索/刷新 | `search` `refresh-cw` |
| 网络/通信 | `network` `wifi` `radio` `plug` `usb` `bluetooth` `activity` |
| 数据库/存储 | `database` `hard-drive` |
| 工具/设置 | `settings` `wrench` `terminal` |
| 状态提示 | `check` `x` `triangle-alert` `info` `eye` |

完整图标检索：https://lucide.dev/icons

> 注意：图标集成进打包产物时，需把 `icons/` 加入 `南网协议解析工具.spec`
> 的 datas；本批次仅入库资源，未改 spec 与任何代码。
