@echo off
REM 恒功率放电模拟器 - Windows 启动脚本
REM 双击此文件即可启动应用

echo ========================================
echo 恒功率放电模拟器
echo ========================================
echo.

REM 检查虚拟环境
if not exist "venv" (
    echo [错误] 未找到虚拟环境 venv
    echo 请先运行：python -m venv venv
    echo 然后运行：venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo [信息] 启动 Streamlit 应用...
echo.

REM 激活虚拟环境并运行
call venv\Scripts\activate.bat
streamlit run discharge_simulator_app.py --server.headless true

pause
