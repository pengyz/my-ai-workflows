"""Tests for mai-issue-query.py — 问题查询脚本.

覆盖: extract_issues / build_filters / fixdb_status / format_mr / print_table (JSON)
"""
from __future__ import annotations

import importlib.util
import json
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

# ---------- 动态导入 (脚本文件名含连字符, 不能直接 import) ----------
_SCRIPT = Path(__file__).resolve().parent.parent / "mai-issue-query.py"

def _load_module():
    spec = importlib.util.spec_from_file_location("miq", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

miq = _load_module()


# ===================================================================
# extract_issues
# ===================================================================

class TestExtractIssues:
    """从 MCP 响应中提取 issue 列表。"""

    def test_structured_content(self):
        result = {"structuredContent": {"data": [{"issId": "A"}, {"issId": "B"}]}}
        assert miq.extract_issues(result) == [{"issId": "A"}, {"issId": "B"}]

    def test_content_text_json(self):
        result = {"content": [{"type": "text", "text": '{"data": [{"issId": "X"}]}'}]}
        assert miq.extract_issues(result) == [{"issId": "X"}]

    def test_content_text_with_prefix(self):
        """text 前面有非 JSON 前缀时, 从第一个 { 开始解析。"""
        result = {"content": [{"type": "text", "text": 'some prefix {"data": [{"issId": "Y"}]}'}]}
        assert miq.extract_issues(result) == [{"issId": "Y"}]

    def test_empty_content(self):
        assert miq.extract_issues({}) == []
        assert miq.extract_issues({"content": []}) == []

    def test_malformed_json(self):
        result = {"content": [{"type": "text", "text": "not json at all"}]}
        assert miq.extract_issues(result) == []

    def test_no_data_key(self):
        result = {"content": [{"type": "text", "text": '{"total": 0}'}]}
        assert miq.extract_issues(result) == []


# ===================================================================
# build_filters
# ===================================================================

class TestBuildFilters:
    """按范围/维度构建 IPD 查询 filters。"""

    def _args(self, **kwargs):
        defaults = {"priority": None, "module": None, "rd_module": None, "status": None, "assignee": None}
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_todo_scope(self):
        filters = miq.build_filters("待办", "alice", self._args())
        keys = [f["key"] for f in filters]
        assert "issueAssigneeId" in keys
        assert "issueStatus" in keys
        # NOT_IN 闭合状态
        status_f = next(f for f in filters if f["key"] == "issueStatus")
        assert status_f["operator"] == "NOT_IN"
        assert "Closed" in status_f["value"]

    def test_all_scope_no_assignee(self):
        filters = miq.build_filters("全部", "alice", self._args())
        keys = [f["key"] for f in filters]
        assert "issueAssigneeId" not in keys
        assert "deleted" in keys

    def test_with_priority(self):
        filters = miq.build_filters("待办", "alice", self._args(priority="Critical"))
        pf = next(f for f in filters if f["key"] == "issuePriority")
        assert pf["value"] == ["Critical"]

    def test_with_module(self):
        filters = miq.build_filters("待办", "alice", self._args(module="互联互通"))
        mf = next(f for f in filters if f["key"] == "issueTestComponent")
        assert mf["operator"] == "LIKE"

    def test_with_assignee_override(self):
        filters = miq.build_filters("待办", "alice", self._args(assignee="bob"))
        af = next(f for f in filters if f["key"] == "issueAssigneeId")
        assert af["value"] == ["bob"]


# ===================================================================
# fixdb_status
# ===================================================================

class TestFixdbStatus:
    """读取 fix-db 条目 front-matter。"""

    def test_existing_entry(self, tmp_path):
        entry = tmp_path / "ISS-TEST.md"
        entry.write_text(textwrap.dedent("""\
            # ISS-TEST 问题修复记录

            - issId: ISS-TEST
            - type: bugfix
            - title: 测试标题
            - status: mr_created
            - conclusion: 根因xxx
            - mr: !1234
            - merge_status: merged
            - updated_at: 2026-08-15T12:00:00+0800

            - timeline:
              - 2026-08-15 12:00 mr_created 创建记录
        """))
        # monkey-patch FIX_DB_DIR
        orig = miq.FIX_DB_DIR
        miq.FIX_DB_DIR = tmp_path
        try:
            result = miq.fixdb_status("ISS-TEST")
            assert result["found"] is True
            assert result["issId"] == "ISS-TEST"
            assert result["status"] == "mr_created"
            assert result["mr"] == "!1234"
            assert len(result["timeline"]) == 1
        finally:
            miq.FIX_DB_DIR = orig

    def test_missing_entry(self, tmp_path):
        orig = miq.FIX_DB_DIR
        miq.FIX_DB_DIR = tmp_path
        try:
            result = miq.fixdb_status("ISS-NONEXIST")
            assert result["found"] is False
        finally:
            miq.FIX_DB_DIR = orig


# ===================================================================
# format_mr
# ===================================================================

class TestFormatMR:
    """格式化 MR 链接 (changeId + backport + fixdb_mr 去重)。"""

    def test_empty(self):
        assert miq.format_mr("") == "-"

    def test_change_id_url(self):
        result = miq.format_mr("https://git.n.xiaomi.com/ai-framework/osbot/-/merge_requests/5299")
        assert "!5299" in result
        assert "5299" in result

    def test_multiple_change_ids(self):
        change_id = "https://example.com/merge_requests/111,https://example.com/merge_requests/222"
        result = miq.format_mr(change_id)
        assert "!111" in result
        assert "!222" in result

    def test_backport(self):
        result = miq.format_mr("", backport="!999")
        assert "!999" in result

    def test_fixdb_mr(self):
        result = miq.format_mr("", fixdb_mr="!888, !777")
        assert "!888" in result
        assert "!777" in result

    def test_dedup(self):
        """changeId 和 fixdb_mr 引用同一个 MR 时只显示一次。"""
        change_id = "https://example.com/merge_requests/123"
        result = miq.format_mr(change_id, fixdb_mr="!123")
        assert result.count("[!123]") == 1


# ===================================================================
# print_table (JSON mode)
# ===================================================================

class TestPrintTable:
    """--json 输出格式。"""

    def test_json_output(self, tmp_path, capsys):
        # 构造最小 issues 列表
        issues = [{
            "issId": "ISS-TEST-001",
            "id": 12345,
            "issueTitle": "测试标题",
            "issuePriority": "Critical",
            "issueStatus": "Open",
            "issueTestComponent": "测试模块",
            "changeId": "https://example.com/merge_requests/999",
        }]
        # monkey-patch FIX_DB_DIR
        orig = miq.FIX_DB_DIR
        miq.FIX_DB_DIR = tmp_path
        try:
            miq.print_table(issues, "待办", as_json=True)
        finally:
            miq.FIX_DB_DIR = orig
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) == 1
        assert data[0]["issId"] == "ISS-TEST-001"
        assert data[0]["issueId"] == 12345
        assert data[0]["priority"] == "Critical"
        assert "999" in data[0]["mr"][0]

    def test_json_empty(self, capsys):
        miq.print_table([], "待办", as_json=True)
        captured = capsys.readouterr()
        assert json.loads(captured.out) == []
