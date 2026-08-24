#!/bin/bash
#
# Git hooks 安装脚本
#
# 使用方式：
#   ./scripts/install-hooks.sh          # 安装 hooks
#   ./scripts/install-hooks.sh --uninstall  # 卸载 hooks
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
GIT_HOOKS_DIR="$PROJECT_ROOT/.git/hooks"
HOOKS_SOURCE_DIR="$SCRIPT_DIR/hooks"

# 检查是否在 git 仓库中
if [ ! -d "$PROJECT_ROOT/.git" ]; then
    echo -e "${RED}❌ 错误：不在 git 仓库中${NC}"
    exit 1
fi

# 卸载 hooks
if [ "$1" = "--uninstall" ]; then
    echo -e "${YELLOW}🗑️  卸载 git hooks...${NC}"

    for hook in "$GIT_HOOKS_DIR"/*; do
        hook_name=$(basename "$hook")
        if [ -f "$hook" ] && grep -q "my-ai-workflows" "$hook" 2>/dev/null; then
            rm "$hook"
            echo -e "${GREEN}✅ 已卸载: $hook_name${NC}"
        fi
    done

    echo -e "${GREEN}✅ 卸载完成${NC}"
    exit 0
fi

# 安装 hooks
echo -e "${YELLOW}📦 安装 git hooks...${NC}"
echo ""

# 检查 hooks 源目录
if [ ! -d "$HOOKS_SOURCE_DIR" ]; then
    echo -e "${RED}❌ 错误：hooks 源目录不存在: $HOOKS_SOURCE_DIR${NC}"
    exit 1
fi

# 创建 hooks 目录（如果不存在）
mkdir -p "$GIT_HOOKS_DIR"

# 安装每个 hook
installed=0
for hook_file in "$HOOKS_SOURCE_DIR"/*; do
    if [ ! -f "$hook_file" ]; then
        continue
    fi

    hook_name=$(basename "$hook_file")
    target_file="$GIT_HOOKS_DIR/$hook_name"

    # 检查是否已存在其他 hook
    if [ -f "$target_file" ]; then
        if grep -q "my-ai-workflows" "$target_file" 2>/dev/null; then
            echo -e "${YELLOW}⚠️  已存在，更新: $hook_name${NC}"
        else
            echo -e "${YELLOW}⚠️  已存在其他 hook，跳过: $hook_name${NC}"
            echo "  如需覆盖，请先删除: $target_file"
            continue
        fi
    fi

    # 复制并设置权限
    cp "$hook_file" "$target_file"
    chmod +x "$target_file"
    echo -e "${GREEN}✅ 已安装: $hook_name${NC}"
    installed=$((installed + 1))
done

echo ""
if [ $installed -gt 0 ]; then
    echo -e "${GREEN}✅ 安装完成！共安装 $installed 个 hook${NC}"
    echo ""
    echo "使用方式："
    echo "  - 正常提交：git commit"
    echo "  - 跳过验证：git commit --no-verify"
    echo ""
    echo "卸载 hooks："
    echo "  ./scripts/install-hooks.sh --uninstall"
else
    echo -e "${YELLOW}⚠️  没有安装任何 hook${NC}"
fi
