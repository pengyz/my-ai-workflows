#!/usr/bin/env python3
"""
依赖管理脚本

功能：
1. 检查所有依赖状态
2. 自动安装可安装的依赖
3. 提供交互式配置向导

使用方式：
    python3 scripts/manage-deps.py check      # 检查依赖
    python3 scripts/manage-deps.py install    # 安装依赖
    python3 scripts/manage-deps.py setup      # 交互式配置
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path
from typing import Dict, List, Tuple

# 配置
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
SKILLS_DIR = PROJECT_ROOT / "skills"

# 颜色定义
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color

def print_colored(text: str, color: str):
    """打印彩色文本"""
    print(f"{color}{text}{Colors.NC}")

def print_header(text: str):
    """打印标题"""
    print()
    print_colored("=" * 60, Colors.BLUE)
    print_colored(f"  {text}", Colors.BLUE)
    print_colored("=" * 60, Colors.BLUE)

def print_section(text: str):
    """打印章节标题"""
    print()
    print_colored(f"📋 {text}", Colors.YELLOW)
    print_colored("-" * 40, Colors.YELLOW)

def print_success(text: str):
    """打印成功信息"""
    print_colored(f"  ✅ {text}", Colors.GREEN)

def print_warning(text: str):
    """打印警告信息"""
    print_colored(f"  ⚠️  {text}", Colors.YELLOW)

def print_error(text: str):
    """打印错误信息"""
    print_colored(f"  ❌ {text}", Colors.RED)

def print_info(text: str):
    """打印信息"""
    print(f"  ℹ️  {text}")

def run_command(cmd: List[str], check: bool = True) -> Tuple[bool, str]:
    """运行命令"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip()
    except FileNotFoundError:
        return False, f"命令未找到: {cmd[0]}"

# ==================== 检查函数 ====================

def check_command_exists(cmd: str) -> bool:
    """检查命令是否存在"""
    return shutil.which(cmd) is not None

def check_python_package(package: str) -> bool:
    """检查 Python 包是否安装"""
    try:
        __import__(package)
        return True
    except ImportError:
        return False

def check_file_exists(path: Path) -> bool:
    """检查文件是否存在"""
    return path.exists()

def check_env_var(name: str) -> bool:
    """检查环境变量是否设置"""
    return os.environ.get(name) is not None

def check_mcp_config() -> Dict[str, bool]:
    """检查 MCP 配置"""
    results = {}

    # 检查 Claude MCP 配置
    claude_config = Path.home() / ".claude" / "mcp.json"
    if claude_config.exists():
        try:
            import json
            with open(claude_config) as f:
                config = json.load(f)
                results['mi-adt'] = 'mi-adt' in str(config)
        except:
            results['mi-adt'] = False
    else:
        results['mi-adt'] = False

    return results

def check_osbot_repo() -> Dict[str, any]:
    """检查 osbot 仓库"""
    results = {
        'exists': False,
        'path': None,
        'skills': {},
    }

    # 检查环境变量
    osbot_path = os.environ.get('OSBOT_PATH')
    if osbot_path:
        osbot_path = Path(osbot_path)
    else:
        # 尝试常见路径
        common_paths = [
            Path.home() / "workspace" / "osbot",
            Path.home() / "osbot",
            Path("/opt/osbot"),
        ]
        for path in common_paths:
            if path.exists():
                osbot_path = path
                break

    if osbot_path and osbot_path.exists():
        results['exists'] = True
        results['path'] = str(osbot_path)

        # 检查项目级 skills
        skills_dir = osbot_path / ".agents" / "skills"
        if skills_dir.exists():
            for skill_dir in skills_dir.iterdir():
                if skill_dir.is_dir():
                    results['skills'][skill_dir.name] = True

    return results

# 项目级 skill 列表（需要从 osbot 仓库安装）
PROJECT_SKILLS = [
    'osbot-eval',
    'osbot-review',
    'osbot-mr-preflight',
    'osbot-trace-viz',
]

# 全局 skill 列表（需要从 agentichub 安装）
GLOBAL_SKILLS = [
    'glab',
    'ipd-mcp-setup',
]

# skill 安装说明
SKILL_INSTALL_GUIDES = {
    'glab': {
        'source': 'https://agentichub.mioffice.cn/skills/2025',
        'description': 'GitLab CLI skill',
        'install_steps': [
            '1. 访问 Agentic Hub: https://agentichub.mioffice.cn/skills/2025',
            '2. 点击"下载"按钮下载 skill',
            '3. 解压到 ~/.agents/skills/glab/',
            '4. 创建符号链接: ln -s ~/.agents/skills/glab ~/.claude/skills/glab',
        ],
    },
    'ipd-mcp-setup': {
        'source': 'https://agentichub.mioffice.cn/skills/526',
        'description': 'IPD 问题库 MCP 配置 skill',
        'install_steps': [
            '1. 访问 Agentic Hub: https://agentichub.mioffice.cn/skills/526',
            '2. 点击"下载"按钮下载 skill',
            '3. 解压到 ~/.agents/skills/ipd-mcp-setup/',
            '4. 创建符号链接: ln -s ~/.agents/skills/ipd-mcp-setup ~/.claude/skills/ipd-mcp-setup',
        ],
    },
}

def check_project_skills_installed() -> Dict[str, bool]:
    """检查项目级 skill 是否已安装"""
    results = {}
    skills_dir = PROJECT_ROOT / "skills"

    for skill_name in PROJECT_SKILLS:
        skill_path = skills_dir / skill_name
        # 检查是否存在且是符号链接
        if skill_path.exists() or skill_path.is_symlink():
            results[skill_name] = True
        else:
            results[skill_name] = False

    return results

def check_global_skills_installed() -> Dict[str, bool]:
    """检查全局 skill 是否已安装"""
    results = {}

    # 检查 .agents/skills 目录（小米内部 skill 安装位置）
    agents_skills_dir = Path.home() / ".agents" / "skills"

    for skill_name in GLOBAL_SKILLS:
        # 检查 .agents/skills 目录
        skill_path = agents_skills_dir / skill_name
        if skill_path.exists():
            results[skill_name] = True
        else:
            # 检查 Claude skills 目录（符号链接）
            claude_skill_path = Path.home() / ".claude" / "skills" / skill_name
            if claude_skill_path.exists() or claude_skill_path.is_symlink():
                results[skill_name] = True
            else:
                results[skill_name] = False

    return results

def install_project_skills(osbot_path: Path):
    """安装项目级 skill"""
    skills_dir = PROJECT_ROOT / "skills"
    osbot_skills_dir = osbot_path / ".agents" / "skills"

    if not osbot_skills_dir.exists():
        print_error(f"osbot skills 目录不存在: {osbot_skills_dir}")
        return False

    installed = 0
    for skill_name in PROJECT_SKILLS:
        source = osbot_skills_dir / skill_name
        target = skills_dir / skill_name

        if not source.exists():
            print_warning(f"skill 不存在: {skill_name}")
            continue

        if target.exists() or target.is_symlink():
            print_success(f"{skill_name}: 已安装")
            continue

        # 创建符号链接
        try:
            os.symlink(source, target, target_is_directory=True)
            print_success(f"{skill_name}: 安装成功")
            installed += 1
        except Exception as e:
            print_error(f"{skill_name}: 安装失败 - {e}")

    return installed > 0

# ==================== 安装函数 ====================

def install_glab():
    """安装 glab"""
    system = platform.system()

    if system == "Darwin":  # macOS
        print_info("检测到 macOS，使用 brew 安装...")
        success, output = run_command(["brew", "install", "glab"], check=False)
        if success:
            print_success("glab 安装成功")
        else:
            print_error(f"glab 安装失败: {output}")
            print_info("请手动安装: brew install glab")
    elif system == "Linux":
        # 检测发行版
        if check_command_exists("apt"):
            print_info("检测到 Debian/Ubuntu，使用 apt 安装...")
            success, output = run_command(["sudo", "apt", "install", "-y", "glab"], check=False)
            if success:
                print_success("glab 安装成功")
            else:
                print_error(f"glab 安装失败: {output}")
                print_info("请手动安装: https://gitlab.com/gitlab-org/cli#installation")
        elif check_command_exists("yum"):
            print_info("检测到 RHEL/CentOS，请手动安装 glab")
            print_info("参考: https://gitlab.com/gitlab-org/cli#installation")
        else:
            print_warning("未知的 Linux 发行版，请手动安装 glab")
            print_info("参考: https://gitlab.com/gitlab-org/cli#installation")
    elif system == "Windows":
        print_info("检测到 Windows，使用 winget 安装...")
        success, output = run_command(["winget", "install", "GitLab.cli"], check=False)
        if success:
            print_success("glab 安装成功")
        else:
            print_error(f"glab 安装失败: {output}")
            print_info("请手动安装: https://gitlab.com/gitlab-org/cli#installation")
    else:
        print_warning(f"未知系统: {system}，请手动安装 glab")

def install_python_package(package: str):
    """安装 Python 包"""
    print_info(f"安装 {package}...")
    success, output = run_command([sys.executable, "-m", "pip", "install", package], check=False)
    if success:
        print_success(f"{package} 安装成功")
    else:
        print_error(f"{package} 安装失败: {output}")

def setup_ipd_user():
    """设置 IPD_USER 环境变量"""
    print_section("设置 IPD_USER")

    current = os.environ.get('IPD_USER')
    if current:
        print_info(f"当前值: {current}")
        update = input("是否更新? (y/N): ").strip().lower()
        if update != 'y':
            return

    username = input("请输入 IPD 用户名: ").strip()
    if username:
        # 写入 shell 配置文件
        shell = os.environ.get('SHELL', '')
        if 'zsh' in shell:
            config_file = Path.home() / ".zshrc"
        elif 'bash' in shell:
            config_file = Path.home() / ".bashrc"
        else:
            config_file = None

        if config_file:
            with open(config_file, 'a') as f:
                f.write(f'\nexport IPD_USER="{username}"\n')
            print_success(f"已写入 {config_file}")
            print_info("请运行: source ~/.zshrc 或 source ~/.bashrc")
        else:
            print_info(f"请手动设置: export IPD_USER=\"{username}\"")

def setup_glab_auth():
    """设置 glab 认证"""
    print_section("设置 glab 认证")

    if not check_command_exists("glab"):
        print_error("glab 未安装，请先安装")
        return

    print_info("开始 glab 认证...")
    print_info("将打开浏览器进行 GitLab 认证")
    success, output = run_command(["glab", "auth", "login"], check=False)
    if success:
        print_success("glab 认证成功")
    else:
        print_error(f"glab 认证失败: {output}")

def setup_mcp_config():
    """设置 MCP 配置"""
    print_section("设置 MCP 配置")

    print_info("MCP 配置需要手动完成")
    print_info("请参考 ipd-mcp-setup skill 进行配置")
    print()
    print_info("配置文件位置: ~/.claude/mcp.json")
    print_info("配置示例:")
    print("""
    {
      "mcpServers": {
        "mi-adt": {
          "command": "npx",
          "args": ["mi-adt-mcp-server"],
          "env": {
            "MI_ADT_TOKEN": "your-token-here"
          }
        }
      }
    }
    """)

def setup_osbot_repo():
    """设置 osbot 仓库"""
    print_section("设置 osbot 仓库")

    osbot_path = os.environ.get('OSBOT_PATH', '')
    if osbot_path:
        print_info(f"当前路径: {osbot_path}")
        update = input("是否更新? (y/N): ").strip().lower()
        if update != 'y':
            return

    print_info("请输入 osbot 仓库路径（留空使用默认路径）:")
    print_info("默认路径: ~/workspace/osbot")
    path = input("路径: ").strip()

    if not path:
        path = str(Path.home() / "workspace" / "osbot")

    path = Path(path).expanduser()

    if path.exists():
        print_success(f"osbot 仓库已存在: {path}")
    else:
        print_warning(f"osbot 仓库不存在: {path}")
        clone = input("是否 clone? (y/N): ").strip().lower()
        if clone == 'y':
            print_info("请输入 osbot 仓库 URL:")
            url = input("URL: ").strip()
            if url:
                success, output = run_command(["git", "clone", url, str(path)], check=False)
                if success:
                    print_success("osbot 仓库 clone 成功")
                else:
                    print_error(f"clone 失败: {output}")

    # 设置环境变量
    shell = os.environ.get('SHELL', '')
    if 'zsh' in shell:
        config_file = Path.home() / ".zshrc"
    elif 'bash' in shell:
        config_file = Path.home() / ".bashrc"
    else:
        config_file = None

    if config_file:
        with open(config_file, 'a') as f:
            f.write(f'\nexport OSBOT_PATH="{path}"\n')
        print_success(f"已写入 {config_file}")
        print_info("请运行: source ~/.zshrc 或 source ~/.bashrc")

# ==================== 主函数 ====================

def check_all(skip_env: bool = False, ci_mode: bool = False):
    """检查所有依赖"""
    print_header("依赖检查报告")

    # 1. 自包含脚本
    print_section("自包含脚本（无需安装）")
    scripts = {
        'fix-db.py': PROJECT_ROOT / 'fix-db.py',
        'wf_root.py': PROJECT_ROOT / 'wf_root.py',
        'mai-issue-query.py': PROJECT_ROOT / 'mai-issue-query.py',
        'setup.py': PROJECT_ROOT / 'setup.py',
    }
    all_ok = True
    for name, path in scripts.items():
        if path.exists():
            print_success(name)
        else:
            print_error(name)
            all_ok = False

    # 2. CLI 工具
    print_section("CLI 工具")
    tools = {
        'python3': 'python3',
        'git': 'git',
        'node': 'node',
        'pnpm': 'pnpm',
        'glab': 'glab',
    }
    for name, cmd in tools.items():
        if check_command_exists(cmd):
            print_success(name)
        else:
            print_warning(name)
            all_ok = False

    # 3. MCP 配置（CI 环境中通常不存在）
    if not ci_mode:
        print_section("MCP 配置")
        mcp_results = check_mcp_config()
        for name, configured in mcp_results.items():
            if configured:
                print_success(name)
            else:
                print_warning(name)
                all_ok = False

    # 4. 外部仓库（CI 环境中通常不存在）
    if not ci_mode:
        print_section("外部仓库")
        osbot = check_osbot_repo()
        if osbot['exists']:
            print_success(f"osbot: {osbot['path']}")
            if osbot['skills']:
                print_info(f"  项目级 skills: {', '.join(osbot['skills'].keys())}")
        else:
            print_warning("osbot: 未找到")
            all_ok = False

    # 5. 项目级 Skill（CI 环境中通常不存在）
    if not ci_mode:
        print_section("项目级 Skill")
        skills_installed = check_project_skills_installed()
        all_skills_installed = True
        for skill_name, installed in skills_installed.items():
            if installed:
                print_success(skill_name)
            else:
                print_warning(f"{skill_name} 未安装")
                all_skills_installed = False
        if not all_skills_installed:
            all_ok = False

    # 6. 全局 Skill（CI 环境中通常不存在）
    if not ci_mode:
        print_section("全局 Skill (小米 Agentic Hub)")
        global_skills_installed = check_global_skills_installed()
        all_global_installed = True
        for skill_name, installed in global_skills_installed.items():
            if installed:
                print_success(skill_name)
            else:
                guide = SKILL_INSTALL_GUIDES.get(skill_name, {})
                print_warning(f"{skill_name} 未安装")
                if guide:
                    print_info(f"  描述: {guide.get('description', '')}")
                    print_info(f"  平台: {guide.get('source', '')}")
                    print_info("  安装步骤:")
                    for step in guide.get('install_steps', []):
                        print_info(f"    {step}")
                all_global_installed = False
        if not all_global_installed:
            all_ok = False

    # 6. 环境变量（CI 环境可跳过）
    if not skip_env and not ci_mode:
        print_section("环境变量")
        env_vars = {
            'IPD_USER': 'IPD 用户名',
            'MY_AI_WORKFLOWS': '工作流根目录',
            'OSBOT_PATH': 'osbot 仓库路径',
        }
        for name, desc in env_vars.items():
            value = os.environ.get(name)
            if value:
                print_success(f"{name} = {value}")
            else:
                print_warning(f"{name} 未设置 ({desc})")

    # 总结
    print()
    if all_ok:
        print_colored("✅ 所有依赖检查通过！", Colors.GREEN)
    else:
        print_colored("⚠️  部分依赖缺失，请运行 install 或 setup 命令", Colors.YELLOW)

    return all_ok

def install_all():
    """安装所有可安装的依赖"""
    print_header("安装依赖")

    # 1. 检查并安装 CLI 工具
    print_section("CLI 工具")

    if not check_command_exists("glab"):
        print_warning("glab 未安装")
        install = input("是否安装 glab? (Y/n): ").strip().lower()
        if install != 'n':
            install_glab()
    else:
        print_success("glab 已安装")

    # 2. 检查并安装 Python 包
    print_section("Python 依赖")

    packages = {
        'zod': 'zod',
    }
    for package, import_name in packages.items():
        if check_python_package(import_name):
            print_success(package)
        else:
            print_warning(f"{package} 未安装")
            install = input(f"是否安装 {package}? (Y/n): ").strip().lower()
            if install != 'n':
                install_python_package(package)

    # 3. 检查并安装项目级 Skill
    print_section("项目级 Skill")

    skills_installed = check_project_skills_installed()
    all_installed = all(skills_installed.values())

    if all_installed:
        print_success("所有项目级 skill 已安装")
    else:
        print_warning("部分项目级 skill 未安装")
        print_info(f"需要安装的 skill: {', '.join(s for s, installed in skills_installed.items() if not installed)}")

        # 检查 osbot 仓库
        osbot = check_osbot_repo()
        if not osbot['exists']:
            print_error("osbot 仓库不存在，无法安装项目级 skill")
            print_info("请先运行: python3 scripts/manage-deps.py setup")
        else:
            install = input("是否安装项目级 skill? (Y/n): ").strip().lower()
            if install != 'n':
                osbot_path = Path(osbot['path'])
                install_project_skills(osbot_path)

def setup_all():
    """交互式配置所有依赖"""
    print_header("交互式配置向导")

    # 1. IPD_USER
    if not check_env_var('IPD_USER'):
        print_warning("IPD_USER 未设置")
        setup = input("是否设置 IPD_USER? (Y/n): ").strip().lower()
        if setup != 'n':
            setup_ipd_user()

    # 2. glab 认证
    if check_command_exists("glab"):
        success, output = run_command(["glab", "auth", "status"], check=False)
        if not success:
            print_warning("glab 未认证")
            setup = input("是否进行 glab 认证? (Y/n): ").strip().lower()
            if setup != 'n':
                setup_glab_auth()
        else:
            print_success("glab 已认证")
    else:
        print_warning("glab 未安装，跳过认证")

    # 3. MCP 配置
    mcp_results = check_mcp_config()
    if not mcp_results.get('mi-adt', False):
        print_warning("mi-adt MCP 未配置")
        setup = input("是否查看 MCP 配置指南? (Y/n): ").strip().lower()
        if setup != 'n':
            setup_mcp_config()

    # 4. osbot 仓库
    osbot = check_osbot_repo()
    if not osbot['exists']:
        print_warning("osbot 仓库未找到")
        setup = input("是否设置 osbot 仓库? (Y/n): ").strip().lower()
        if setup != 'n':
            setup_osbot_repo()
            # 重新检查
            osbot = check_osbot_repo()

    # 5. 项目级 Skill
    skills_installed = check_project_skills_installed()
    if not all(skills_installed.values()):
        print_warning("部分项目级 skill 未安装")
        if osbot['exists']:
            setup = input("是否安装项目级 skill? (Y/n): ").strip().lower()
            if setup != 'n':
                osbot_path = Path(osbot['path'])
                install_project_skills(osbot_path)
        else:
            print_error("osbot 仓库不存在，无法安装项目级 skill")

    print()
    print_success("配置完成！")
    print_info("请运行: python3 scripts/manage-deps.py check 验证配置")

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='依赖管理工具')
    parser.add_argument('action', choices=['check', 'install', 'setup'],
                        help='操作: check(检查), install(安装), setup(配置)')
    parser.add_argument('--skip-env', action='store_true',
                        help='跳过环境变量检查（CI 环境使用）')
    parser.add_argument('--ci', action='store_true',
                        help='CI 模式：跳过 MCP 配置、外部仓库、环境变量检查')

    args = parser.parse_args()

    if args.action == 'check':
        success = check_all(skip_env=args.skip_env, ci_mode=args.ci)
        sys.exit(0 if success else 1)
    elif args.action == 'install':
        install_all()
    elif args.action == 'setup':
        setup_all()

if __name__ == '__main__':
    main()
