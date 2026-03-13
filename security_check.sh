#!/bin/bash
# security_check.sh - 安全代码检查脚本

echo "=== 安全代码检查 ==="
echo ""

echo "1. 检查shell=True的使用..."
echo "----------------------------------------"
grep -r "shell=True" --include="*.py" dlazy/ | grep -v "security.py" | grep -v "test_" || echo "✓ 未发现新的 shell=True 使用"
echo ""

echo "2. 检查未转义的用户输入..."
echo "----------------------------------------"
grep -r "\.format(" --include="*.py" dlazy/ | grep -v "safe_format" | grep -v "test_" | grep -v "security.py" || echo "✓ 未发现未转义的 format 调用"
echo ""

echo "3. 检查危险的subprocess调用..."
echo "----------------------------------------"
grep -r "subprocess\." --include="*.py" dlazy/ | grep -v "run_command_safe" | grep -v "import subprocess" | grep -v "test_" | grep -v "security.py" || echo "✓ 未发现危险的 subprocess 调用"
echo ""

echo "4. 检查路径操作..."
echo "----------------------------------------"
echo "建议检查以下文件中的 Path() 使用:"
find dlazy/ -name "*.py" -exec grep -l "Path(" {} \; | grep -v "security.py" | grep -v "test_"
echo ""

echo "5. 检查配置文件..."
echo "----------------------------------------"
if [ -f "global_config.yaml" ]; then
    echo "发现配置文件: global_config.yaml"
    echo "建议运行: python -c 'from dlazy.config_validator import validate_global_config; import yaml; print(validate_global_config(yaml.safe_load(open(\"global_config.yaml\"))))'"
else
    echo "✓ 未发现配置文件"
fi
echo ""

echo "=== 检查完成 ==="
