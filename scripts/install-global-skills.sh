#!/bin/bash
#
# 全局 Skill 安装脚本（支持多 agent/harness）
#
# 功能：
# 1. 检查全局 skill 是否已安装
# 2. 引导用户从 Agentic Hub 下载 skill
# 3. 自动创建符号链接到多个 agent/harness 目录
#
# 使用方式：
#   ./scripts/install-global-skills.sh          # 安装所有全局 skill
#   ./scripts/install-global-skills.sh glab      # 安装指定 skill
#   ./scripts/install-global-skills.sh --status  # 显示安装状态
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

# Harness 目录列表（与 setup.py 一致）
declare -A HARNESS_DIRS=(
    ["Claude Code"]="$HOME/.claude/skills"
    ["Codex"]="$HOME/.codex/skills"
    ["OpenCode"]="$HOME/.config/opencode/skills"
    ["DSH (用户级)"]="$HOME/.agents/skills"
)

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
    local installed_in=()

    # 检查所有 harness 目录
    for harness_name in "${!HARNESS_DIRS[@]}"; do
        local skills_dir="${HARNESS_DIRS[$harness_name]}"
        if [ -L "$skills_dir/$skill_name" ] || [ -d "$skills_dir/$skill_name" ]; then
            installed_in+=("$harness_name")
        fi
    done

    if [ ${#installed_in[@]} -gt 0 ]; then
        echo "${installed_in[*]}"
        return 0
    fi

    return 1
}

# 创建符号链接
create_symlinks() {
    local skill_name=$1
    local source_dir="$AGENTS_SKILLS_DIR/$skill_name"
    local created=0

    for harness_name in "${!HARNESS_DIRS[@]}"; do
        local skills_dir="${HARNESS_DIRS[$harness_name]}"

        # 跳过 DSH (用户级)，因为 source_dir 就在这个目录
        if [ "$harness_name" = "DSH (用户级)" ]; then
            continue
        fi

        # 创建目录
        mkdir -p "$skills_dir"

        # 检查是否已存在
        if [ -L "$skills_dir/$skill_name" ] || [ -d "$skills_dir/$skill_name" ]; then
            print_info "$harness_name: 已存在"
            continue
        fi

        # 创建符号链接
        ln -s "$source_dir" "$skills_dir/$skill_name"
        print_success "$harness_name: 创建符号链接"
        created=$((created + 1))
    done

    return $created
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
    local installed_in=$(check_skill_installed "$skill_name")
    if [ $? -eq 0 ]; then
        print_success "$skill_name 已安装在: $installed_in"
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

    # 创建符号链接到所有 harness 目录
    print_info "创建符号链接到所有 agent/harness 目录..."
    create_symlinks "$skill_name"

    print_success "$skill_name 安装完成"
    return 0
}

# 显示安装状态
show_status() {
    print_header "全局 Skill 安装状态"

    for skill_name in "${!SKILL_CONFIGS[@]}"; do
        local config="${SKILL_CONFIGS[$skill_name]}"
        local description=$(echo "$config" | cut -d'|' -f2)

        print_section "$skill_name"
        print_info "描述: $description"

        local installed_in=$(check_skill_installed "$skill_name")
        if [ $? -eq 0 ]; then
            print_success "已安装在: $installed_in"
        else
            print_warning "未安装"
        fi
    done
}

# 主函数
main() {
    print_header "全局 Skill 安装脚本 (多 Agent/Harness)"

    # 创建目录
    mkdir -p "$AGENTS_SKILLS_DIR"

    # 检查参数
    if [ "$1" = "--status" ] || [ "$1" = "-s" ]; then
        show_status
        exit 0
    fi

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
