#!/usr/bin/env python3
"""个人 AI 工作流设置脚本: 环境检查 (check) + 安装 (install) + 卸载 (uninstall)

跨平台: Linux / macOS / Windows (Python 3.9+)

用法:
  setup.py            - 环境检查 + 提示缺失项 + 询问是否安装 (默认)
  setup.py check      - 仅环境检查, 输出 ✅/⚠️/❌ 检查表并写入 .env-status.json
  setup.py install    - 仅安装符号链接 (Unix: symlink, Windows: junction, 免管理员)
  setup.py uninstall  - 删除指向本仓库的符号链接 (真实目录不受影响)

环境变量:
  MY_AI_WORKFLOWS       仓库根 (默认取脚本自身位置)
  MY_AI_WORKFLOWS_STATUS 状态文件路径 (默认 <仓库根>/.env-status.json)
  OSBOT_PATH            osbot 仓库路径 (默认探测常见位置)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKFLOW_DIR = SCRIPT_DIR / "skills"
STATUS_FILE = Path(os.environ.get("MY_AI_WORKFLOWS_STATUS", str(SCRIPT_DIR / ".env-status.json")))
STATUS_TTL_DAYS = 7
IS_WINDOWS = os.name == "nt"

WORKFLOWS = ["env-doctor", "ipd-analysis", "ipd-fix-workflow", "mr-review-workflow", "mr-pick-workflow", "osbot-test"]
PROJECT_SKILLS = ["osbot-eval", "osbot-review", "osbot-mr-preflight", "osbot-trace-viz"]

GREEN, RED, YELLOW, BLUE, NC = "\033[0;32m", "\033[0;31m", "\033[1;33m", "\033[0;34m", "\033[0m"

results: list[tuple[str, str, str, str]] = []
status = {"mi_adt_config": "missing", "glab": "missing", "osbot_path": "", "project_skills": "unknown", "workflow_links": "missing"}


def add_result(name: str, kind: str, state: str, note: str) -> None:
    results.append((name, kind, state, note))


# ---------- A. mi-adt MCP 配置检查 ----------
# 用 JSON 解析 (比 grep 可靠), jsonc/损坏文件 fallback 到文本包含检查
def _mcp_configured(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in ("mcpServers", "mcp", "mcpServersLocal"):
            if isinstance(data, dict) and "mi-adt" in (data.get(key) or {}):
                return True
        return "mi-adt" in path.read_text(encoding="utf-8", errors="ignore")
    except (json.JSONDecodeError, OSError):
        return "mi-adt" in path.read_text(encoding="utf-8", errors="ignore")


def check_mcp_config() -> None:
    home = Path.home()
    candidates = [
        home / ".claude.json",
        home / ".claude" / "mcp.json",
        home / ".config" / "opencode" / "opencode.json",
        home / ".config" / "opencode" / "opencode.jsonc",
    ]
    for path in candidates:
        if _mcp_configured(path):
            add_result("mi-adt MCP 配置", "必需", "✅", f"已配置于 {path} (连通性运行时验证)")
            status["mi_adt_config"] = "ok"
            return
    add_result(
        "mi-adt MCP 配置", "必需", "❌",
        "未找到配置; 修复: 参考 ipd-mcp-setup skill 或 https://mi.feishu.cn/wiki/WOJEw38DaicBlVknasjccb7nnDc",
    )


# ---------- B. glab CLI 检查 ----------
def check_glab() -> None:
    glab = shutil.which("glab")
    if not glab:
        add_result("glab CLI", "必需", "❌",
                   "未安装; 修复: macOS `brew install glab`, Windows `winget install GitLab.GLab`, "
                   "或 https://gitlab.com/gitlab-org/cli#installation")
        return
    try:
        proc = subprocess.run(["glab", "auth", "status"], capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            add_result("glab CLI", "必需", "✅", f"已安装且已认证 ({glab})")
            status["glab"] = "ok"
        else:
            add_result("glab CLI", "必需", "❌", "已安装但未认证; 修复: glab auth login")
            status["glab"] = "no_auth"
    except (OSError, subprocess.TimeoutExpired):
        add_result("glab CLI", "必需", "❌", "glab 执行异常; 修复: 检查安装并重试")


# ---------- C. osbot 项目路径探测 ----------
def check_osbot_path() -> None:
    found = ""
    env_path = os.environ.get("OSBOT_PATH", "")
    if env_path and Path(env_path).is_dir():
        found = env_path

    if not found:
        home = Path.home()
        if IS_WINDOWS:
            candidates = [home / "workspace" / "osbot", home / "workspace" / "osbot-new3", home / "osbot"]
        else:
            candidates = [Path("/home/peng/workspace/osbot"), Path("/home/peng/workspace/osbot-new3")]
        for p in candidates:
            if p.is_dir():
                found = str(p)
                break

    if not found:
        try:
            proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10)
            if proc.returncode == 0:
                top = proc.stdout.strip()
                remote = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, timeout=10).stdout
                if "osbot" in remote:
                    found = top
        except (OSError, subprocess.TimeoutExpired):
            pass

    if found:
        add_result("osbot 项目路径", "必需", "✅", found)
        status["osbot_path"] = found
    else:
        add_result("osbot 项目路径", "必需", "❌",
                   "未找到; 修复: 设置 OSBOT_PATH 环境变量或在 osbot 仓库内运行")


# ---------- D. 项目 skills 检查 ----------
def check_project_skills() -> None:
    if not status["osbot_path"]:
        add_result("项目 skills", "按需", "⚠️", "osbot 路径未知, 跳过")
        status["project_skills"] = "unknown"
        return
    base = Path(status["osbot_path"]) / ".agents" / "skills"
    missing = [s for s in PROJECT_SKILLS if not (base / s / "SKILL.md").is_file()]
    if not missing:
        add_result("项目 skills", "按需", "✅", "osbot-eval/osbot-review/osbot-mr-preflight/osbot-trace-viz 均存在")
        status["project_skills"] = "ok"
    else:
        add_result("项目 skills", "按需", "⚠️", f"缺失:{' '.join(missing)} (需在 osbot 仓库内运行工作流)")
        status["project_skills"] = "partial"


# ---------- E. 符号链接状态检查 ----------
def harness_dirs() -> list[tuple[str, Path]]:
    home = Path.home()
    dirs = [
        ("Claude Code", home / ".claude" / "skills"),
        ("Codex", home / ".codex" / "skills"),
        ("OpenCode", home / ".config" / "opencode" / "skills"),
    ]
    try:
        proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            root = Path(proc.stdout.strip())
            for name, sub in ((".agents", ".agents/skills"), (".claude", ".claude/skills")):
                if (root / sub).is_dir():
                    dirs.append((f"当前项目 ({name})", root / sub))
    except (OSError, subprocess.TimeoutExpired):
        pass
    return dirs


def link_ok(target: Path, source: Path) -> bool:
    try:
        return os.path.realpath(target) == os.path.realpath(source)
    except OSError:
        return False


# Windows 上 islink() 对 junction 返回 False (Python <3.12), 需用 reparse point 属性检测
FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def is_link_like(path: Path) -> bool:
    if not IS_WINDOWS:
        return os.path.islink(path)
    try:
        return bool(path.stat().st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return False


def remove_link(path: Path) -> None:
    if IS_WINDOWS and path.is_dir():
        os.rmdir(path)
    else:
        path.unlink()


def check_links() -> None:
    total = broken = 0
    for _name, skills_dir in harness_dirs():
        if not skills_dir.is_dir():
            continue
        for workflow in WORKFLOWS:
            total += 1
            if not link_ok(skills_dir / workflow, WORKFLOW_DIR / workflow):
                broken += 1
    if total == 0:
        add_result("符号链接安装", "必需", "❌", "未检测到任何 harness skills 目录; 运行 setup.py install")
        status["workflow_links"] = "missing"
    elif broken == 0:
        add_result("符号链接安装", "必需", "✅", f"{total} 个链接全部正确 (指向 {WORKFLOW_DIR})")
        status["workflow_links"] = "ok"
    else:
        add_result("符号链接安装", "必需", "⚠️", f"{broken}/{total} 个链接缺失或失效; 运行 setup.py install 修复")
        status["workflow_links"] = "partial"


# ---------- 输出与状态文件 ----------
def print_results() -> None:
    print()
    print("=" * 42)
    print("环境检查结果")
    print("=" * 42)
    print(f"{'依赖':<24} {'类型':<6} {'状态':<4} 说明")
    print("-" * 60)
    for name, kind, state, note in results:
        print(f"{name:<24} {kind:<6} {state:<4} {note}")
    print("=" * 42)


def required_ok() -> bool:
    return status["mi_adt_config"] == "ok" and status["glab"] == "ok" and bool(status["osbot_path"])


def write_status_file() -> None:
    payload = {
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ttl_days": STATUS_TTL_DAYS,
        "required_ok": required_ok(),
        "items": status,
    }
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{BLUE}状态文件已写入: {STATUS_FILE}{NC}")


def run_check() -> None:
    print()
    print("=" * 42)
    print("个人 AI 工作流 - 环境检查")
    print("=" * 42)
    check_mcp_config()
    check_glab()
    check_osbot_path()
    check_project_skills()
    check_links()
    print_results()
    if required_ok():
        print(f"{GREEN}✓ 必需依赖全部就绪{NC}")
    else:
        print(f"{RED}✗ 存在缺失的必需依赖, 请按上方修复指引处理后重新运行{NC}")
        print(f"{YELLOW}提示: 工作流运行时如遇工具调用失败, 也会提示运行 setup.py check 定位问题{NC}")
    write_status_file()


# ---------- 安装 ----------
def create_link(source: Path, target: Path) -> None:
    if IS_WINDOWS:
        proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(target), str(source)], capture_output=True, text=True)
        if proc.returncode == 0:
            return
        os.symlink(source, target, target_is_directory=True)
    else:
        os.symlink(source, target, target_is_directory=True)


def run_install() -> None:
    print()
    print("=" * 42)
    print("个人 AI 工作流安装")
    print("=" * 42)
    print()

    if not WORKFLOW_DIR.is_dir():
        print(f"{RED}错误: 工作流目录不存在: {WORKFLOW_DIR}{NC}")
        sys.exit(1)

    print(f"{BLUE}扫描 AI Harness skills 目录...{NC}")
    print()
    dirs = harness_dirs()
    if not dirs:
        print(f"{YELLOW}未找到任何 AI Harness skills 目录{NC}")
        print("请先安装 Claude Code / OpenCode / Codex, 或在项目中创建 .agents/skills 目录")
        sys.exit(1)

    for i, (name, path) in enumerate(dirs, 1):
        print(f"{GREEN}✓ 找到 {name} 目录{NC}: {path}")
    print()

    print(f"{BLUE}将要安装的工作流:{NC}")
    for workflow in WORKFLOWS:
        print(f"  • {workflow}")
    print()

    confirm = input(f"{YELLOW}是否继续安装? [Y/n]: {NC}").strip() or "Y"
    if confirm.lower() not in ("y", "yes"):
        print(f"{YELLOW}安装已取消{NC}")
        return

    installed = updated = skipped = 0
    for name, skills_dir in dirs:
        print(f"{BLUE}[{name}]{NC}")
        skills_dir.mkdir(parents=True, exist_ok=True)
        for workflow in WORKFLOWS:
            source = WORKFLOW_DIR / workflow
            target = skills_dir / workflow
            if not source.is_dir():
                print(f"  {RED}✗ {workflow}: 源目录不存在{NC}")
                continue
            if os.path.lexists(target):
                if link_ok(target, source):
                    print(f"  {GREEN}✓ {workflow}: 已安装{NC}")
                    skipped += 1
                else:
                    if is_link_like(target):
                        remove_link(target)
                    else:
                        backup = target.with_name(f"{target.name}.backup.{datetime.now():%Y%m%d_%H%M%S}")
                        target.rename(backup)
                        print(f"  {YELLOW}⚠ {workflow}: 备份现有目录到 {backup.name}{NC}")
                    create_link(source, target)
                    print(f"  {GREEN}✓ {workflow}: 已更新{NC}")
                    updated += 1
            else:
                create_link(source, target)
                print(f"  {GREEN}✓ {workflow}: 已安装{NC}")
                installed += 1
        print()

    print("=" * 42)
    print(f"{GREEN}安装完成!{NC}")
    print(f"新安装: {installed}")
    print(f"已更新: {updated}")
    print(f"已存在: {skipped}")
    print("=" * 42)
    print()
    print("使用方式:")
    print("  /ipd-fix-workflow ISS-xxx    - IPD 问题修复")
    print("  /mr-review-workflow           - MR review 流程")
    print("  /mr-pick-workflow !123 !456   - Cherry-pick 工作流")
    print("  /env-doctor                   - 运行时环境诊断 (可选)")
    print()
    print(f"{YELLOW}注意: 部分 Harness 需要重启才能识别新的 skills{NC}")


def run_uninstall() -> None:
    print()
    print("=" * 42)
    print("个人 AI 工作流卸载")
    print("=" * 42)
    print()

    dirs = [d for d in harness_dirs() if d[1].is_dir()]
    if not dirs:
        print(f"{YELLOW}未找到任何 harness skills 目录, 无需卸载{NC}")
        return

    # 收集将要删除的链接 (仅指向本仓库的, 避免误删用户目录)
    to_remove: list[tuple[str, Path, Path]] = []
    for name, skills_dir in dirs:
        for workflow in WORKFLOWS:
            target = skills_dir / workflow
            source = WORKFLOW_DIR / workflow
            if os.path.lexists(target) and link_ok(target, source):
                to_remove.append((name, target, source))

    if not to_remove:
        print(f"{GREEN}✓ 没有找到指向 {WORKFLOW_DIR} 的链接, 无需卸载{NC}")
        return

    print(f"{BLUE}将删除以下链接:{NC}")
    for name, target, source in to_remove:
        print(f"  [{name}] {target} → {source}")
    print()

    confirm = input(f"{YELLOW}确认卸载? [y/N]: {NC}").strip() or "N"
    if confirm.lower() not in ("y", "yes"):
        print(f"{YELLOW}卸载已取消{NC}")
        return

    removed = 0
    for name, target, _source in to_remove:
        if target.is_dir() and not is_link_like(target):
            print(f"  {YELLOW}⚠ [{name}] {target.name}: 是真实目录不是链接, 跳过 (如需删除请手动处理){NC}")
            continue
        remove_link(target)
        print(f"  {GREEN}✓ [{name}] 已删除: {target}{NC}")
        removed += 1

    print()
    print("=" * 42)
    print(f"{GREEN}卸载完成, 共删除 {removed} 个链接{NC}")
    print("=" * 42)
    print()
    print(f"{BLUE}提示:{NC} 卸载后工作流将不可用; 需要时运行 setup.py install 可重新安装")


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "check":
        run_check()
    elif arg == "install":
        run_install()
    elif arg == "uninstall":
        run_uninstall()
    else:
        run_check()
        print()
        print(f"{BLUE}环境检查完成。{NC}")
        print(f"{YELLOW}提示: 如需安装/更新符号链接, 运行: python {SCRIPT_DIR / 'setup.py'} install{NC}")
        print()
        confirm = input(f"{YELLOW}是否现在安装/更新符号链接? [Y/n]: {NC}").strip() or "Y"
        if confirm.lower() in ("y", "yes"):
            run_install()
        else:
            print(f"{YELLOW}跳过安装。工作流需符号链接可用才能被调用。{NC}")


if __name__ == "__main__":
    main()
