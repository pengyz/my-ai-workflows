#!/usr/bin/env python3
"""问题修复数据库 (fix-db)

跨平台: Linux / macOS / Windows (Python 3.9+)
对接当前 issue 系统 (IPD) 的单号 issId, 记录 分析结论/修复 MR/回流 MR/合入状态。

用法:
  fix-db.py add <issId> --title "<标题>" [--conclusion "<根因>"] [--status <状态>]
  fix-db.py update <issId> [-f key=value ...] [-t "<时间线说明>"] [--status <状态>]
  fix-db.py query <issId>
  fix-db.py list [--days N] [--status <状态>]
  fix-db.py stats

状态机: analyzing → conclusion_uploaded → fixing → mr_created → merged → closed

并发设计:
  每个问题一个条目文件 (fix-db/<issId>.md), 并行 session 写不同文件零冲突;
  index.md 是派生产物, 写条目后 flock 加锁重建, list/query 实时扫描条目不依赖索引。

环境变量:
  MY_AI_WORKFLOWS      仓库根 (默认取脚本自身位置)
  FIX_DB_DIR           数据目录覆盖 (默认 <仓库根>/fix-db)
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DB_DIR = Path(os.environ.get("FIX_DB_DIR", str(SCRIPT_DIR / "fix-db")))
INDEX_FILE = DB_DIR / "index.md"

STATUSES = ["analyzing", "conclusion_uploaded", "fixing", "implementing", "mr_created", "merged", "closed"]
TYPES = ["bugfix", "feature"]
FIELD_KEYS = {"title", "conclusion", "mr", "merge_status", "backport_mr", "type"}
TIME_FMT = "%Y-%m-%dT%H:%M:%S%z"


# ---------- 跨平台文件锁 ----------
def _lock_file(f) -> None:
    if os.name == "nt":
        import msvcrt
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_EX)


def _unlock_file(f) -> None:
    if os.name == "nt":
        import msvcrt
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_UN)


def _locked(target: Path, fn):
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a+", encoding="utf-8") as f:
        _lock_file(f)
        try:
            return fn()
        finally:
            _unlock_file(f)


# ---------- 条目读写 ----------
FRONT_RE = re.compile(r"^- ([A-Za-z_][\w]*): (.*)$")
TIMELINE_RE = re.compile(r"^\s*- \d{4}-\d{2}-\d{2} ")


def parse_entry(text: str) -> dict:
    front, timeline = {}, []
    for line in text.splitlines():
        m = FRONT_RE.match(line)
        if m and not TIMELINE_RE.match(line):
            front[m.group(1)] = m.group(2)
        elif TIMELINE_RE.match(line):
            timeline.append(re.sub(r"^\s*- ", "", line).strip())
    return {"front": front, "timeline": timeline}


def entry_path(iss_id: str) -> Path:
    return DB_DIR / f"{iss_id}.md"


def now_str() -> str:
    return datetime.datetime.now().astimezone().strftime(TIME_FMT)


def now_short() -> str:
    return datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")


def add_issue(iss_id: str, title: str, conclusion: str, status: str, typ: str) -> None:
    path = entry_path(iss_id)
    if path.exists():
        print(f"✗ {iss_id} 已存在 (query 查看详情, update 修改)")
        sys.exit(1)
    ts = now_str()
    lines = [
        f"# {iss_id} 问题修复记录", "",
        f"- issId: {iss_id}",
        f"- type: {typ}",
        f"- title: {title}",
        f"- status: {status}",
        f"- conclusion: {conclusion}",
        "- mr:",
        "- backport_mr:",
        "- merge_status: pending",
        f"- updated_at: {ts}", "",
        "- timeline:",
        f"  - {now_short()} {status} 创建记录",
    ]
    _locked(path, lambda: path.write_text("\n".join(lines) + "\n", encoding="utf-8"))
    print(f"✓ 已创建 {iss_id} (type={typ}, status={status})")
    _rebuild_index()


def update_issue(iss_id: str, fields: dict, note: str, status: str) -> None:
    path = entry_path(iss_id)
    if not path.exists():
        print(f"✗ {iss_id} 不存在 (先 add)")
        sys.exit(1)

    def _do() -> None:
        data = parse_entry(path.read_text(encoding="utf-8"))
        front, timeline = data["front"], data["timeline"]
        for k, v in fields.items():
            if k not in FIELD_KEYS:
                print(f"✗ 未知字段 {k} (允许: {sorted(FIELD_KEYS)})")
                sys.exit(1)
            front[k] = v
        if status:
            if status not in STATUSES:
                print(f"✗ 非法状态 {status} (允许: {STATUSES})")
                sys.exit(1)
            front["status"] = status
        front["updated_at"] = now_str()
        action = status or note or "update"
        timeline.append(f"{now_short()} {action} {note or ''}".rstrip())
        out = [f"# {iss_id} 问题修复记录", ""]
        for k in ["issId", "type", "title", "status", "conclusion", "mr", "backport_mr", "merge_status", "updated_at"]:
            out.append(f"- {k}: {front.get(k, '')}")
        out += ["", "- timeline:"]
        out += [f"  - {t}" for t in timeline]
        path.write_text("\n".join(out) + "\n", encoding="utf-8")

    _locked(path, _do)
    print(f"✓ 已更新 {iss_id}" + (f" (status={status})" if status else ""))
    _rebuild_index()


def query_issue(iss_id: str) -> None:
    path = entry_path(iss_id)
    if not path.exists():
        print(f"✗ {iss_id} 无记录 (尚未 add)")
        sys.exit(1)
    print(path.read_text(encoding="utf-8").rstrip())


def iter_entries():
    if not DB_DIR.is_dir():
        return
    for p in sorted(DB_DIR.glob("ISS-*.md")):
        data = parse_entry(p.read_text(encoding="utf-8"))
        yield p.stem, data


def list_issues(days: int | None, status: str | None, mr: str | None, typ: str | None) -> None:
    now = datetime.datetime.now().astimezone()
    rows = []
    for iss_id, data in iter_entries():
        f = data["front"]
        if status and f.get("status") != status:
            continue
        if typ and f.get("type") != typ:
            continue
        if mr and mr not in (f.get("mr") or "") and mr not in (f.get("backport_mr") or ""):
            continue
        try:
            updated = datetime.datetime.strptime(f.get("updated_at", ""), TIME_FMT)
        except ValueError:
            updated = now
        if days is not None and (now - updated).days > days:
            continue
        rows.append((updated, iss_id, f))
    rows.sort(reverse=True)
    print(f"{'issId':<26} {'类型':<8} {'状态':<20} {'MR':<8} {'回流':<8} {'合入':<8} 标题")
    print("-" * 120)
    for _ts, iss_id, f in rows:
        print(f"{iss_id:<26} {f.get('type',''):<8} {f.get('status',''):<20} {f.get('mr','') or '-':<8} "
              f"{f.get('backport_mr','') or '-':<8} {f.get('merge_status','pending'):<8} {f.get('title','')}")
    print(f"\n共 {len(rows)} 条")


def stats() -> None:
    counts = {s: 0 for s in STATUSES}
    type_counts = {t: 0 for t in TYPES}
    total = merged = 0
    for _iss_id, data in iter_entries():
        f = data["front"]
        total += 1
        st = f.get("status", "")
        counts[st] = counts.get(st, 0) + 1
        type_counts[f.get("type", "bugfix")] = type_counts.get(f.get("type", "bugfix"), 0) + 1
        if f.get("merge_status") == "merged" or st == "merged":
            merged += 1
    print(f"总记录: {total} (bugfix={type_counts.get('bugfix',0)}, feature={type_counts.get('feature',0)})")
    for s in STATUSES:
        if counts[s]:
            print(f"  {s:<20} {counts[s]}")
    print(f"MR 合入率: {merged}/{total} ({100 * merged // total if total else 0}%)")


def _rebuild_index() -> None:
    def _do() -> None:
        lines = ["# IPD 修复数据库索引", "", f"生成时间: {now_short()}", "",
                 "| issId | 标题 | 状态 | 修复 MR | 合入 | 更新时间 |",
                 "|---|---|---|---|---|---|"]
        counts = {s: 0 for s in STATUSES}
        for iss_id, data in iter_entries():
            f = data["front"]
            counts[f.get("status", "")] = counts.get(f.get("status", ""), 0) + 1
            lines.append(f"| {iss_id} | {f.get('title','')} | {f.get('status','')} | "
                         f"{f.get('mr','') or '-'} | {f.get('merge_status','pending')} | {f.get('updated_at','')} |")
        lines.append("")
        summary = " | ".join(f"{s}={counts.get(s,0)}" for s in STATUSES if counts.get(s))
        lines.append(f"统计: 共 {sum(counts.values())} 条 | {summary}")
        INDEX_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    _locked(INDEX_FILE, _do)


def main() -> None:
    parser = argparse.ArgumentParser(prog="fix-db", description="IPD 问题修复数据库")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="创建条目")
    p_add.add_argument("issId")
    p_add.add_argument("--title", required=True)
    p_add.add_argument("--conclusion", default="")
    p_add.add_argument("--type", default="bugfix", choices=TYPES, help="bugfix 默认从 analyzing 开始; feature 从 implementing 开始")
    p_add.add_argument("--status", choices=STATUSES)

    p_upd = sub.add_parser("update", help="更新字段+追加时间线")
    p_upd.add_argument("issId")
    p_upd.add_argument("-f", action="append", default=[], metavar="key=value", help="字段: title/conclusion/mr/backport_mr/merge_status/type")
    p_upd.add_argument("-t", default="", help="时间线说明")
    p_upd.add_argument("--status", choices=STATUSES)

    p_q = sub.add_parser("query", help="查单条")
    p_q.add_argument("issId")

    p_list = sub.add_parser("list", help="列出")
    p_list.add_argument("--days", type=int)
    p_list.add_argument("--status", choices=STATUSES)
    p_list.add_argument("--type", choices=TYPES)
    p_list.add_argument("--mr", help="按 MR 编号过滤 (匹配 mr 或 backport_mr)")

    sub.add_parser("stats", help="统计")

    args = parser.parse_args()
    if args.cmd == "add":
        status = args.status or ("implementing" if args.type == "feature" else "analyzing")
        add_issue(args.issId, args.title, args.conclusion, status, args.type)
    elif args.cmd == "update":
        fields = {}
        for kv in args.f:
            if "=" not in kv:
                print(f"✗ 参数需 key=value: {kv}")
                sys.exit(1)
            k, v = kv.split("=", 1)
            if k == "type" and v not in TYPES:
                print(f"✗ 非法 type {v} (允许: {TYPES})")
                sys.exit(1)
            fields[k] = v
        update_issue(args.issId, fields, args.t, args.status)
    elif args.cmd == "query":
        query_issue(args.issId)
    elif args.cmd == "list":
        list_issues(args.days, args.status, args.mr, args.type)
    elif args.cmd == "stats":
        stats()


if __name__ == "__main__":
    main()
