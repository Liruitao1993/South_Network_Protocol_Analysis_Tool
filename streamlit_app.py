"""
南网协议解析工具 - Streamlit Web版
"""
import streamlit as st
import json
from protocol_parser import ProtocolFrameParser

# 页面配置
st.set_page_config(
    page_title="南网协议解析工具",
    page_icon="🔌",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS样式
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .result-container {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 20px;
        margin-top: 20px;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        padding: 10px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .error-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
        padding: 10px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .info-box {
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        color: #0c5460;
        padding: 10px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .stTextArea textarea {
        font-family: 'Courier New', monospace;
        font-size: 14px;
    }
    .json-key {
        color: #d73a49;
        font-weight: bold;
    }
    .json-string {
        color: #032f62;
    }
    .json-number {
        color: #005cc5;
    }
    .json-boolean {
        color: #005cc5;
    }
</style>
""", unsafe_allow_html=True)

# 标题
st.markdown('<div class="main-header">🔌 南网协议解析工具</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">支持南网通信协议帧的解析与分析</div>', unsafe_allow_html=True)

# 侧边栏 - 使用说明和示例
with st.sidebar:
    st.header("📖 使用说明")
    st.markdown("""
    ### 输入格式
    - 输入十六进制报文字符串
    - 支持带空格或不带空格的格式
    - 大小写不敏感
    
    ### 示例报文
    **确认帧：**
    ```
    68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16
    ```
    
    **复位硬件帧：**
    ```
    68 0C 00 40 01 00 01 01 02 E8 2D 16
    ```
    
    **添加从节点帧：**
    ```
    68 1A 00 40 40 00 01 04 02 E8 02 AAAAAAABBBBBB 5C 16
    ```
    """)
    
    st.header("📝 快捷操作")
    
    # 示例按钮
    if st.button("📋 加载确认帧示例"):
        st.session_state.frame_input = "680E00000000010001E80005EF16"
        st.rerun()
    
    if st.button("📋 加载复位硬件示例"):
        st.session_state.frame_input = "680C00400100010102E82D16"
        st.rerun()
        
    if st.button("📋 加载添加从节点示例"):
        st.session_state.frame_input = "681A00400400010402E802AAAAAAAAAAAAAABBBBBBBBBBBB5C16"
        st.rerun()

    if st.button("📋 加载启动文件传输示例"):
        st.session_state.frame_input = "681C00400700010702E80105999999999999001000010000ABCD0A8F16"
        st.rerun()

# 主界面
# 输入区域
st.header("📝 输入报文")

# 使用session_state保存输入值
if 'frame_input' not in st.session_state:
    st.session_state.frame_input = ""

# 文本输入框
frame_input = st.text_area(
    "请输入十六进制报文（支持带空格或不带空格）：",
    value=st.session_state.frame_input,
    height=100,
    placeholder="例如：68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16",
    key="frame_textarea"
)

# 更新session_state
if frame_input != st.session_state.frame_input:
    st.session_state.frame_input = frame_input

# 按钮区域
col1, col2, col3 = st.columns([1, 1, 4])

with col1:
    parse_button = st.button("🔍 解析报文", type="primary", use_container_width=True)

with col2:
    clear_button = st.button("🗑️ 清空输入", use_container_width=True)

# 处理清空按钮
if clear_button:
    st.session_state.frame_input = ""
    st.rerun()


def get_byte_description(offset: int, result: dict) -> str:
    """获取字节位置说明"""
    # 帧头
    if offset == 0:
        return "帧起始字符(0x68)"
    
    # 长度域
    if offset in [1, 2]:
        return "长度域(2字节)"
    
    # 控制域
    if offset == 3:
        return "控制域"
    
    # 根据用户数据区长度计算
    if "用户数据区" in result:
        user_data_start = 4
        user_data_len = result["用户数据区"].get("长度", 0)
        
        if user_data_start <= offset < user_data_start + user_data_len:
            rel_offset = offset - user_data_start
            
            # 地址域 (12字节)
            if "地址域" in result["用户数据区"]:
                if rel_offset < 12:
                    if rel_offset < 6:
                        return f"源地址[{rel_offset}]"
                    else:
                        return f"目的地址[{rel_offset-6}]"
                rel_offset -= 12
            
            # AFN
            if rel_offset == 0:
                return "应用功能码(AFN)"
            
            # SEQ
            if rel_offset == 1:
                return "帧序列号(SEQ)"
            
            # DI (4字节)
            if 2 <= rel_offset < 6:
                di_pos = ["DI0", "DI1", "DI2", "DI3"][rel_offset - 2]
                return f"数据标识({di_pos})"
            
            # 数据内容
            if rel_offset >= 6:
                return f"数据内容[{rel_offset-6}]"
        
        # 校验和
        cs_offset = user_data_start + user_data_len
        if offset == cs_offset:
            return "校验和(CS)"
        
        # 结束符
        if offset == cs_offset + 1:
            return "结束符(0x16)"
    
    return ""


# 解析逻辑
if parse_button and frame_input.strip():
    # 去除空格和非法字符
    clean_input = frame_input.replace(" ", "").replace("\n", "").replace("\t", "").strip()
    
    # 验证输入
    if not all(c in '0123456789abcdefABCDEF' for c in clean_input):
        st.error("❌ 输入包含非法字符，请只输入十六进制字符（0-9, A-F）！")
    elif len(clean_input) % 2 != 0:
        st.error("❌ 输入长度为奇数，十六进制字符串必须是偶数长度！")
    else:
        try:
            # 转换为字节
            frame_bytes = bytes.fromhex(clean_input)
            
            # 创建解析器并解析
            parser = ProtocolFrameParser()
            result = parser.parse(frame_bytes)
            
            # 显示解析结果
            st.header("📊 解析结果")
            
            # 显示原始数据信息
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.metric("报文长度", f"{len(frame_bytes)} 字节")
            with col_info2:
                status = "✅ 成功" if result["解析状态"] == "成功" else "❌ 失败"
                st.metric("解析状态", status)
            with col_info3:
                st.metric("原始数据", result["原始数据"][:20] + "..." if len(result["原始数据"]) > 20 else result["原始数据"])
            
            # 如果解析失败，显示错误信息
            if result["解析状态"] == "失败":
                st.error(f"❌ 解析失败：{result['错误信息']}")
            
            # 使用标签页展示不同部分
            tab1, tab2, tab3, tab4 = st.tabs(["📋 完整JSON", "🔍 帧结构", "📡 用户数据区", "🔧 数据标识内容"])
            
            with tab1:
                # 完整JSON，带语法高亮
                json_str = json.dumps(result, ensure_ascii=False, indent=2)
                st.code(json_str, language="json", height=600)
                
                # 下载按钮
                st.download_button(
                    label="📥 下载JSON结果",
                    data=json_str.encode('utf-8'),
                    file_name=f"parse_result_{clean_input[:16]}.json",
                    mime="application/json"
                )
            
            with tab2:
                # 帧结构信息
                if "帧头" in result:
                    with st.expander("📍 帧头", expanded=True):
                        st.json(result["帧头"])
                
                if "长度域" in result:
                    with st.expander("📏 长度域", expanded=True):
                        st.json(result["长度域"])
                
                if "控制域" in result:
                    with st.expander("🎛️ 控制域", expanded=True):
                        st.json(result["控制域"])
                
                if "校验和" in result:
                    with st.expander("✓ 校验和", expanded=True):
                        st.json(result["校验和"])
                
                if "结束符" in result:
                    with st.expander("🏁 结束符", expanded=True):
                        st.json(result["结束符"])
            
            with tab3:
                # 用户数据区
                if "用户数据区" in result:
                    user_data = result["用户数据区"]
                    
                    if "地址域" in user_data:
                        with st.expander("📮 地址域", expanded=True):
                            st.json(user_data["地址域"])
                    
                    if "应用功能码(AFN)" in user_data:
                        with st.expander("⚙️ 应用功能码(AFN)", expanded=True):
                            st.json(user_data["应用功能码(AFN)"])
                    
                    if "帧序列号(SEQ)" in user_data:
                        with st.expander("🔢 帧序列号(SEQ)", expanded=True):
                            st.json(user_data["帧序列号(SEQ)"])
                    
                    if "数据标识(DI)" in user_data:
                        with st.expander("🏷️ 数据标识(DI)", expanded=True):
                            st.json(user_data["数据标识(DI)"])
            
            with tab4:
                # 数据标识内容（详细解析）
                if "用户数据区" in result and "数据标识内容" in result["用户数据区"]:
                    data_content = result["用户数据区"]["数据标识内容"]
                    
                    # 显示业务说明
                    if "用户数据区" in result and "数据标识(DI)" in result["用户数据区"]:
                        di_info = result["用户数据区"]["数据标识(DI)"]
                        if "业务说明" in di_info:
                            st.info(f"📌 **业务类型：** {di_info['业务说明']}")
                    
                    # 显示详细解析结果
                    st.subheader("📋 数据内容详细解析")
                    st.json(data_content)
                    
                    # 如果是列表类型，用表格展示
                    for key, value in data_content.items():
                        if isinstance(value, list) and len(value) > 0:
                            st.subheader(f"📑 {key}")
                            st.dataframe(value, use_container_width=True)
                else:
                    st.info("ℹ️ 此报文无数据标识内容")
            
            # 显示原始字节分析
            with st.expander("🔬 原始字节分析"):
                bytes_data = []
                for i, b in enumerate(frame_bytes):
                    bytes_data.append({
                        "偏移": f"0x{i:04X}",
                        "十进制": i,
                        "十六进制": f"0x{b:02X}",
                        "二进制": f"{b:08b}",
                        "说明": get_byte_description(i, result)
                    })
                st.dataframe(bytes_data, use_container_width=True)
                
        except Exception as e:
            st.error(f"❌ 解析出错：{str(e)}")
            st.exception(e)

elif parse_button and not frame_input.strip():
    st.warning("⚠️ 请输入报文内容！")

# 页脚
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.9rem;">
    <p>🔌 南网协议解析工具 | 基于Python + Streamlit构建</p>
    <p>支持南网通信协议帧的完整解析，包括帧头、控制域、地址域、AFN、DI及数据内容</p>
</div>
""", unsafe_allow_html=True)
