#!/bin/bash
# 个人 AI 工作流自动安装脚本
# 默认全局安装到所有检测到的 harness skills 目录

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 工作流源目录
WORKFLOW_DIR="$HOME/my-ai-workflows/skills"

# 工作流列表
WORKFLOWS=(
    "ipd-fix-workflow"
    "mr-review-workflow"
    "mr-pick-workflow"
)

echo ""
echo "=========================================="
echo "个人 AI 工作流安装脚本"
echo "=========================================="
echo ""

# 检查工作流源目录是否存在
if [ ! -d "$WORKFLOW_DIR" ]; then
    echo -e "${RED}错误: 工作流目录不存在: $WORKFLOW_DIR${NC}"
    exit 1
fi

# 扫描所有可能的 skills 目录
echo -e "${BLUE}扫描 AI Harness skills 目录...${NC}"
echo ""

SKILLS_DIRS=()
HARNESS_NAMES=()

# 全局目录（推荐）
if [ -d "$HOME/.claude/skills" ]; then
    SKILLS_DIRS+=("$HOME/.claude/skills")
    HARNESS_NAMES+=("Claude Code")
    echo -e "${GREEN}✓ 找到 Claude Code 全局目录${NC}: ~/.claude/skills"
fi

if [ -d "$HOME/.codex/skills" ]; then
    SKILLS_DIRS+=("$HOME/.codex/skills")
    HARNESS_NAMES+=("Codex")
    echo -e "${GREEN}✓ 找到 Codex 全局目录${NC}: ~/.codex/skills"
fi

if [ -d "$HOME/.config/opencode/skills" ]; then
    SKILLS_DIRS+=("$HOME/.config/opencode/skills")
    HARNESS_NAMES+=("OpenCode")
    echo -e "${GREEN}✓ 找到 OpenCode 全局目录${NC}: ~/.config/opencode/skills"
fi

# 项目级目录（如果在项目中运行）
if git rev-parse --git-dir > /dev/null 2>&1; then
    PROJECT_ROOT=$(git rev-parse --show-toplevel)

    if [ -d "$PROJECT_ROOT/.agents/skills" ]; then
        SKILLS_DIRS+=("$PROJECT_ROOT/.agents/skills")
        HARNESS_NAMES+=("当前项目 (.agents)")
        echo -e "${GREEN}✓ 找到项目目录${NC}: $PROJECT_ROOT/.agents/skills"
    fi

    if [ -d "$PROJECT_ROOT/.claude/skills" ]; then
        SKILLS_DIRS+=("$PROJECT_ROOT/.claude/skills")
        HARNESS_NAMES+=("当前项目 (.claude)")
        echo -e "${GREEN}✓ 找到项目目录${NC}: $PROJECT_ROOT/.claude/skills"
    fi
fi

echo ""

# 如果没有找到任何目录
if [ ${#SKILLS_DIRS[@]} -eq 0 ]; then
    echo -e "${YELLOW}未找到任何 AI Harness skills 目录${NC}"
    echo ""
    echo "请先安装以下任一 AI Harness:"
    echo "  - Claude Code (会创建 ~/.claude/skills)"
    echo "  - OpenCode/Codex (会创建 ~/.codex/skills)"
    echo ""
    echo "或者在项目中创建 skills 目录:"
    echo "  mkdir -p .agents/skills"
    echo "  mkdir -p .claude/skills"
    echo ""
    exit 1
fi

# 显示将要安装的工作流
echo -e "${BLUE}将要安装的工作流:${NC}"
for workflow in "${WORKFLOWS[@]}"; do
    echo "  • $workflow"
done
echo ""

# 显示将要安装到的目录
echo -e "${BLUE}将要安装到以下目录:${NC}"
for i in "${!SKILLS_DIRS[@]}"; do
    echo "  [$((i+1))] ${HARNESS_NAMES[$i]}: ${SKILLS_DIRS[$i]}"
done
echo ""

# 询问用户确认
read -p "$(echo -e ${YELLOW}是否继续安装? [Y/n]: ${NC})" confirm
confirm=${confirm:-Y}

if [[ ! $confirm =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}安装已取消${NC}"
    exit 0
fi

echo ""
echo "开始安装..."
echo ""

# 统计
installed=0
updated=0
skipped=0

# 遍历所有目录和工作流
for i in "${!SKILLS_DIRS[@]}"; do
    SKILLS_DIR="${SKILLS_DIRS[$i]}"
    HARNESS="${HARNESS_NAMES[$i]}"

    echo -e "${BLUE}[${HARNESS}]${NC}"

    for workflow in "${WORKFLOWS[@]}"; do
        SOURCE="$WORKFLOW_DIR/$workflow"
        TARGET="$SKILLS_DIR/$workflow"

        # 检查源目录是否存在
        if [ ! -d "$SOURCE" ]; then
            echo -e "  ${RED}✗ $workflow: 源目录不存在${NC}"
            continue
        fi

        # 如果目标已存在
        if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
            # 检查是否已经是正确的符号链接
            if [ -L "$TARGET" ] && [ "$(readlink -f "$TARGET")" = "$(readlink -f "$SOURCE")" ]; then
                echo -e "  ${GREEN}✓ $workflow: 已安装${NC}"
                skipped=$((skipped + 1))
            else
                # 备份旧文件/目录
                if [ -d "$TARGET" ] && [ ! -L "$TARGET" ]; then
                    BACKUP="${TARGET}.backup.$(date +%Y%m%d_%H%M%S)"
                    mv "$TARGET" "$BACKUP"
                    echo -e "  ${YELLOW}⚠ $workflow: 备份现有目录到 ${BACKUP##*/}${NC}"
                else
                    rm -f "$TARGET"
                fi

                # 创建新的符号链接
                ln -s "$SOURCE" "$TARGET"
                echo -e "  ${GREEN}✓ $workflow: 已更新${NC}"
                updated=$((updated + 1))
            fi
        else
            # 创建符号链接
            ln -s "$SOURCE" "$TARGET"
            echo -e "  ${GREEN}✓ $workflow: 已安装${NC}"
            installed=$((installed + 1))
        fi
    done

    echo ""
done

echo "=========================================="
echo -e "${GREEN}安装完成!${NC}"
echo "新安装: $installed"
echo "已更新: $updated"
echo "已存在: $skipped"
echo "=========================================="
echo ""
echo -e "${BLUE}使用方式:${NC}"
echo ""
echo "在任何项目中（如果安装到全局目录）或当前项目中："
echo ""
echo "  /ipd-fix-workflow ISS-xxx    - IPD 问题修复"
echo "  /mr-review-workflow           - MR review 流程"
echo "  /mr-pick-workflow !123 !456   - Cherry-pick 工作流"
echo ""
echo "或使用自然语言触发："
echo ""
echo '  "修复 IPD 问题 ISS-xxx"'
echo '  "准备提交 MR"'
echo '  "cherry-pick MR !123 !456"'
echo ""
echo -e "${YELLOW}注意: 部分 Harness 需要重启才能识别新的 skills${NC}"
echo ""
