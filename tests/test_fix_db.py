"""Tests for fix-db.py — 问题修复数据库.

覆盖: parse_entry / entry_path / add_issue / update_issue / query_issue / list_issues / stats
"""
from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "fix-db.py"

def _load_module():
    spec = importlib.util.spec_from_file_location("fdb", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

fdb = _load_module()


# ===================================================================
# parse_entry
# ===================================================================

class TestParseEntry:
    """从 markdown 文本解析 front-matter 和 timeline。"""

    def test_basic_entry(self):
        text = textwrap.dedent("""\
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
              - 2026-08-15 13:00 update 补充信息
        """)
        result = fdb.parse_entry(text)
        assert result["front"]["issId"] == "ISS-TEST"
        assert result["front"]["status"] == "mr_created"
        assert result["front"]["mr"] == "!1234"
        assert len(result["timeline"]) == 2

    def test_empty_entry(self):
        result = fdb.parse_entry("")
        assert result["front"] == {}
        assert result["timeline"] == []

    def test_entry_with_note(self):
        text = "- issId: ISS-X\n- note: 缺少系统性分析\n"
        result = fdb.parse_entry(text)
        assert result["front"]["note"] == "缺少系统性分析"

    def test_timeline_not_parsed_as_front(self):
        """timeline 行不应被解析为 front-matter。"""
        text = "- issId: ISS-X\n- timeline:\n  - 2026-08-15 12:00 test\n"
        result = fdb.parse_entry(text)
        assert "timeline" not in result["front"]
        assert len(result["timeline"]) == 1


# ===================================================================
# entry_path
# ===================================================================

class TestEntryPath:
    def test_path(self):
        p = fdb.entry_path("ISS-202608-00012345A")
        assert p.name == "ISS-202608-00012345A.md"


# ===================================================================
# add_issue / query_issue
# ===================================================================

class TestAddAndQuery:
    """add_issue 创建条目, query_issue 读取。"""

    def test_add_and_query(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fdb, "DB_DIR", tmp_path)
        monkeypatch.setattr(fdb, "INDEX_FILE", tmp_path / "index.md")

        fdb.add_issue("ISS-ADD-001", title="测试添加", conclusion="", status="analyzing", typ="bugfix")

        # 文件存在
        assert (tmp_path / "ISS-ADD-001.md").is_file()

        # 解析正确
        text = (tmp_path / "ISS-ADD-001.md").read_text()
        result = fdb.parse_entry(text)
        assert result["front"]["issId"] == "ISS-ADD-001"
        assert result["front"]["status"] == "analyzing"
        assert result["front"]["type"] == "bugfix"
        assert len(result["timeline"]) == 1

    def test_add_duplicate_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fdb, "DB_DIR", tmp_path)
        monkeypatch.setattr(fdb, "INDEX_FILE", tmp_path / "index.md")

        fdb.add_issue("ISS-DUP", title="第一次", conclusion="", status="analyzing", typ="bugfix")
        with pytest.raises(SystemExit):
            fdb.add_issue("ISS-DUP", title="第二次", conclusion="", status="analyzing", typ="bugfix")


# ===================================================================
# update_issue
# ===================================================================

class TestUpdateIssue:
    def test_update_fields(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fdb, "DB_DIR", tmp_path)
        monkeypatch.setattr(fdb, "INDEX_FILE", tmp_path / "index.md")

        fdb.add_issue("ISS-UPD", title="原始", conclusion="", status="analyzing", typ="bugfix")
        fdb.update_issue("ISS-UPD", fields={"mr": "!9999", "merge_status": "merged"}, note="MR 已提交", status="mr_created")

        text = (tmp_path / "ISS-UPD.md").read_text()
        result = fdb.parse_entry(text)
        assert result["front"]["mr"] == "!9999"
        assert result["front"]["merge_status"] == "merged"
        assert result["front"]["status"] == "mr_created"
        assert len(result["timeline"]) == 2  # add + update

    def test_update_nonexistent_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fdb, "DB_DIR", tmp_path)
        with pytest.raises(SystemExit):
            fdb.update_issue("ISS-NONE", fields={}, note="", status=None)


# ===================================================================
# list_issues / stats
# ===================================================================

class TestListAndStats:
    def _setup_db(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fdb, "DB_DIR", tmp_path)
        monkeypatch.setattr(fdb, "INDEX_FILE", tmp_path / "index.md")
        fdb.add_issue("ISS-A", title="问题A", conclusion="", status="analyzing", typ="bugfix")
        fdb.add_issue("ISS-B", title="问题B", conclusion="根因X", status="mr_created", typ="bugfix")
        fdb.update_issue("ISS-B", fields={"mr": "!1111"}, note="MR 提交", status="mr_created")

    def test_list_all(self, tmp_path, monkeypatch, capsys):
        self._setup_db(tmp_path, monkeypatch)
        fdb.list_issues(days=None, status=None, mr=None, typ=None)
        out = capsys.readouterr().out
        assert "ISS-A" in out
        assert "ISS-B" in out
        assert "共 2 条" in out

    def test_list_by_status(self, tmp_path, monkeypatch, capsys):
        self._setup_db(tmp_path, monkeypatch)
        fdb.list_issues(days=None, status="mr_created", mr=None, typ=None)
        out = capsys.readouterr().out
        assert "ISS-B" in out
        assert "ISS-A" not in out

    def test_stats(self, tmp_path, monkeypatch, capsys):
        self._setup_db(tmp_path, monkeypatch)
        fdb.stats()
        out = capsys.readouterr().out
        assert "总记录: 2" in out
        assert "analyzing=1" in out
        assert "mr_created=1" in out


# ===================================================================
# wf_root.py
# ===================================================================

class TestWfRoot:
    """wf_root.py 共享定位脚本。"""

    def test_resolves_with_env(self, tmp_path, monkeypatch):
        """MY_AI_WORKFLOWS 环境变量优先。"""
        monkeypatch.setenv("MY_AI_WORKFLOWS", str(tmp_path))
        spec = importlib.util.spec_from_file_location("wfr", Path(__file__).resolve().parent.parent / "wf_root.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod._resolve_wf_root() == tmp_path

    def test_resolves_fallback(self, monkeypatch):
        """无环境变量时回落到 $HOME/my-ai-workflows。"""
        monkeypatch.delenv("MY_AI_WORKFLOWS", raising=False)
        spec = importlib.util.spec_from_file_location("wfr", Path(__file__).resolve().parent.parent / "wf_root.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        result = mod._resolve_wf_root()
        assert result.name == "my-ai-workflows"
