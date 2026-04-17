# simulator_core.py - 恒功率放电模拟核心库

"""
放电模拟器核心算法库
提供数据加载、插值函数构建、恒功率模拟等功能
可被多个 UI 应用复用（单一工况、多段工况等）
"""

import pandas as pd
import numpy as np
from scipy import interpolate
import re


def load_discharge_data(filepath: str) -> pd.DataFrame:
    """从 Excel 文件加载放电数据
    
    智能检测表格结构：
    - 自动跳过空行
    - 检测电流标签所在行（90A, 80A, ...）
    - 检测列名行（容量，电压，温度）
    - 自动识别数据起始行
    
    返回：{current, capacity, voltage, temperature}
    """
    # 第 1 步：读取原始数据（不跳过任何行）
    df_raw = pd.read_excel(filepath, header=None)
    
    # 第 2 步：找到电流标签所在行
    current_row_idx = None
    currents = []
    
    for row_idx in range(min(5, len(df_raw))):  # 只检查前 5 行
        row_data = df_raw.iloc[row_idx].tolist()
        for col, val in enumerate(row_data):
            val_str = str(val).strip()
            match = re.match(r'^(\d+)A?$', val_str, re.IGNORECASE)
            if match:
                current = int(match.group(1))
                if 10 <= current <= 1000:
                    if current_row_idx is None:
                        current_row_idx = row_idx
                    currents.append((col, current))
        
        if current_row_idx is not None:
            break  # 找到电流标签行
    
    if current_row_idx is None:
        raise ValueError(
            f"未检测到有效的电流标签（格式：90A, 80A 等）\n"
            f"已检查前 5 行，请确认 Excel 包含电流标签"
        )
    
    # 第 3 步：找到列名行（电流标签的下一行）
    header_row_idx = current_row_idx + 1
    
    # 第 4 步：数据从列名行的下一行开始
    data_start_row = header_row_idx + 1
    
    # 第 5 步：读取数据（跳过表头行）
    df_data = pd.read_excel(filepath, skiprows=data_start_row, header=None)
    
    # 按电流值排序（从高到低）
    currents.sort(key=lambda x: x[1], reverse=True)
    
    # 解析数据：每 3 列一组（容量，电压，温度）
    data_list = []
    for i, (col_base, current) in enumerate(currents):
        col_cap = col_base      # 容量列
        col_volt = col_base + 1  # 电压列
        col_temp = col_base + 2  # 温度列
        
        if col_temp >= len(df_data.columns):
            continue
        
        group_data = df_data.iloc[:, col_cap:col_temp+1].copy()
        group_data.columns = ['capacity', 'voltage', 'temperature']
        group_data['current'] = current
        
        data_list.append(group_data)
    
    if not data_list:
        raise ValueError("未能解析任何有效的数据列")
    
    # 合并所有数据
    df = pd.concat(data_list, ignore_index=True)
    
    # 确保数值类型
    df['capacity'] = pd.to_numeric(df['capacity'], errors='coerce')
    df['voltage'] = pd.to_numeric(df['voltage'], errors='coerce')
    df['temperature'] = pd.to_numeric(df['temperature'], errors='coerce')
    df['current'] = pd.to_numeric(df['current'], errors='coerce')
    
    # 删除空值
    df = df.dropna()
    
    return df


def create_2d_interpolators(data: pd.DataFrame) -> tuple:
    """创建 2D 插值函数：voltage = f(capacity, current), temperature = f(capacity, current)
    
    返回：(voltage_func, temp_func, current_min, current_max)
    - voltage_func: 电压插值函数
    - temp_func: 温度插值函数
    - current_min: 数据中的最小电流
    - current_max: 数据中的最大电流
    
    支持单电流数据（返回常数函数）
    """
    unique_caps = sorted(data['capacity'].unique())
    
    # 获取电流范围（用于边界检查和初始猜测）
    all_currents = sorted(data['current'].unique())
    current_min = all_currents[0]
    current_max = all_currents[-1]
    
    volt_interp_dict = {}
    temp_interp_dict = {}
    
    for cap in unique_caps:
        subset = data[data['capacity'] == cap]
        # 即使只有 1 个点，也创建插值函数
        if len(subset) >= 1:
            if len(subset) == 1:
                # 单点：返回常数
                const_voltage = subset['voltage'].values[0]
                const_temp = subset['temperature'].values[0]
                volt_interp_dict[cap] = lambda c, v=const_voltage: v
                temp_interp_dict[cap] = lambda c, t=const_temp: t
            else:
                # 多点：正常插值
                volt_interp = interpolate.interp1d(
                    subset['current'].values,
                    subset['voltage'].values,
                    kind='linear',
                    bounds_error=False,
                    fill_value='extrapolate'
                )
                temp_interp = interpolate.interp1d(
                    subset['current'].values,
                    subset['temperature'].values,
                    kind='linear',
                    bounds_error=False,
                    fill_value='extrapolate'
                )
                volt_interp_dict[cap] = volt_interp
                temp_interp_dict[cap] = temp_interp
    
    cap_list = sorted(volt_interp_dict.keys())
    
    def voltage_func(capacity, current):
        if not cap_list:
            raise ValueError("没有可用的插值数据")
        
        if capacity <= cap_list[0]:
            return float(volt_interp_dict[cap_list[0]](current))
        if capacity >= cap_list[-1]:
            return float(volt_interp_dict[cap_list[-1]](current))
        
        for i in range(len(cap_list) - 1):
            if cap_list[i] <= capacity <= cap_list[i+1]:
                cap_low = cap_list[i]
                cap_high = cap_list[i+1]
                volt_low = volt_interp_dict[cap_low](current)
                volt_high = volt_interp_dict[cap_high](current)
                ratio = (capacity - cap_low) / (cap_high - cap_low)
                voltage = volt_low + ratio * (volt_high - volt_low)
                return float(voltage)
        
        return float(volt_interp_dict[cap_list[-1]](current))
    
    def temperature_func(capacity, current):
        if not cap_list:
            raise ValueError("没有可用的插值数据")
        
        if capacity <= cap_list[0]:
            return float(temp_interp_dict[cap_list[0]](current))
        if capacity >= cap_list[-1]:
            return float(temp_interp_dict[cap_list[-1]](current))
        
        for i in range(len(cap_list) - 1):
            if cap_list[i] <= capacity <= cap_list[i+1]:
                cap_low = cap_list[i]
                cap_high = cap_list[i+1]
                temp_low = temp_interp_dict[cap_low](current)
                temp_high = temp_interp_dict[cap_high](current)
                ratio = (capacity - cap_low) / (cap_high - cap_low)
                temperature = temp_low + ratio * (temp_high - temp_low)
                return float(temperature)
        
        return float(temp_interp_dict[cap_list[-1]](current))
    
    return voltage_func, temperature_func, current_min, current_max


def simulate_constant_power(voltage_func, temp_func, cell_cap, start_soc, power, duration, dt, current_guess=None, ambient_temp=25.0):
    """恒功率放电模拟
    
    参数:
        voltage_func: 电压插值函数 V = f(Q, I)
        temp_func: 温度插值函数 T = f(Q, I)
        cell_cap: 电芯额定容量 (Ah)
        start_soc: 起始 SoC (0-1)
        power: 恒功率 (W)
        duration: 时长 (秒)
        dt: 时间步长 (秒)
        current_guess: 初始电流猜测值（None 时自动估算）
        ambient_temp: 环境温度 (℃)
    
    返回：{time, discharged_capacity, remaining_capacity, voltage, current, soc, temperature}
    """
    discharged_capacity = cell_cap * (1 - start_soc)
    remaining_capacity = cell_cap * start_soc
    
    # 如果没有提供初始电流猜测，使用功率/标称电压估算
    if current_guess is None:
        nominal_voltage = 3.7  # 锂电瓶标称电压
        current_guess = power / nominal_voltage
    
    results = {
        'time': [],
        'discharged_capacity': [],
        'remaining_capacity': [],
        'voltage': [],
        'current': [],
        'soc': [],
        'temperature': []
    }
    
    time = 0
    while time <= duration:
        soc = remaining_capacity / cell_cap
        
        if len(results['voltage']) == 0:
            # 第一次迭代：使用初始猜测电流
            voltage = voltage_func(discharged_capacity, current_guess)
            temperature = temp_func(discharged_capacity, current_guess)
        else:
            voltage = results['voltage'][-1]
            temperature = results['temperature'][-1]
        
        current = power / voltage
        voltage = voltage_func(discharged_capacity, current)
        temperature = temp_func(discharged_capacity, current)
        current = power / voltage
        
        results['time'].append(time)
        results['discharged_capacity'].append(discharged_capacity)
        results['remaining_capacity'].append(remaining_capacity)
        results['voltage'].append(voltage)
        results['current'].append(current)
        results['soc'].append(soc)
        results['temperature'].append(temperature)
        
        if voltage < 2.5 or remaining_capacity <= 0:
            break
        
        delta_capacity = current * dt / 3600
        discharged_capacity += delta_capacity
        remaining_capacity -= delta_capacity
        time += dt
    
    return pd.DataFrame(results)


def simulate_multi_segment_power(voltage_func, temp_func, cell_cap, start_soc, segments, dt=0.1):
    """多段恒功率放电模拟
    
    参数:
        voltage_func: 电压插值函数 V = f(Q, I)
        temp_func: 温度插值函数 T = f(Q, I)
        cell_cap: 电芯额定容量 (Ah)
        start_soc: 初始 SoC (0-1)
        segments: 工况列表，每项为 {"power": float, "duration": int}
        dt: 时间步长 (秒)
    
    返回：
        - all_results: 所有段的 DataFrame 列表
        - combined_result: 拼接后的完整 DataFrame
    """
    all_results = []
    current_soc = start_soc
    time_offset = 0  # 时间累加器
    
    for i, seg in enumerate(segments):
        power = seg['power']
        duration = seg['duration']
        
        # 智能估算初始电流：使用功率/标称电压
        nominal_voltage = 3.7
        current_guess = power / nominal_voltage
        
        # 运行单段模拟
        result = simulate_constant_power(
            voltage_func, temp_func, cell_cap,
            current_soc, power, duration, dt,
            current_guess=current_guess
        )
        
        # 添加段索引
        result['segment'] = i + 1
        
        # 时间累加：当前段的时间 + 之前所有段的总时长
        result['time'] = result['time'] + time_offset
        
        all_results.append(result)
        
        # 更新时间累加器（使用本段实际结束时间）
        time_offset = result['time'].iloc[-1]
        
        # 更新 SoC 为下一段的初始状态
        current_soc = result['soc'].iloc[-1]
        
        # 如果提前终止（电压过低或电量耗尽），停止后续段
        if result['voltage'].iloc[-1] < 2.5 or result['remaining_capacity'].iloc[-1] <= 0:
            break
    
    # 拼接所有段
    combined_result = pd.concat(all_results, ignore_index=True)
    
    return all_results, combined_result
