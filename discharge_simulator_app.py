#!/usr/bin/env python3
"""
恒功率放电模拟器 - Streamlit 交互应用
从电芯放电数据出发，模拟任意恒功率放电过程（支持单段/多段工况）
"""

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import tempfile
import os
from datetime import datetime

# 导入核心库
from simulator_core import (
    load_discharge_data,
    create_2d_interpolators,
    simulate_constant_power,
    simulate_multi_segment_power
)

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="恒功率放电模拟器",
    page_icon="🔋",
    layout="wide"
)

st.title("🔋 恒功率放电模拟器")
st.markdown("**支持单段或多段恒功率工况组合**")
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
dt = st.sidebar.number_input(
    "时间步长 (秒)",
    value=0.1,
    min_value=0.01,
    max_value=1.0,
    step=0.01
)

# 温度拟合选项
st.sidebar.subheader("🌡️ 温度设置")
enable_temp_fit = st.sidebar.checkbox(
    "启用温度曲线拟合",
    value=True,
    help="勾选后使用多项式拟合温度曲线（返回小数值，精度更高）；\n不勾选则使用原始数据插值（只有整数温度）"
)

fit_order = st.sidebar.slider(
    "拟合阶数",
    min_value=2,
    max_value=5,
    value=3,
    disabled=not enable_temp_fit,
    help="多项式拟合阶数：2-5 阶，越高曲线越复杂，但可能过拟合"
)

# 文件上传
st.sidebar.subheader("📁 数据文件")
uploaded_file = st.sidebar.file_uploader(
    "上传放电数据 Excel 文件",
    type=["xlsx"],
    help="文件格式：多列，每 3 列一组（容量、电压、温度），对应不同电流倍率"
)

# ==================== 工况段管理 ====================
st.sidebar.subheader("⚡ 工况配置")

# 初始化 session_state
if 'segments' not in st.session_state:
    st.session_state.segments = [{"power": 290.0, "duration": 90.0}]

def add_segment():
    st.session_state.segments.append({"power": 150.0, "duration": 60.0})

def remove_segment(index):
    if len(st.session_state.segments) > 1:
        st.session_state.segments.pop(index)

# 显示工况段卡片
total_duration = 0
for i, seg in enumerate(st.session_state.segments):
    with st.sidebar.container():
        col1, col2, col3 = st.columns([3, 3, 1])
        
        with col1:
            seg_power = st.number_input(
                "功率 (W)",
                value=float(seg['power']),
                min_value=0.01,
                max_value=10000.0,
                step=0.01,
                format="%.2f",
                key=f"power_{i}",
                label_visibility="collapsed"
            )
            seg['power'] = seg_power
        
        with col2:
            seg_duration = st.number_input(
                "时长 (s)",
                value=float(seg['duration']),
                min_value=1.0,
                max_value=100000.0,
                step=1.0,
                key=f"duration_{i}",
                label_visibility="collapsed"
            )
            seg['duration'] = seg_duration
        
        with col3:
            if st.button("🗑️", key=f"remove_{i}", help="删除此工况段"):
                remove_segment(i)
                st.rerun()
        
        total_duration += seg['duration']

# 添加/删除按钮
col_add, col_info = st.sidebar.columns([3, 2])
with col_add:
    if st.button("+ 添加工况段", use_container_width=True):
        add_segment()
        st.rerun()

with col_info:
    st.info(f"**总计**: {len(st.session_state.segments)} 段 / {total_duration} 秒")

# ==================== 数据加载 ====================
if uploaded_file:
    try:
        # 保存临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name
        
        # 加载数据（带缓存）
        data = load_discharge_data(tmp_path)
        st.session_state.data = data
        
        # 删除临时文件
        os.unlink(tmp_path)
        
        # 数据预览
        with st.expander("📊 查看原始数据", expanded=False):
            st.write(f"**数据点总数**: {len(data)}")
            st.write(f"**电流范围**: {data['current'].min():.0f}A - {data['current'].max():.0f}A")
            st.write(f"**容量范围**: {data['capacity'].min():.2f}Ah - {data['capacity'].max():.2f}Ah")
            
            # 绘制原始数据
            fig_data, ax_data = plt.subplots(figsize=(10, 6))
            for current in sorted(data['current'].unique(), reverse=True):
                subset = data[data['current'] == current]
                ax_data.plot(subset['capacity'], subset['voltage'], 
                           label=f'{current:.0f}A', linewidth=2)
            ax_data.set_xlabel('Capacity (Ah)')
            ax_data.set_ylabel('Voltage (V)')
            ax_data.set_title('原始放电数据')
            ax_data.grid(True, alpha=0.3)
            ax_data.legend()
            st.pyplot(fig_data)
            
    except Exception as e:
        st.error(f"❌ 读取文件失败：{str(e)}")
        import traceback
        st.code(traceback.format_exc())
        st.session_state.data = None
else:
    st.info("👈 请从左侧上传放电数据 Excel 文件")
    st.session_state.data = None

# ==================== 模拟执行 ====================
if st.session_state.data is not None:
    # 运行按钮
    if st.button("🚀 开始模拟", type="primary"):
        st.session_state.run_button = True
    else:
        st.session_state.run_button = False

# ==================== 模拟结果 ====================
if st.session_state.get('run_button', False) and st.session_state.data is not None:
    try:
        with st.spinner("正在模拟..."):
            # 创建插值函数（根据用户选项决定是否拟合温度）
            if enable_temp_fit:
                voltage_func, temp_func, current_min, current_max = create_2d_interpolators(
                    st.session_state.data, fit_temp_order=fit_order
                )
            else:
                voltage_func, temp_func, current_min, current_max = create_2d_interpolators(
                    st.session_state.data, fit_temp_order=None
                )
            
            # 判断单段还是多段
            segments = st.session_state.segments
            is_multi_segment = len(segments) > 1
            
            if is_multi_segment:
                # 多段工况模拟（温度连续传递）
                all_results, result = simulate_multi_segment_power(
                    voltage_func, temp_func, cell_capacity, start_soc,
                    segments, dt=dt, start_temperature=None, ambient_temp=25.0
                )
            else:
                # 单段工况（向后兼容）
                seg = segments[0]
                initial_current_guess = (current_min + current_max) / 2
                result = simulate_constant_power(
                    voltage_func, temp_func, cell_capacity, start_soc,
                    seg['power'], seg['duration'], dt,
                    current_guess=initial_current_guess,
                    start_temperature=None, ambient_temp=25.0
                )
        
        # 关键指标
        st.markdown("---")
        st.header("📈 模拟结果")
        
        # 显示工况信息
        if is_multi_segment:
            st.info(f"⚡ **多段工况**: {len(segments)} 段，总时长 {result['time'].iloc[-1]:.1f} 秒")
        
        # 第一行指标（电压）
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("初始电压", f"{result['voltage'].iloc[0]:.3f} V")
        with col2:
            st.metric("结束电压", f"{result['voltage'].iloc[-1]:.3f} V")
        with col3:
            st.metric("电压变化", f"{result['voltage'].iloc[0] - result['voltage'].iloc[-1]:.3f} V")
        with col4:
            st.metric("实际时长", f"{result['time'].iloc[-1]:.1f} 秒")
        
        # 第二行指标（电流）
        col5, col6, col7, col8 = st.columns(4)
        with col5:
            st.metric("初始电流", f"{result['current'].iloc[0]:.2f} A")
        with col6:
            st.metric("结束电流", f"{result['current'].iloc[-1]:.2f} A")
        with col7:
            st.metric("结束 SoC", f"{result['soc'].iloc[-1]*100:.1f}%")
        with col8:
            st.metric("放出容量", f"{result['discharged_capacity'].iloc[-1] - result['discharged_capacity'].iloc[0]:.3f} Ah")
        
        # 第三行指标（温度）
        col9, col10, col11 = st.columns(3)
        with col9:
            st.metric("初始温度", f"{result['temperature'].iloc[0]:.1f} ℃")
        with col10:
            st.metric("最高温度", f"{result['temperature'].max():.1f} ℃")
        with col11:
            st.metric("温升", f"{result['temperature'].max() - result['temperature'].iloc[0]:.1f} ℃")
        
        # 曲线图 - 时间为横坐标
        st.subheader("Discharge Curves vs Time")
        
        fig1, axes1 = plt.subplots(4, 1, figsize=(12, 12), sharex=True)
        fig1.suptitle(f'Constant Power Discharge\nStart: {start_soc*100:.0f}% SoC', 
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
        
        # Temperature vs Time
        ax3 = axes1[2]
        ax3.plot(result['time'], result['temperature'], 'm-', linewidth=2)
        ax3.set_ylabel('Temperature (℃)')
        ax3.grid(True, alpha=0.3)
        ax3.set_ylim(result['temperature'].min() - 1, result['temperature'].max() + 1)
        
        # SoC vs Time
        ax4 = axes1[3]
        ax4.plot(result['time'], result['soc'] * 100, 'g-', linewidth=2)
        ax4.set_ylabel('SoC (%)')
        ax4.set_xlabel('Time (s)')
        ax4.grid(True, alpha=0.3)
        ax4.set_ylim(result['soc'].min() * 100 - 5, result['soc'].max() * 100 + 5)
        
        # 标注工况段边界（多段模式）
        if is_multi_segment and 'segment' in result.columns:
            segment_boundaries = []
            cumulative_time = 0
            for seg in segments:
                cumulative_time += seg['duration']
                segment_boundaries.append(cumulative_time)
            
            for boundary in segment_boundaries[:-1]:  # 不在最后画线
                for ax in axes1:
                    ax.axvline(x=boundary, color='gray', linestyle='--', alpha=0.5)
        
        plt.tight_layout()
        st.pyplot(fig1)
        
        # 曲线图 - 容量为横坐标
        st.subheader("Discharge Curves vs Capacity")
        
        # 计算累积放电容量
        discharged_cap = result['discharged_capacity'] - result['discharged_capacity'].iloc[0]
        
        fig2, axes2 = plt.subplots(4, 1, figsize=(12, 12), sharex=True)
        fig2.suptitle(f'Voltage/Current/SoC/Temperature vs Discharged Capacity\nStart: {start_soc*100:.0f}% SoC', 
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
        
        # Temperature vs Capacity
        ax6 = axes2[2]
        ax6.plot(discharged_cap, result['temperature'], 'm-', linewidth=2)
        ax6.set_ylabel('Temperature (℃)')
        ax6.grid(True, alpha=0.3)
        ax6.set_ylim(result['temperature'].min() - 1, result['temperature'].max() + 1)
        
        # SoC vs Capacity
        ax7 = axes2[3]
        ax7.plot(discharged_cap, result['soc'] * 100, 'g-', linewidth=2)
        ax7.set_ylabel('SoC (%)')
        ax7.set_xlabel('Discharged Capacity (Ah)')
        ax7.grid(True, alpha=0.3)
        ax7.set_ylim(result['soc'].min() * 100 - 5, result['soc'].max() * 100 + 5)
        
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
        fig1.savefig(buf, format='png', dpi=150, bbox_inches='tight')
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
st.markdown("**版本**: v1.1.0 | **作者**: Claw_395 | **日期**: 2026-04-17")
