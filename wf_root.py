#!/usr/bin/env python3
"""定位 my-ai-workflows 仓库根 (WF_ROOT) 并输出状态文件。

供各 skill Step 0 环境门禁统一调用, 消除 SKILL.md 中重复的 bash/PowerShell 检测逻辑。

用法:
  python3 wf_root.py              # 输出 WF_ROOT 路径
  python3 wf_root.py --status     # 输出 .env-status.json 内容 (不存在则输出 MISSING)
  python3 wf_root.py --check      # 输出 WF_ROOT + 状态判定 (供 LLM 直接判断)

定位优先级: MY_AI_WORKFLOWS 环境变量 > 符号链接反查 > $HOME/my-ai-workflows 兜底
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _resolve_wf_root() -> Path:
    """按优先级定位 my-ai-workflows 仓库根。"""
    # 1. 环境变量
    env = os.environ.get("MY_AI_WORKFLOWS")
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p

    # 2. 符号链接反查: 扫描已知 harness skills 目录
    home = Path.home()
    skill_dirs = [
        home / ".config" / "opencode" / "skills",
        home / ".claude" / "skills",
        home / ".codex" / "skills",
        Path.cwd() / ".agents" / "skills",
        Path.cwd() / ".claude" / "skills",
    ]
    # 查找任意 mai-* 符号链接, 反推仓库根
    for sd in skill_dirs:
        if not sd.is_dir():
            continue
        for child in sd.iterdir():
            if not child.name.startswith("mai-"):
                continue
            try:
                resolved = child.resolve()
            except OSError:
                continue
            if (resolved / "SKILL.md").is_file():
                # resolved = <WF_ROOT>/skills/mai-xxx → parent.parent = WF_ROOT
                candidate = resolved.parent.parent
                if (candidate / "setup.py").is_file():
                    return candidate

    # 3. 兜底
    return home / "my-ai-workflows"


def _read_status(wf_root: Path) -> dict | None:
    """读取 .env-status.json, 不存在或解析失败返回 None。"""
    status_file = wf_root / ".env-status.json"
    if not status_file.is_file():
        return None
    try:
        return json.loads(status_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def main() -> None:
    args = sys.argv[1:]
    wf_root = _resolve_wf_root()

    if "--status" in args:
        status = _read_status(wf_root)
        if status is None:
            print("MISSING")
        else:
            print(json.dumps(status, ensure_ascii=False, indent=2))
        return

    if "--check" in args:
        print(f"WF_ROOT={wf_root}")
        status = _read_status(wf_root)
        if status is None:
            print("STATUS=MISSING")
            print("ACTION=请先运行 setup.py check 完成一次性环境配置")
        elif not status.get("required_ok", False):
            print("STATUS=INCOMPLETE")
            print("ACTION=存在必需项缺失, 请运行 setup.py check 查看详情")
        else:
            print("STATUS=OK")
        return

    # 默认: 仅输出路径
    print(wf_root)


if __name__ == "__main__":
    main()
