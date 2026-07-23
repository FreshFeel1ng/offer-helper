#!/usr/bin/env bash
set -e

echo "================================"
echo " offer-helper 环境安装"
echo "================================"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 python3，请先安装 Python 3.10+"
    exit 1
fi
echo "✅ Python $(python3 --version)"

# 安装项目及 CLI
echo ""
echo ">> pip install -e ."
pip3 install -e .

# 安装 Playwright 浏览器
echo ""
echo ">> 安装 Playwright Firefox..."
python3 -m playwright install firefox

echo ""
echo "================================"
echo " 安装完成！使用方式："
echo ""
echo "  启动服务："
echo "    offerhelper server --start --port 8010"
echo "    或 python boss/app.py --port 8010"
echo ""
echo "  浏览器打开 http://127.0.0.1:8010 即可使用"
echo ""
echo "  CLI 示例："
echo "    offerhelper search \"Python\" --city 北京"
echo "    offerhelper status"
echo "    offerhelper doctor"
echo "================================"
