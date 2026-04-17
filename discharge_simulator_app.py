#!/usr/bin/env python3
"""
恒功率放电模拟器 - Streamlit 交互应用
从电芯放电数据出发，模拟任意恒功率放电过程
"""

import streamlit as st
import pandas as pd
import numpy as np
from scipy import interpolate
import matplotlib.pyplot as plt
import tempfile
import os
from datetime import datetime

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="恒功率放电模拟器",
    page_icon="🔋",
    layout="wide"
)

st.title("🔋 恒功率放电模拟器")
st.markdown("---")

# ==================== 侧边栏：参数设置 ====================
st.sidebar.header("⚙️ 参数设置")

# 电芯参数
st.sidebar.subheader("电芯参数")
cell_capacity = st.sidebar.number_input(
    "额定容量 (Ah)",
    value=4.95,
    min_value=0.1,
    max_value=1000.0,
    step=0.01
)
start_soc = st.sidebar.number_input(
    "起始 SoC (%)",
    value=95.0,
    min_value=1.0,
    max_value=100.0,
    step=1.0
) / 100.0

# 放电参数
st.sidebar.subheader("放电参数")
power = st.sidebar.number_input(
    "恒功率 (W)",
    value=290.0,
    min_value=1.0,
    max_value=10000.0,
    step=1.0
)
duration = st.sidebar.number_input(
    "持续时间 (秒)",
    value=90,
    min_value=1,
    max_value=3600,
    step=1
)
dt = st.sidebar.number_input(
    "时间步长 (秒)",
    value=0.1,
    min_value=0.01,
    max_value=1.0,
    step=0.01
)

# 文件上传
st.sidebar.subheader("📁 数据文件")
uploaded_file = st.sidebar.file_uploader(
    "上传放电数据 Excel 文件",
    type=["xlsx"],
    help="文件格式：多列，每 3 列一组（容量、电压、温度），对应不同电流倍率"
)

# ==================== 数据处理函数 ====================
@st.cache_data
def load_discharge_data(filepath):
    """读取多倍率放电数据 - 动态检测表格结构"""
    # 先读取前 3 行分析表格结构
    df_preview = pd.read_excel(filepath, header=None, nrows=3)
    
    # 尝试从表头读取电流值（只检查第 1 行）
    header_row = df_preview.iloc[0]
    currents = []
    
    # 扫描表头行，寻找电流标签
    # 格式可能是："90A", "90", "90A 放电", "Current: 90A" 等
    for col_idx in range(len(header_row)):
        val = header_row.iloc[col_idx]
        if pd.isna(val):
            continue
        
        val_str = str(val).strip()
        
        # 尝试提取电流值
        import re
        # 匹配模式：数字+A（如 "90A"），或纯数字（如 "90"）
        match = re.search(r'(\d+(?:\.\d+)?)\s*[Aa]?', val_str)
        if match:
            try:
                num_val = float(match.group(1))
                # 电流通常是 10-1000A 的整数
                if 10 <= num_val <= 1000:
                    # 检查是否为整数或接近整数（排除容量值）
                    if num_val == int(num_val):
                        if int(num_val) not in currents:
                            currents.append(int(num_val))
            except (ValueError, TypeError):
                continue
    
    # 如果没有从表头找到电流值，使用默认值
    if not currents:
        currents = [90, 80, 70, 60, 50]
    
    # 排序电流值（从大到小）
    currents = sorted(currents, reverse=True)
    
    # 重新读取数据，跳过表头（假设表头占 1 行）
    skip_rows = 1
    df = pd.read_excel(filepath, header=None, skiprows=skip_rows)
    
    all_data = []
    
    # 动态检测列数
    total_cols = len(df.columns)
    cols_per_group = 3  # 假设每组 3 列：容量、电压、温度
    num_groups = total_cols // cols_per_group
    
    # 如果电流值数量与列组数不匹配，以列组数为准
    if len(currents) != num_groups and num_groups > 0:
        if len(currents) > num_groups:
            currents = currents[:num_groups]
        elif len(currents) < num_groups:
            # 补充默认电流值（按常见放电倍率）
            default_currents = [100, 90, 80, 70, 60, 50, 40, 30, 20, 10]
            for curr in default_currents:
                if curr not in currents and len(currents) < num_groups:
                    currents.append(curr)
            currents = sorted(currents, reverse=True)
    
    for i, curr in enumerate(currents):
        col_base = i * cols_per_group
        if col_base + 2 >= total_cols:
            break
            
        cap = pd.to_numeric(df.iloc[:, col_base], errors='coerce').values
        volt = pd.to_numeric(df.iloc[:, col_base + 1], errors='coerce').values
        temp = pd.to_numeric(df.iloc[:, col_base + 2], errors='coerce').values
        
        valid = ~np.isnan(cap)
        cap = cap[valid]
        volt = volt[valid]
        temp = temp[valid]
        
        for c, v, t in zip(cap, volt, temp):
            all_data.append({'current': curr, 'capacity': c, 'voltage': v, 'temperature': t})
    
    result_df = pd.DataFrame(all_data)
    
    # 存储元数据以便显示
    st.session_state['data_metadata'] = {
        'currents': currents,
        'num_groups': len(currents),
        'total_points': len(result_df),
        'skip_rows': skip_rows,
        'total_cols': total_cols
    }
    
    return result_df

def create_2d_interpolator(data):
    """创建 2D 插值函数：voltage = f(capacity, current)"""
    unique_caps = sorted(data['capacity'].unique())
    
    cap_interp_dict = {}
    for cap in unique_caps:
        subset = data[data['capacity'] == cap]
        if len(subset) >= 2:
            interp = interpolate.interp1d(
                subset['current'].values,
                subset['voltage'].values,
                kind='linear',
                bounds_error=False,
                fill_value='extrapolate'
            )
            cap_interp_dict[cap] = interp
    
    cap_list = sorted(cap_interp_dict.keys())
    
    def voltage_func(capacity, current):
        if capacity <= cap_list[0]:
            return float(cap_interp_dict[cap_list[0]](current))
        if capacity >= cap_list[-1]:
            return float(cap_interp_dict[cap_list[-1]](current))
        
        for i in range(len(cap_list) - 1):
            if cap_list[i] <= capacity <= cap_list[i+1]:
                cap_low = cap_list[i]
                cap_high = cap_list[i+1]
                volt_low = cap_interp_dict[cap_low](current)
                volt_high = cap_interp_dict[cap_high](current)
                ratio = (capacity - cap_low) / (cap_high - cap_low)
                voltage = volt_low + ratio * (volt_high - volt_low)
                return float(voltage)
        
        return float(cap_interp_dict[cap_list[-1]](current))
    
    return voltage_func

def simulate_constant_power(voltage_func, cell_cap, start_soc, power, duration, dt):
    """恒功率放电模拟"""
    discharged_capacity = cell_cap * (1 - start_soc)
    remaining_capacity = cell_cap * start_soc
    
    results = {
        'time': [],
        'discharged_capacity': [],
        'remaining_capacity': [],
        'voltage': [],
        'current': [],
        'soc': []
    }
    
    time = 0
    while time <= duration:
        soc = remaining_capacity / cell_cap
        
        if len(results['voltage']) == 0:
            voltage = voltage_func(discharged_capacity, 80)
        else:
            voltage = results['voltage'][-1]
        
        current = power / voltage
        voltage = voltage_func(discharged_capacity, current)
        current = power / voltage
        
        results['time'].append(time)
        results['discharged_capacity'].append(discharged_capacity)
        results['remaining_capacity'].append(remaining_capacity)
        results['voltage'].append(voltage)
        results['current'].append(current)
        results['soc'].append(soc)
        
        if voltage < 2.5 or remaining_capacity <= 0:
            break
        
        delta_capacity = current * dt / 3600
        discharged_capacity += delta_capacity
        remaining_capacity -= delta_capacity
        time += dt
    
    return pd.DataFrame(results)

# ==================== 主界面 ====================
col1, col2 = st.columns([2, 1])

# 初始化 session state
if 'data' not in st.session_state:
    st.session_state.data = None

with col1:
    st.header("📊 放电数据预览")
    
    if uploaded_file:
        # 保存临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name
        
        try:
            data = load_discharge_data(tmp_path)
            st.session_state.data = data  # 保存到 session state
            
            # 显示数据摘要
            st.success(f"✓ 成功加载 {len(data)} 个数据点")
            
            # 显示检测到的表格结构
            if 'data_metadata' in st.session_state:
                meta = st.session_state.data_metadata
                st.info(f"""**📋 表格结构检测**
- 检测到 **{meta['num_groups']}** 组数据（{meta['currents']})
- 跳过表头行数：{meta['skip_rows']}
- 总数据点：{meta['total_points']}""")
            
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.metric("电流范围", f"{data['current'].min()}A - {data['current'].max()}A")
            with col_b:
                st.metric("容量范围", f"{data['capacity'].min():.3f} - {data['capacity'].max():.3f} Ah")
            with col_c:
                st.metric("电压范围", f"{data['voltage'].min():.3f} - {data['voltage'].max():.3f} V")
            
            # 显示各倍率曲线
            st.subheader("各倍率放电曲线")
            fig_data, ax_data = plt.subplots(figsize=(10, 6))
            
            for curr in sorted(data['current'].unique(), reverse=True):
                subset = data[data['current'] == curr]
                ax_data.plot(subset['capacity'], subset['voltage'], 
                           label=f'{int(curr)}A', linewidth=1.5)
            
            ax_data.set_xlabel('容量 (Ah)')
            ax_data.set_ylabel('电压 (V)')
            ax_data.set_title('原始放电数据')
            ax_data.grid(True, alpha=0.3)
            ax_data.legend()
            
            st.pyplot(fig_data)
            
        except Exception as e:
            st.error(f"读取文件失败：{str(e)}")
            st.session_state.data = None
    else:
        st.info("👈 请从左侧上传放电数据 Excel 文件")
        st.session_state.data = None

with col2:
    st.header("📝 配置摘要")
    
    st.markdown(f"""
    **电芯参数**
    - 额定容量：{cell_capacity} Ah
    - 起始 SoC: {start_soc*100:.0f}%
    
    **放电条件**
    - 恒功率：{power} W
    - 持续时间：{duration} 秒
    - 时间步长：{dt} 秒
    
    **初始状态**
    - 已放电：{cell_capacity * (1 - start_soc):.3f} Ah
    - 剩余容量：{cell_capacity * start_soc:.3f} Ah
    """)
    
    # 运行按钮
    run_button = st.button("🚀 开始模拟", type="primary", disabled=(st.session_state.data is None))

# ==================== 模拟结果 ====================
if run_button and st.session_state.data is not None:
    try:
        with st.spinner("正在模拟..."):
            # 创建插值函数
            voltage_func = create_2d_interpolator(st.session_state.data)
            
            # 运行模拟
            result = simulate_constant_power(
                voltage_func, cell_capacity, start_soc, 
                power, duration, dt
            )
        
        # 关键指标
        st.markdown("---")
        st.header("📈 模拟结果")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("初始电压", f"{result['voltage'].iloc[0]:.3f} V")
        with col2:
            st.metric("结束电压", f"{result['voltage'].iloc[-1]:.3f} V")
        with col3:
            st.metric("电压变化", f"{result['voltage'].iloc[0] - result['voltage'].iloc[-1]:.3f} V")
        with col4:
            st.metric("实际时长", f"{result['time'].iloc[-1]:.1f} 秒")
        
        col5, col6, col7, col8 = st.columns(4)
        with col5:
            st.metric("初始电流", f"{result['current'].iloc[0]:.2f} A")
        with col6:
            st.metric("结束电流", f"{result['current'].iloc[-1]:.2f} A")
        with col7:
            st.metric("结束 SoC", f"{result['soc'].iloc[-1]*100:.1f}%")
        with col8:
            st.metric("放出容量", f"{result['discharged_capacity'].iloc[-1] - result['discharged_capacity'].iloc[0]:.3f} Ah")
        
        # 曲线图 - 时间为横坐标
        st.subheader("Discharge Curves vs Time")
        
        fig1, axes1 = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
        fig1.suptitle(f'Constant Power Discharge ({power}W, {duration}s)\nStart: {start_soc*100:.0f}% SoC', 
                    fontsize=14, fontweight='bold')
        
        # Voltage vs Time
        ax1 = axes1[0]
        ax1.plot(result['time'], result['voltage'], 'b-', linewidth=2)
        ax1.set_ylabel('Voltage (V)')
        ax1.grid(True, alpha=0.3)
        ax1.set_ylim(2.5, result['voltage'].max() + 0.1)
        
        # Current vs Time
        ax2 = axes1[1]
        ax2.plot(result['time'], result['current'], 'r-', linewidth=2)
        ax2.set_ylabel('Current (A)')
        ax2.grid(True, alpha=0.3)
        ax2.set_ylim(result['current'].min() - 2, result['current'].max() + 2)
        
        # SoC vs Time
        ax3 = axes1[2]
        ax3.plot(result['time'], result['soc'] * 100, 'g-', linewidth=2)
        ax3.set_ylabel('SoC (%)')
        ax3.set_xlabel('Time (s)')
        ax3.grid(True, alpha=0.3)
        ax3.set_ylim(result['soc'].min() * 100 - 5, result['soc'].max() * 100 + 5)
        
        plt.tight_layout()
        st.pyplot(fig1)
        
        # 曲线图 - 容量为横坐标
        st.subheader("Discharge Curves vs Capacity")
        
        # 计算累积放电容量
        discharged_cap = result['discharged_capacity'] - result['discharged_capacity'].iloc[0]
        
        fig2, axes2 = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
        fig2.suptitle(f'Voltage/Current/SoC vs Discharged Capacity\nStart: {start_soc*100:.0f}% SoC', 
                    fontsize=14, fontweight='bold')
        
        # Voltage vs Capacity
        ax4 = axes2[0]
        ax4.plot(discharged_cap, result['voltage'], 'b-', linewidth=2)
        ax4.set_ylabel('Voltage (V)')
        ax4.grid(True, alpha=0.3)
        ax4.set_ylim(2.5, result['voltage'].max() + 0.1)
        
        # Current vs Capacity
        ax5 = axes2[1]
        ax5.plot(discharged_cap, result['current'], 'r-', linewidth=2)
        ax5.set_ylabel('Current (A)')
        ax5.grid(True, alpha=0.3)
        ax5.set_ylim(result['current'].min() - 2, result['current'].max() + 2)
        
        # SoC vs Capacity
        ax6 = axes2[2]
        ax6.plot(discharged_cap, result['soc'] * 100, 'g-', linewidth=2)
        ax6.set_ylabel('SoC (%)')
        ax6.set_xlabel('Discharged Capacity (Ah)')
        ax6.grid(True, alpha=0.3)
        ax6.set_ylim(result['soc'].min() * 100 - 5, result['soc'].max() * 100 + 5)
        
        plt.tight_layout()
        st.pyplot(fig2)
        
        # Smoothness Check
        volt_diff = np.diff(result['voltage'].values)
        st.subheader("Smoothness Check")
        st.write(f"- 最大单步电压变化：**{np.abs(volt_diff).max():.6f} V**")
        st.write(f"- 平均单步电压变化：**{np.abs(volt_diff).mean():.6f} V**")
        st.write(f"- 标准差：**{np.std(volt_diff):.6f} V/步**")
        
        if np.abs(volt_diff).max() < 0.01:
            st.success("✓ 曲线平滑，无跳变")
        else:
            st.warning("⚠️ 曲线可能存在跳变，请检查数据质量")
        
        # 数据下载
        st.subheader("💾 导出结果")
        
        # CSV 下载
        csv = result.to_csv(index=False)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.download_button(
            label="📥 下载 CSV 数据",
            data=csv,
            file_name=f"discharge_simulation_{timestamp}.csv",
            mime="text/csv"
        )
        
        # PNG 下载
        import io
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        st.download_button(
            label="📥 下载曲线图 (PNG)",
            data=buf,
            file_name=f"discharge_curve_{timestamp}.png",
            mime="image/png"
        )
        
        # 详细数据表
        with st.expander("📋 查看详细数据表"):
            st.dataframe(result, use_container_width=True)
    
    except Exception as e:
        st.error(f"❌ 模拟失败：{str(e)}")
        import traceback
        st.code(traceback.format_exc())

# ==================== 页脚 ====================
st.markdown("---")
st.caption("恒功率放电模拟器 v1.0 | 基于二维插值的电芯放电仿真工具")
