#!/usr/bin/env python3
"""
Skill 静态验证脚本

验证项目：
1. 结构完整性：必需章节存在、步骤编号连续、引用有效性
2. 格式一致性：Markdown 格式、路径占位符统一
3. 依赖完整性：引用的工具/文件存在

使用方法：
    python3 scripts/verify-skills.py [--verbose] [--fix]
"""

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# 配置
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
SKILLS_DIR = PROJECT_ROOT / "skills"

# 必需章节（按优先级排序）
# 支持多种章节名称变体
REQUIRED_SECTIONS = {
    'trigger': ['触发', '触发方式', 'trigger', '调用时机', '使用方式'],
    'prerequisite': ['前置', 'prerequisite', '依赖检查', '环境要求', '环境门禁'],
    'steps': ['Step', '步骤', '工作流程', '工作流', '执行流程', '流程', '阶段'],
    'output': ['输出', 'output', '结果', '报告', '完成报告', '统计', '结论'],
    'error': ['错误处理', 'error', '异常', '失败', '问题'],
    'dependencies': ['依赖', 'dependencies', '工具', '环境'],
}

# 可选章节（有更好，没有也可以）
OPTIONAL_SECTIONS = {
    'prerequisite': True,  # 前置章节是可选的，有些 skill 可能在触发方式中说明
    'error': True,  # 错误处理是可选的
}

# 有效路径占位符
VALID_PLACEHOLDERS = {
    '<WF_ROOT>', '<OSBOT_PATH>', '<ISS_ID>', '<issId>',
    '<MR编号>', '<hash>', '<repo-path>', '<log-dir>',
}

# 已知工具依赖
KNOWN_TOOLS = {
    'mi-adt', 'fix-db.py', 'wf_root.py', 'glab',
    'mai-osbot-test', 'mai-env-doctor', 'mai-analysis',
    'mai-fix-workflow', 'mai-implement-workflow',
    'mai-mr-review-workflow', 'mai-mr-pick-workflow',
    'mai-issue-schedule', 'mai-issue-query.py',
}


class SkillIssue:
    """Skill 问题记录"""
    def __init__(self, skill_name: str, level: str, category: str, message: str, line: Optional[int] = None):
        self.skill_name = skill_name
        self.level = level  # error, warning, info
        self.category = category  # structure, format, dependency
        self.message = message
        self.line = line

    def __str__(self):
        line_info = f":{self.line}" if self.line else ""
        return f"[{self.level.upper()}] {self.skill_name}{line_info} ({self.category}): {self.message}"


def verify_skill_structure(skill_path: Path, skill_name: str) -> List[SkillIssue]:
    """验证 skill 结构完整性"""
    issues = []
    
    try:
        content = skill_path.read_text(encoding='utf-8')
    except Exception as e:
        issues.append(SkillIssue(skill_name, 'error', 'structure', f'无法读取文件: {e}'))
        return issues
    
    lines = content.split('\n')
    
    # 1. 检查必需章节
    found_sections = set()
    for line_num, line in enumerate(lines, 1):
        if line.startswith('## ') or line.startswith('### '):
            section_title = line.lstrip('#').strip()
            # 移除 emoji 前缀（如 🎯、📋、🔍 等）
            section_title_clean = re.sub(r'^[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF]+\s*', '', section_title)
            for section_key, keywords in REQUIRED_SECTIONS.items():
                if any(keyword in section_title_clean or keyword in section_title for keyword in keywords):
                    found_sections.add(section_key)
    
    for section_key, keywords in REQUIRED_SECTIONS.items():
        if section_key not in found_sections:
            # 检查是否是可选章节
            if section_key in OPTIONAL_SECTIONS:
                issues.append(SkillIssue(
                    skill_name, 'info', 'structure',
                    f'缺少可选章节: {keywords[0]} (建议添加包含 {"/".join(keywords[:2])} 的章节)'
                ))
            else:
                issues.append(SkillIssue(
                    skill_name, 'warning', 'structure',
                    f'缺少必需章节: {keywords[0]} (建议添加包含 {"/".join(keywords[:2])} 的章节)'
                ))
    
    # 2. 检查步骤编号连续性
    step_numbers = []
    for line_num, line in enumerate(lines, 1):
        match = re.match(r'^#{2,4}\s+(?:Step\s+)?(\d+)', line)
        if match:
            step_num = int(match.group(1))
            step_numbers.append((step_num, line_num))
    
    for i in range(len(step_numbers) - 1):
        current_num, current_line = step_numbers[i]
        next_num, next_line = step_numbers[i + 1]
        if next_num - current_num > 1:
            issues.append(SkillIssue(
                skill_name, 'warning', 'structure',
                f'步骤编号跳过: Step {current_num} → Step {next_num} (缺少 Step {current_num + 1})',
                current_line
            ))
    
    # 3. 检查路径占位符
    for line_num, line in enumerate(lines, 1):
        placeholders = re.findall(r'<[^>]+>', line)
        for placeholder in placeholders:
            if placeholder.startswith('<WF_ROOT>') or placeholder.startswith('<'):
                if placeholder not in VALID_PLACEHOLDERS and not placeholder.startswith('<http'):
                    # 检查是否是已知的占位符格式
                    if re.match(r'^<[A-Z_]+>$', placeholder):
                        issues.append(SkillIssue(
                            skill_name, 'info', 'format',
                            f'未知路径占位符: {placeholder} (可能需要添加到 VALID_PLACEHOLDERS)',
                            line_num
                        ))
    
    return issues


def verify_skill_format(skill_path: Path, skill_name: str) -> List[SkillIssue]:
    """验证 skill 格式一致性"""
    issues = []
    
    try:
        content = skill_path.read_text(encoding='utf-8')
    except Exception as e:
        return issues
    
    lines = content.split('\n')
    
    # 1. 检查 Markdown 格式
    for line_num, line in enumerate(lines, 1):
        # 检查标题格式
        if line.startswith('#') and not line.startswith('## ') and not line.startswith('### ') and not line.startswith('#### '):
            if line.startswith('# ') and len(line) > 2:
                continue  # H1 标题
            issues.append(SkillIssue(
                skill_name, 'warning', 'format',
                f'标题格式不规范: {line[:50]}...',
                line_num
            ))
        
        # 检查代码块语言标记
        if line.startswith('```') and len(line) > 3:
            lang = line[3:].strip()
            if lang and lang not in ['python', 'bash', 'json', 'yaml', 'markdown', 'text', 'typescript', 'javascript']:
                issues.append(SkillIssue(
                    skill_name, 'info', 'format',
                    f'代码块语言标记: {lang} (建议使用标准标记)',
                    line_num
                ))
    
    # 2. 检查路径占位符一致性
    placeholders_in_file = set()
    for line_num, line in enumerate(lines, 1):
        placeholders = re.findall(r'<[A-Z_]+>', line)
        placeholders_in_file.update(placeholders)
    
    # 检查是否使用了非标准占位符
    for placeholder in placeholders_in_file:
        if placeholder not in VALID_PLACEHOLDERS:
            issues.append(SkillIssue(
                skill_name, 'info', 'format',
                f'使用了非标准占位符: {placeholder} (建议使用 <WF_ROOT> 等标准占位符)'
            ))
    
    return issues


def verify_skill_dependencies(skill_path: Path, skill_name: str) -> List[SkillIssue]:
    """验证 skill 依赖完整性"""
    issues = []
    
    try:
        content = skill_path.read_text(encoding='utf-8')
    except Exception as e:
        return issues
    
    # 提取依赖章节
    in_dependencies = False
    dependencies_text = []
    for line in content.split('\n'):
        if line.startswith('## 依赖') or line.startswith('## Dependencies'):
            in_dependencies = True
            continue
        if in_dependencies:
            if line.startswith('## '):
                break
            dependencies_text.append(line)
    
    if not dependencies_text:
        issues.append(SkillIssue(skill_name, 'warning', 'dependency', '缺少依赖章节'))
        return issues
    
    # 检查引用的工具
    deps_text = '\n'.join(dependencies_text)
    for tool in KNOWN_TOOLS:
        if tool in deps_text:
            # 检查工具是否在项目中存在
            if tool.endswith('.py'):
                tool_path = PROJECT_ROOT / tool
                if not tool_path.exists():
                    issues.append(SkillIssue(
                        skill_name, 'error', 'dependency',
                        f'依赖的脚本不存在: {tool}'
                    ))
            elif tool.startswith('mai-'):
                skill_dir = SKILLS_DIR / tool
                if not skill_dir.exists():
                    issues.append(SkillIssue(
                        skill_name, 'warning', 'dependency',
                        f'依赖的 skill 不存在: {tool} (可能需要安装)'
                    ))
    
    return issues


def verify_skill(skill_dir: Path) -> List[SkillIssue]:
    """验证单个 skill"""
    skill_name = skill_dir.name
    skill_path = skill_dir / 'SKILL.md'
    
    if not skill_path.exists():
        return [SkillIssue(skill_name, 'error', 'structure', 'SKILL.md 文件不存在')]
    
    issues = []
    issues.extend(verify_skill_structure(skill_path, skill_name))
    issues.extend(verify_skill_format(skill_path, skill_name))
    issues.extend(verify_skill_dependencies(skill_path, skill_name))
    
    return issues


def verify_all_skills() -> Dict[str, List[SkillIssue]]:
    """验证所有 skills"""
    all_issues = {}
    
    if not SKILLS_DIR.exists():
        return {'_global': [SkillIssue('_global', 'error', 'structure', f'Skills 目录不存在: {SKILLS_DIR}')]}
    
    for skill_dir in SKILLS_DIR.iterdir():
        if skill_dir.is_dir() and not skill_dir.name.startswith('.'):
            issues = verify_skill(skill_dir)
            if issues:
                all_issues[skill_dir.name] = issues
    
    return all_issues


def print_report(all_issues: Dict[str, List[SkillIssue]], verbose: bool = False):
    """打印验证报告"""
    total_errors = 0
    total_warnings = 0
    total_info = 0
    
    print("=" * 60)
    print("Skill 静态验证报告")
    print("=" * 60)
    
    for skill_name, issues in sorted(all_issues.items()):
        errors = [i for i in issues if i.level == 'error']
        warnings = [i for i in issues if i.level == 'warning']
        infos = [i for i in issues if i.level == 'info']
        
        total_errors += len(errors)
        total_warnings += len(warnings)
        total_info += len(infos)
        
        if errors or warnings or verbose:
            print(f"\n📋 {skill_name}")
            print("-" * 40)
            
            for issue in errors:
                print(f"  ❌ {issue}")
            for issue in warnings:
                print(f"  ⚠️  {issue}")
            if verbose:
                for issue in infos:
                    print(f"  ℹ️  {issue}")
    
    print("\n" + "=" * 60)
    print("📊 统计")
    print("=" * 60)
    print(f"  ❌ 错误: {total_errors}")
    print(f"  ⚠️  警告: {total_warnings}")
    print(f"  ℹ️  信息: {total_info}")
    
    if total_errors > 0:
        print("\n❌ 验证失败：存在错误需要修复")
        return False
    elif total_warnings > 0:
        print("\n⚠️  验证通过：存在警告建议修复")
        return True
    else:
        print("\n✅ 验证通过：所有检查项正常")
        return True


def get_changed_skills() -> List[str]:
    """获取 git 修改的 skill 文件"""
    import subprocess

    try:
        # 获取暂存区修改的文件
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACM'],
            capture_output=True, text=True, cwd=PROJECT_ROOT
        )
        if result.returncode != 0:
            return []

        changed_files = result.stdout.strip().split('\n')
        skills = set()
        for file in changed_files:
            # 匹配 skills/<name>/SKILL.md 模式
            match = re.match(r'skills/([^/]+)/SKILL\.md$', file)
            if match:
                skills.add(match.group(1))
        return list(skills)
    except Exception:
        return []


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='Skill 静态验证')
    parser.add_argument('--verbose', '-v', action='store_true', help='显示详细信息')
    parser.add_argument('--fix', action='store_true', help='自动修复可修复的问题')
    parser.add_argument('--skill', '-s', help='验证指定的 skill')
    parser.add_argument('--changed-only', '-c', action='store_true', help='只验证 git 修改的 skill')

    args = parser.parse_args()

    if args.changed_only:
        changed_skills = get_changed_skills()
        if not changed_skills:
            print("✅ 没有修改 skill 文件")
            sys.exit(0)
        print(f"🔍 验证修改的 skill: {', '.join(changed_skills)}")
        all_issues = {}
        for skill_name in changed_skills:
            skill_dir = SKILLS_DIR / skill_name
            if skill_dir.exists():
                issues = verify_skill(skill_dir)
                if issues:
                    all_issues[skill_name] = issues
    elif args.skill:
        skill_dir = SKILLS_DIR / args.skill
        if not skill_dir.exists():
            print(f"❌ Skill 不存在: {args.skill}")
            sys.exit(1)
        all_issues = {args.skill: verify_skill(skill_dir)}
    else:
        all_issues = verify_all_skills()

    success = print_report(all_issues, args.verbose)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
