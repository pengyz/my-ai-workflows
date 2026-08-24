#!/bin/bash
#
# 全局 Skill 安装脚本
#
# 功能：
# 1. 检查全局 skill 是否已安装
# 2. 引导用户从 Agentic Hub 下载 skill
# 3. 自动创建符号链接
#
# 使用方式：
#   ./scripts/install-global-skills.sh          # 安装所有全局 skill
#   ./scripts/install-global-skills.sh glab      # 安装指定 skill
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
AGENTS_SKILLS_DIR="$HOME/.agents/skills"
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"

# Skill 配置
declare -A SKILL_CONFIGS=(
    ["glab"]="https://agentichub.mioffice.cn/skills/2025|GitLab 全能操作 skill"
    ["ipd-mcp-setup"]="https://agentichub.mioffice.cn/skills/526|IPD 问题库 MCP 配置 skill"
)

# 打印函数
print_header() {
    echo -e "${BLUE}"
    echo "============================================================"
    echo "  $1"
    echo "============================================================"
    echo -e "${NC}"
}

print_section() {
    echo ""
    echo -e "${YELLOW}📋 $1${NC}"
    echo -e "${YELLOW}----------------------------------------${NC}"
}

print_success() {
    echo -e "${GREEN}  ✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}  ⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}  ❌ $1${NC}"
}

print_info() {
    echo "  ℹ️  $1"
}

# 检查 skill 是否已安装
check_skill_installed() {
    local skill_name=$1

    # 检查 .agents/skills 目录
    if [ -d "$AGENTS_SKILLS_DIR/$skill_name" ]; then
        return 0
    fi

    # 检查 .claude/skills 目录
    if [ -L "$CLAUDE_SKILLS_DIR/$skill_name" ] || [ -d "$CLAUDE_SKILLS_DIR/$skill_name" ]; then
        return 0
    fi

    return 1
}

# 安装 skill
install_skill() {
    local skill_name=$1
    local config="${SKILL_CONFIGS[$skill_name]}"
    local url=$(echo "$config" | cut -d'|' -f1)
    local description=$(echo "$config" | cut -d'|' -f2)

    print_section "安装 $skill_name"
    print_info "描述: $description"
    print_info "平台: $url"
    echo ""

    # 检查是否已安装
    if check_skill_installed "$skill_name"; then
        print_success "$skill_name 已安装"
        return 0
    fi

    print_warning "$skill_name 未安装"
    echo ""
    print_info "请按以下步骤安装："
    echo ""
    print_info "1. 访问 Agentic Hub 平台："
    print_info "   $url"
    echo ""
    print_info "2. 点击"下载"按钮下载 skill"
    echo ""
    print_info "3. 解压到 ~/.agents/skills/ 目录："
    print_info "   mkdir -p ~/.agents/skills/$skill_name"
    print_info "   unzip ~/Downloads/$skill_name.zip -d ~/.agents/skills/"
    echo ""
    print_info "4. 创建符号链接："
    print_info "   ln -s ~/.agents/skills/$skill_name ~/.claude/skills/$skill_name"
    echo ""

    # 询问用户是否已完成下载
    read -p "是否已完成下载并解压？(y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_warning "跳过 $skill_name 安装"
        return 1
    fi

    # 检查解压目录
    if [ ! -d "$AGENTS_SKILLS_DIR/$skill_name" ]; then
        print_error "未找到 $skill_name 解压目录"
        print_info "请确认已解压到: $AGENTS_SKILLS_DIR/$skill_name"
        return 1
    fi

    # 创建符号链接
    mkdir -p "$CLAUDE_SKILLS_DIR"
    if [ -L "$CLAUDE_SKILLS_DIR/$skill_name" ]; then
        print_info "符号链接已存在，跳过创建"
    else
        ln -s "$AGENTS_SKILLS_DIR/$skill_name" "$CLAUDE_SKILLS_DIR/$skill_name"
        print_success "创建符号链接: $CLAUDE_SKILLS_DIR/$skill_name"
    fi

    print_success "$skill_name 安装完成"
    return 0
}

# 主函数
main() {
    print_header "全局 Skill 安装脚本"

    # 创建目录
    mkdir -p "$AGENTS_SKILLS_DIR"
    mkdir -p "$CLAUDE_SKILLS_DIR"

    # 检查参数
    if [ $# -eq 0 ]; then
        # 安装所有 skill
        for skill_name in "${!SKILL_CONFIGS[@]}"; do
            install_skill "$skill_name"
        done
    else
        # 安装指定 skill
        for skill_name in "$@"; do
            if [ -z "${SKILL_CONFIGS[$skill_name]}" ]; then
                print_error "未知的 skill: $skill_name"
                print_info "支持的 skill: ${!SKILL_CONFIGS[*]}"
                exit 1
            fi
            install_skill "$skill_name"
        done
    fi

    echo ""
    print_success "安装完成！"
    print_info "请运行: python3 scripts/manage-deps.py check 验证安装"
}

# 运行主函数
main "$@"
