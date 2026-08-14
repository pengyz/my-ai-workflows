#!/usr/bin/env python3
"""问题查询脚本 (mai-issue-query) — 直接调 mi-adt MCP HTTP API, 不经过 LLM 上下文

跨平台: Linux / macOS / Windows (Python 3.9+)

用法:
  mai-issue-query.py [范围] [维度...]
  范围: 待办(默认) | 未关闭 | 全部
  维度: --priority Critical|Blocker|Major|Minor|Trivial   --module <测试模块 LIKE>
        --rd-module <研发模块 LIKE>  --status <状态>        --assignee <user>
  输出: 精简表格(issId/标题/优先级/状态/fix MR/进度), 关联 fix-db

原理: mi-adt 是 streamableHttp MCP server, 直接 JSON-RPC 调用 M_issueQuery,
      分页拉取后只提取所需字段, LLM 拿到的是精简结果而非 200KB+ 原始响应。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
import uuid
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# ---------- 配置读取 ----------
def load_mcp_config() -> dict:
    home = Path.home()
    candidates = [
        home / ".claude.json",
        home / ".config" / "opencode" / "opencode.json",
        home / ".config" / "opencode" / "opencode.jsonc",
    ]
    for p in candidates:
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for key in ("mcpServers", "mcp"):
            ms = d.get(key) or {}
            if "mi-adt" in ms:
                return ms["mi-adt"]
    sys.exit("✗ 未找到 mi-adt MCP 配置 (检查 ~/.claude.json 或 opencode 配置)")


# ---------- 最小 MCP streamableHttp client ----------
class McpClient:
    def __init__(self, url: str, headers: dict):
        self.url = url
        self.headers = {k: v for k, v in headers.items() if v}
        self.session_id = ""

    def _post(self, payload: dict) -> dict:
        headers = {**self.headers, "Content-Type": "application/json"}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode(), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            sid = resp.headers.get("Mcp-Session-Id")
            if sid:
                self.session_id = sid
            body = resp.read().decode("utf-8", errors="replace")
        if "text/event-stream" in resp.headers.get("Content-Type", ""):
            last = None
            for line in body.splitlines():
                if line.startswith("data:"):
                    try:
                        last = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        pass
            return last or {}
        if not body.strip():
            return {}
        return json.loads(body)

    def initialize(self) -> None:
        self._post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "mai-issue-query", "version": "1.0"}}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call_tool(self, name: str, args: dict) -> dict:
        resp = self._post({"jsonrpc": "2.0", "id": str(uuid.uuid4()),
                           "method": "tools/call", "params": {"name": name, "arguments": args}})
        return resp.get("result", {})


def extract_issues(result: dict) -> list:
    sc = result.get("structuredContent")
    if isinstance(sc, dict) and "data" in sc:
        return sc["data"]
    for item in result.get("content", []):
        text = item.get("text", "")
        if "data" in text:
            dec = json.JSONDecoder()
            try:
                data, _ = dec.raw_decode(text[text.index("{"):])
                if isinstance(data, dict) and "data" in data:
                    return data["data"]
            except (json.JSONDecodeError, ValueError):
                continue
    return []


# ---------- 查询 ----------
# IPD 状态中英文混合, 终止状态必须全部排除 (否则已关闭/已解决混入, 返回量爆炸)
CLOSED_STATES = ["Closed", "Verified", "Resolved", "已终止", "Termination", "已解决", "已关闭", "已失效"]


def build_filters(scope: str, user: str, args) -> list:
    filters = []
    if scope == "待办":
        filters.append({"key": "issueAssigneeId", "operator": "EQ", "value": [user]})
        filters.append({"key": "issueStatus", "operator": "NOT_IN", "value": CLOSED_STATES})
    elif scope == "未关闭":
        filters.append({"key": "issueStatus", "operator": "NOT_IN", "value": CLOSED_STATES})
    filters.append({"key": "deleted", "operator": "EQ", "value": ["0"]})
    if args.priority:
        filters.append({"key": "issuePriority", "operator": "EQ", "value": [args.priority]})
    if args.module:
        filters.append({"key": "issueTestComponent", "operator": "LIKE", "value": [args.module]})
    if args.rd_module:
        filters.append({"key": "exHandleAction", "operator": "LIKE", "value": [args.rd_module]})
    if args.status:
        filters.append({"key": "issueStatus", "operator": "EQ", "value": [args.status]})
    if args.assignee:
        filters.append({"key": "issueAssigneeId", "operator": "EQ", "value": [args.assignee]})
    return filters


def fetch_all(client: McpClient, filters: list, page_size: int = 100, max_pages: int = 5) -> tuple[list, bool]:
    issues, page, truncated = [], 1, False
    while page <= max_pages:
        result = client.call_tool("M_issueQuery", {
            "filters": filters,
            "pageInfo": {"pageNum": page, "pageSize": page_size},
            "sorts": [{"key": "issuePriority", "value": "asc"}],
        })
        batch = extract_issues(result)
        if not batch:
            break
        issues.extend(batch)
        if len(batch) < page_size:
            break
        page += 1
    else:
        truncated = True
    return issues, truncated


# ---------- fix-db 关联 ----------
def fixdb_status(iss_id: str) -> dict:
    try:
        r = subprocess.run([sys.executable, str(SCRIPT_DIR / "fix-db.py"), "query", iss_id],
                           capture_output=True, text=True, timeout=10)
        if "issId:" not in r.stdout:
            return {"found": False}
        front = {}
        for line in r.stdout.splitlines():
            m = re.match(r"^- (\w+): (.*)$", line.strip())
            if m:
                front[m.group(1)] = m.group(2)
        return {"found": True, **front}
    except (OSError, subprocess.TimeoutExpired):
        return {"found": False}


MR_BASE = os.environ.get(
    "MAI_MR_BASE_URL",
    "https://git.n.xiaomi.com/ai-framework/osbot/-/merge_requests/",
)


def default_user() -> str:
    env = os.environ.get("IPD_USER")
    if env:
        return env
    try:
        cfg = load_mcp_config()
        h = cfg.get("headers") or {}
        if h.get("x-authenticated-user"):
            return h["x-authenticated-user"]
    except SystemExit:
        pass
    sys.exit("✗ 无法确定 IPD 用户名: 请设置 IPD_USER 环境变量")


def format_mr(change_id: str, backport: str = "") -> str:
    links = [f"[!{m}]({MR_BASE}{m})" for m in re.findall(r"merge_requests/(\d+)", change_id or "")]
    if backport:
        links += [f"[!{m}]({MR_BASE}{m})" for m in re.findall(r"!(\d+)", backport)]
    return ", ".join(links) or "-"


# ---------- 输出 ----------
def print_table(issues: list, scope: str, as_json: bool) -> None:
    if as_json:
        out = [{"issId": i.get("issId"), "title": i.get("issueTitle"), "priority": i.get("issuePriority"),
                "status": i.get("issueStatus"), "component": i.get("issueTestComponent"),
                "mr": re.findall(r"merge_requests/(\d+)", i.get("changeId") or "")} for i in issues]
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    prio = {"Blocker": 0, "Critical": 1, "Major": 2, "Minor": 3, "Trivial": 4}
    issues.sort(key=lambda x: prio.get(x.get("issuePriority"), 9))
    print(f"## 问题编排 ({scope} 共 {len(issues)} 条)")
    print()
    print("| issId | 优先级 | 状态 | fix MR | 标题 |")
    print("|---|---|---|---|---|")
    for it in issues:
        db = fixdb_status(it.get("issId", ""))
        mr = format_mr(it.get("changeId", ""), db.get("backport_mr") if db.get("found") else "")
        print(f"| {it.get('issId')} | {it.get('issuePriority')} | {it.get('issueStatus')} | {mr} | {(it.get('issueTitle') or '')[:44]} |")


def main() -> None:
    parser = argparse.ArgumentParser(prog="mai-issue-query", description="问题查询(直接调 mi-adt API)")
    parser.add_argument("scope", nargs="?", default="待办", choices=["待办", "未关闭", "全部"])
    parser.add_argument("--priority", choices=["Blocker", "Critical", "Major", "Minor", "Trivial"])
    parser.add_argument("--module")
    parser.add_argument("--rd-module")
    parser.add_argument("--status")
    parser.add_argument("--assignee")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    cfg = load_mcp_config()
    user = args.assignee or default_user()
    client = McpClient(cfg["url"], cfg.get("headers", {}))
    client.initialize()

    filters = build_filters(args.scope, user, args)
    if args.scope in ("未关闭", "全部"):
        print(f"(提示) {args.scope} 范围不限定 assignee, 结果可能很大, 已设分页上限 500 条", file=sys.stderr)
    issues, truncated = fetch_all(client, filters)
    if not issues:
        print(f"(空) {args.scope} 范围无匹配问题")
        return
    print_table(issues, args.scope, args.json)
    if truncated:
        print(f"(截断) 结果超过 500 条上限, 请用 --priority/--module/--status 缩小范围", file=sys.stderr)


if __name__ == "__main__":
    main()
