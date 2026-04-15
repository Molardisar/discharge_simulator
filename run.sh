#!/bin/bash
# 恒功率放电模拟器 - Linux 启动脚本
# 用法：./run.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "🔋 恒功率放电模拟器"
echo "========================================"
echo ""

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "[错误] 未找到虚拟环境 venv"
    echo ""
    echo "请先初始化环境："
    echo "  python3 -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install -r requirements.txt"
    echo ""
    exit 1
fi

# 检查依赖
if [ ! -f "venv/bin/streamlit" ]; then
    echo "[错误] 虚拟环境未安装依赖"
    echo ""
    echo "请运行："
    echo "  source venv/bin/activate"
    echo "  pip install -r requirements.txt"
    echo ""
    exit 1
fi

echo "[信息] 启动 Streamlit 应用..."
echo ""
echo "浏览器将自动打开：http://localhost:8501"
echo ""
echo "按 Ctrl+C 停止应用"
echo "========================================"
echo ""

# 启动应用
./venv/bin/streamlit run discharge_simulator_app.py --server.headless true
