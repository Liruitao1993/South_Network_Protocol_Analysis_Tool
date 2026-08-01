# 设计文档：监控器日志路径显示与浏览

## 概述
在监控器的过滤器工具栏中，将现有的"开始记录"按钮和状态标签区域增强，添加路径显示和浏览按钮。

## 当前实现分析

### 现有UI布局（过滤器工具栏）
```
[启用过滤] [NID:] [___] [帧类型: 全部] [MSDU类型: 全部] [反向过滤] | [开始记录] [记录中: filename (N帧)] ... [stretch]
```

### 现有CSV记录逻辑
- `_start_csv_recording()`：创建 `Output/` 目录，生成带时间戳的CSV文件
- `_csv_path`：存储当前记录文件的完整路径
- `csv_status_label`：显示记录状态（文件名+帧数）

## 设计方案

### UI变更

#### 新增元素
1. **路径标签** (`csv_path_label`)：显示当前记录文件的完整路径
2. **浏览按钮** (`browse_log_btn`)：打开资源管理器到 `Output` 目录

#### 布局调整
将记录区域从一行改为两行：

**第一行（原有）：**
```
[开始记录] [记录中: filename (N帧)]
```

**第二行（新增）：**
```
[路径: Output/monitor_log_20260729_143022.csv] [浏览]
```

### 代码修改

#### 1. 添加新控件（`_build_ui` 方法）
在 `filter_toolbar` 区域添加：
```python
# 路径显示
self.csv_path_label = QLabel("路径: 未记录")
self.csv_path_label.setStyleSheet("color: #666; font-family: Consolas, monospace;")
self.csv_path_label.setWordWrap(False)
self.csv_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
filter_toolbar.addWidget(self.csv_path_label)

# 浏览按钮
self.browse_log_btn = QPushButton("浏览")
self.browse_log_btn.setFixedWidth(50)
self.browse_log_btn.setToolTip("打开日志目录")
self.browse_log_btn.clicked.connect(self._open_log_directory)
filter_toolbar.addWidget(self.browse_log_btn)
```

#### 2. 修改 `_start_csv_recording` 方法
在设置 `csv_status_label` 后，更新路径显示：
```python
# 显示完整路径
self.csv_path_label.setText(f"路径: {self._csv_path}")
self.csv_path_label.setStyleSheet("color: #333; font-family: Consolas, monospace;")
```

#### 3. 修改 `_stop_csv_recording` 方法
停止后保留路径显示（灰色）：
```python
# 保留路径显示（灰色）
self.csv_path_label.setText(f"路径: {self._csv_path}")
self.csv_path_label.setStyleSheet("color: #888; font-family: Consolas, monospace;")
```

#### 4. 新增 `_open_log_directory` 方法
```python
def _open_log_directory(self):
    """打开日志目录"""
    log_dir = os.path.abspath("Output")
    os.makedirs(log_dir, exist_ok=True)
    try:
        os.startfile(log_dir)  # Windows
    except AttributeError:
        # Linux/Mac fallback
        import subprocess
        subprocess.Popen(["xdg-open", log_dir])
    except OSError:
        pass  # 静默忽略
```

### 数据流
```
用户点击"开始记录"
  → _start_csv_recording()
    → 创建 Output/ 目录
    → 生成 CSV 文件
    → 更新 csv_path_label 显示完整路径
    → 用户可随时点击"浏览"按钮打开目录
```

### 兼容性
- **向后兼容**：不影响现有CSV记录和导出功能
- **跨平台**：使用 `os.startfile` (Windows) 和 `xdg-open` (Linux/Mac) 双路径
- **UI 一致性**：路径标签使用等宽字体，与现有风格协调

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 路径过长导致UI溢出 | 低 | 使用 `setWordWrap(False)` + 手动截断 |
| 打开资源管理器失败 | 低 | 静默忽略，不影响核心功能 |
| 路径显示影响性能 | 极低 | 仅在记录开始/停止时更新一次 |

## 验证方法
1. 启动监控器，点击"开始记录"
2. 验证路径标签显示完整路径（如 `Output/monitor_log_20260729_143022.csv`）
3. 点击"浏览"按钮，验证资源管理器打开 `Output` 目录
4. 停止记录，验证路径保留显示（灰色）
5. 再次开始记录，验证路径更新为新文件
