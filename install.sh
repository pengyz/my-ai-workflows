#!/bin/bash
# 个人 AI 工作流自动安装脚本
# 在项目目录中创建指向个人工作流的符号链接

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 工作流源目录
WORKFLOW_DIR="$HOME/my-ai-workflows/skills"

# 检查是否在 git 仓库中
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "${RED}错误: 请在项目目录中运行此脚本${NC}"
    exit 1
fi

PROJECT_ROOT=$(git rev-parse --show-toplevel)
echo -e "${GREEN}项目根目录: $PROJECT_ROOT${NC}"

# 检测项目的 skills 目录（支持多个）
SKILLS_DIRS=()
if [ -d "$PROJECT_ROOT/.agents/skills" ]; then
    SKILLS_DIRS+=("$PROJECT_ROOT/.agents/skills")
    echo -e "${GREEN}检测到 .agents/skills 目录${NC}"
fi
if [ -d "$PROJECT_ROOT/.claude/skills" ]; then
    SKILLS_DIRS+=("$PROJECT_ROOT/.claude/skills")
    echo -e "${GREEN}检测到 .claude/skills 目录${NC}"
fi

# 检测全局 skills 目录
if [ -d "$HOME/.claude/skills" ]; then
    SKILLS_DIRS+=("$HOME/.claude/skills")
    echo -e "${GREEN}检测到 ~/.claude/skills 目录 (Claude Code 全局)${NC}"
fi
if [ -d "$HOME/.codex/skills" ]; then
    SKILLS_DIRS+=("$HOME/.codex/skills")
    echo -e "${GREEN}检测到 ~/.codex/skills 目录 (OpenCode/Codex 全局)${NC}"
fi
if [ -d "$HOME/.config/opencode/skills" ]; then
    SKILLS_DIRS+=("$HOME/.config/opencode/skills")
    echo -e "${GREEN}检测到 ~/.config/opencode/skills 目录 (OpenCode 全局)${NC}"
fi

if [ ${#SKILLS_DIRS[@]} -eq 0 ]; then
    # 询问用户要创建哪个目录
    echo -e "${YELLOW}未找到 skills 目录，请选择创建位置:${NC}"
    echo "1) .agents/skills"
    echo "2) .claude/skills"
    read -p "请选择 [1-2]: " choice

    case $choice in
        1)
            SKILLS_DIRS=("$PROJECT_ROOT/.agents/skills")
            ;;
        2)
            SKILLS_DIRS=("$PROJECT_ROOT/.claude/skills")
            ;;
        *)
            echo -e "${RED}无效选择${NC}"
            exit 1
            ;;
    esac

    mkdir -p "${SKILLS_DIRS[0]}"
    echo -e "${GREEN}创建目录: ${SKILLS_DIRS[0]}${NC}"
fi

# 工作流列表
WORKFLOWS=(
    "ipd-fix-workflow"
    "mr-review-workflow"
    "mr-pick-workflow"
)

# 安装计数
installed=0
skipped=0
updated=0

echo ""
echo "开始安装个人工作流..."
echo ""

for workflow in "${WORKFLOWS[@]}"; do
    SOURCE="$WORKFLOW_DIR/$workflow"

    # 检查源目录是否存在
    if [ ! -d "$SOURCE" ]; then
        echo -e "${RED}✗ $workflow: 源目录不存在${NC}"
        continue
    fi

    # 在所有检测到的 skills 目录中创建符号链接
    for SKILLS_DIR in "${SKILLS_DIRS[@]}"; do
        TARGET="$SKILLS_DIR/$workflow"

        # 如果目标已存在
        if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
            # 检查是否已经是正确的符号链接
            if [ -L "$TARGET" ] && [ "$(readlink -f "$TARGET")" = "$(readlink -f "$SOURCE")" ]; then
                echo -e "${GREEN}✓ $workflow -> ${SKILLS_DIR##*/}: 已安装${NC}"
                skipped=$((skipped + 1))
            else
                # 备份旧文件/目录
                if [ -d "$TARGET" ] && [ ! -L "$TARGET" ]; then
                    BACKUP="${TARGET}.backup.$(date +%Y%m%d_%H%M%S)"
                    mv "$TARGET" "$BACKUP"
                    echo -e "${YELLOW}⚠ $workflow -> ${SKILLS_DIR##*/}: 备份现有目录到 ${BACKUP##*/}${NC}"
                else
                    rm -f "$TARGET"
                fi

                # 创建新的符号链接
                ln -s "$SOURCE" "$TARGET"
                echo -e "${GREEN}✓ $workflow -> ${SKILLS_DIR##*/}: 已更新${NC}"
                updated=$((updated + 1))
            fi
        else
            # 创建符号链接
            ln -s "$SOURCE" "$TARGET"
            echo -e "${GREEN}✓ $workflow -> ${SKILLS_DIR##*/}: 已安装${NC}"
            installed=$((installed + 1))
        fi
    done
done

echo ""
echo "=========================================="
echo -e "${GREEN}安装完成!${NC}"
echo "新安装: $installed"
echo "已更新: $updated"
echo "已存在: $skipped"
echo "=========================================="
echo ""
echo "使用方式:"
echo "  /ipd-fix-workflow    - IPD 问题修复"
echo "  /mr-review-workflow  - MR review 流程"
echo "  /mr-pick-workflow    - Cherry-pick 工作流"
echo ""
echo "验证安装:"
for SKILLS_DIR in "${SKILLS_DIRS[@]}"; do
    echo "  ls -la $SKILLS_DIR"
done
echo ""
