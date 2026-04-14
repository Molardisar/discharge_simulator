# 🛠️ 开发指南

## 快速开始

### 环境设置

```bash
# 1. 克隆仓库
git clone <repo-url>
cd dischage_simulator

# 2. 创建虚拟环境
python3 -m venv venv

# 3. 激活虚拟环境
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# 4. 安装依赖
pip install -r requirements.txt

# 5. 启动应用
streamlit run discharge_simulator_app.py
```

### 开发模式

```bash
# 启用自动重载
streamlit run discharge_simulator_app.py --server.headless true

# 或使用 watchmedo 自动重启
pip install watchdog
watchmedo auto-restart --pattern="*.py" --recursive -- \
    streamlit run discharge_simulator_app.py
```

---

## 代码结构

### 主程序组织

```python
dischage_simulator_app.py
│
├── 页面配置 (第 1-15 行)
│   └── st.set_page_config()
│
├── 侧边栏 (第 18-60 行)
│   ├── 电芯参数输入
│   ├── 放电参数输入
│   └── 文件上传
│
├── 数据处理函数 (第 63-130 行)
│   ├── load_discharge_data()
│   └── create_2d_interpolator()
│
├── 模拟引擎 (第 133-180 行)
│   └── simulate_constant_power()
│
├── 主界面 (第 183-240 行)
│   ├── 数据预览区
│   └── 配置摘要区
│
├── 模拟结果 (第 243-320 行)
│   ├── 关键指标
│   ├── 曲线图
│   ├── 平滑度验证
│   └── 导出功能
│
└── 页脚 (第 323 行)
```

### 函数职责

| 函数 | 行数 | 职责 | 输入 | 输出 |
|------|------|------|------|------|
| `load_discharge_data()` | 63-95 | 读取 Excel，解析多列结构 | filepath | DataFrame |
| `create_2d_interpolator()` | 97-130 | 构建 V=f(Q,I) 插值函数 | DataFrame | Callable |
| `simulate_constant_power()` | 133-180 | 时间步进模拟 | 参数 | DataFrame |

---

## 开发任务

### 添加新特征

#### 示例：添加恒流放电模式

1. **侧边栏添加选择器**
   ```python
   mode = st.sidebar.selectbox(
       "放电模式",
       ["恒功率", "恒流"]
   )
   
   if mode == "恒流":
       current = st.sidebar.number_input("电流 (A)", value=80.0)
   else:
       power = st.sidebar.number_input("功率 (W)", value=290.0)
   ```

2. **修改模拟函数**
   ```python
   def simulate(mode, ...):
       if mode == "恒流":
           # 恒流逻辑
           I = current
           V = voltage_func(Q, I)
           P = V * I
       else:
           # 恒功率逻辑（现有）
           ...
   ```

3. **更新结果展示**
   ```python
   if mode == "恒流":
       st.metric("恒定电流", f"{current} A")
   else:
       st.metric("恒定功率", f"{power} W")
   ```

### 优化插值算法

#### 当前实现：双线性插值

```python
def voltage_func(Q, I):
    # 找到 Q_low, Q_high
    # 电流方向插值 → V_low, V_high
    # 容量方向插值 → V
    return V
```

#### 改进：三次样条插值

```python
from scipy.interpolate import interp2d, RectBivariateSpline

# 创建 2D 样条插值
interp_func = RectBivariateSpline(
    unique_caps,  # 容量轴
    currents,     # 电流轴
    voltage_grid  # 电压矩阵
)

def voltage_func(Q, I):
    return interp_func(Q, I)[0, 0]
```

**优点**：更平滑，适合非线性区域  
**缺点**：计算开销略大

---

## 测试

### 单元测试

创建 `tests/test_interpolation.py`:

```python
import pytest
import numpy as np
from discharge_simulator_app import create_2d_interpolator

def test_interpolation_smoothness():
    # 创建测试数据
    data = pd.DataFrame({
        'current': [50, 60, 70, 50, 60, 70],
        'capacity': [0.0, 0.0, 0.0, 0.1, 0.1, 0.1],
        'voltage': [3.9, 3.85, 3.8, 3.85, 3.8, 3.75]
    })
    
    voltage_func = create_2d_interpolator(data)
    
    # 测试平滑性
    voltages = [voltage_func(0.05, I) for I in np.linspace(50, 70, 100)]
    diffs = np.diff(voltages)
    
    assert np.max(np.abs(diffs)) < 0.01  # 单步变化 < 10mV
```

运行测试：
```bash
pip install pytest
pytest tests/
```

### 性能测试

创建 `benchmarks/benchmark_simulation.py`:

```python
import time
import numpy as np

def benchmark(dt_values):
    for dt in dt_values:
        start = time.time()
        result = simulate_constant_power(..., dt=dt)
        elapsed = time.time() - start
        print(f"dt={dt}s: {elapsed:.3f}s, {len(result)} steps")

benchmark([0.1, 0.05, 0.01])
```

---

## 调试技巧

### Streamlit 调试

```python
# 显示中间变量
st.write("调试信息:", intermediate_value)

# 显示 DataFrame 形状
st.write("数据形状:", df.shape)

# 显示异常
try:
    result = some_function()
except Exception as e:
    st.error(f"错误：{e}")
    import traceback
    st.code(traceback.format_exc())
```

### 插值调试

```python
# 检查插值点分布
unique_caps = sorted(data['capacity'].unique())
print(f"容量点数量：{len(unique_caps)}")
print(f"容量范围：{min(unique_caps)} - {max(unique_caps)}")

# 检查某容量的电流覆盖
cap = 1.0
subset = data[data['capacity'] == cap]
print(f"{cap} Ah 处的电流：{subset['current'].tolist()}")
```

### 模拟过程可视化

```python
# 在模拟循环中添加
if t % 10 == 0:  # 每 10 步打印
    print(f"t={t:.1f}s: V={V:.4f}V, I={I:.2f}A, SoC={soc*100:.1f}%")
```

---

## 性能优化

### 当前瓶颈

1. **Python 循环**：900 步 × 每步插值查找
2. **插值查找**：线性搜索容量边界

### 优化方案

#### 1. 向量化模拟

```python
# 当前：循环
results = []
for t in range(900):
    ...

# 优化：向量化
times = np.arange(0, 90, dt)
# 使用 numpy 的 accumulate 或 scipy 的 ODE 求解器
```

**预期**：10-100x 加速

#### 2. 二分查找边界

```python
# 当前：线性搜索
for i in range(len(cap_list) - 1):
    if cap_list[i] <= Q <= cap_list[i+1]:
        ...

# 优化：二分查找
import bisect
idx = bisect.bisect_right(cap_list, Q) - 1
cap_low = cap_list[idx]
cap_high = cap_list[idx + 1]
```

**预期**：O(log n) vs O(n)

#### 3. 预计算插值网格

```python
# 预计算规则网格上的电压
voltage_grid = np.zeros((len(caps), len(currents)))
for i, cap in enumerate(caps):
    for j, curr in enumerate(currents):
        voltage_grid[i, j] = ...

# 模拟时使用 griddata 快速插值
from scipy.interpolate import griddata
V = griddata(points, values, (Q, I), method='linear')
```

---

## 代码风格

### 命名约定

```python
# 变量：小写 + 下划线
cell_capacity = 4.95
start_soc = 0.95

# 函数：小写 + 下划线
def load_discharge_data():
    ...

# 类：大驼峰（如有）
class DischargeSimulator:
    ...

# 常量：全大写
CELL_CAPACITY_DEFAULT = 4.95
DT_DEFAULT = 0.1
```

### 文档字符串

```python
def simulate_constant_power(voltage_func, cell_cap, start_soc, power, duration, dt):
    """
    恒功率放电模拟
    
    参数:
        voltage_func: 电压插值函数 V = f(Q, I)
        cell_cap: 电芯额定容量 (Ah)
        start_soc: 起始 SoC (0-1)
        power: 恒功率 (W)
        duration: 时长 (秒)
        dt: 时间步长 (秒)
    
    返回:
        DataFrame: {time, discharged_capacity, remaining_capacity, voltage, current, soc}
    
    异常:
        ValueError: 当参数超出合理范围时
    """
    ...
```

---

## 版本发布

### 版本号规范

遵循 Semantic Versioning: `MAJOR.MINOR.PATCH`

- **MAJOR**: 不兼容的 API 变更
- **MINOR**: 向后兼容的功能新增
- **PATCH**: 向后兼容的问题修复

### 发布流程

```bash
# 1. 更新版本号 (README.md, 代码注释)
# 2. 更新 CHANGELOG.md
# 3. 提交
git add -A
git commit -m "Bump version to v1.1.0"
git tag v1.1.0

# 4. 推送
git push origin main
git push origin v1.1.0

# 5. 创建 GitHub Release
# https://github.com/<user>/dischage_simulator/releases/new
```

---

## 故障排除

### 常见问题

#### 1. Streamlit 端口被占用

```bash
# 错误：Port 8501 is in use
# 解决：使用其他端口
streamlit run discharge_simulator_app.py --server.port 8502
```

#### 2. 中文字体缺失

```python
# matplotlib 中文显示为方块
# 解决：安装中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False
```

#### 3. Excel 读取失败

```python
# 错误：Excel file format cannot be determined
# 检查：文件扩展名是否为 .xlsx
# 解决：另存为 .xlsx 格式
```

#### 4. 插值外推警告

```python
# 当查询点超出数据范围时
# 解决：检查数据覆盖范围
print(f"容量范围：{data['capacity'].min()} - {data['capacity'].max()}")
print(f"电流范围：{data['current'].min()} - {data['current'].max()}")
```

---

## 贡献指南

### 提交 PR 前检查清单

- [ ] 代码通过测试
- [ ] 更新文档（README/ARCHITECTURE）
- [ ] 更新 CHANGELOG
- [ ] 无 lint 错误
- [ ] 性能无显著下降

### 提交信息格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

**示例**：
```
feat(simulation): 添加恒流放电模式

- 新增 mode 参数支持恒流
- 更新 UI 选择器
- 添加单元测试

Closes #12
```

---

**文档版本**: v1.0  
**最后更新**: 2026-04-14  
**维护者**: Claw_395
