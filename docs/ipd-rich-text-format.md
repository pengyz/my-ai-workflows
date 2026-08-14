# IPD 富文本格式说明

## 概述

IPD 评论的 `content` 字段支持两种格式：
1. **纯文本**：直接传字符串
2. **富文本**：传 JSON 数组（推荐，支持格式化、@人等）

## 富文本结构

富文本是一个 JSON 数组，每个元素是一个节点对象。

### 基本节点类型

#### 1. 文本节点 (text)

```json
{"type": "text", "text": "这是普通文本"}
```

文本内容可以包含 HTML 标签：
```json
{"type": "text", "text": "<b>粗体文本</b>"}
{"type": "text", "text": "<code>代码片段</code>"}
{"type": "text", "text": "<p>段落文本</p>"}
```

#### 2. 换行 (hardBreak)

```json
{"type": "hardBreak"}
```

#### 3. @某人 (mention)

```json
{
  "type": "mention",
  "id": "pengyaozong",           // 用户名（username）
  "label": "彭耀宗",              // 显示名称
  "enableNotification": true    // 是否通知
}
```

## 关键要点

### 1. HTML 标签的使用规则

**正确**：将整个格式化段落放在一个 text 节点中
```json
{
  "type": "text",
  "text": "<p><b>【标题】</b></p><p>段落内容</p>"
}
```

**错误**：不要将 `<p>` 标签和 `hardBreak` 混用
```json
// ❌ 错误 - <p> 标签会直接显示
{"type": "text", "text": "<p>内容</p>"},
{"type": "hardBreak"},
{"type": "text", "text": "<p>下一段</p>"}
```

### 2. 换行的两种方式

**方式 A：使用 `<p>` 标签（推荐用于段落）**
```json
{
  "type": "text",
  "text": "<p><b>标题</b></p><p>第一段内容</p><p>第二段内容</p>"
}
```

**方式 B：使用 `hardBreak`（推荐用于简单换行）**
```json
[
  {"type": "text", "text": "<b>标题</b>"},
  {"type": "hardBreak"},
  {"type": "text", "text": "第一行"},
  {"type": "hardBreak"},
  {"type": "text", "text": "第二行"}
]
```

**不要混用**：`<p>` 和 `hardBreak` 选择其一。

### 3. 专业分析的实际格式示例

```json
[{
  "type": "text",
  "text": "<p><b>【双向交叉校验｜结论等级：实证】</b></p><p><b>结论</b>：<b>核心问题一句话描述</b></p><p><b>根因（实证）</b></p><p>日志证据：<br><code>HH:MM:SS.mmm Component: 关键日志</code><br><code>HH:MM:SS.mmm Component: 错误信息</code></p><p>代码证据：<br>定位到 <code>File.kt:123</code><br>逻辑说明...</p><p><b>问题定界</b></p><p>主责：<b>[Android/PC]</b><br>依据：<br>1. 日志 <code>file.log:123</code> 显示 ...<br>2. 代码逻辑 ...</p><p><b>修复方案</b></p><p>1. 修复点1<br>2. 修复点2</p><p><b>验证结果</b></p><p>✓ 编译通过<br>✓ 测试通过</p><p>MR: <url><br>Commit: <code>hash</code></p>"
}]
```

**关键特征**：
- ✅ **整个分析作为一个 text 节点**
- ✅ 使用 `<p>` 分段，`<b>` 加粗，`<code>` 标记代码
- ✅ 在段落内使用 `<br>` 换行（不是 hardBreak）
- ✅ 无额外的 hardBreak 节点
- ✅ 结构清晰：结论 → 根因 → 定界 → 修复 → 验证

### 示例 1：简单格式化文本

```json
[
  {"type": "text", "text": "<b>【问题已修复】</b>"},
  {"type": "hardBreak"},
  {"type": "text", "text": "根因：XXX"},
  {"type": "hardBreak"},
  {"type": "text", "text": "修复方案：YYY"}
]
```

渲染效果：
```
【问题已修复】
根因：XXX
修复方案：YYY
```

### 示例 2：包含代码和链接

```json
[
  {"type": "text", "text": "<b>修复完成</b>"},
  {"type": "hardBreak"},
  {"type": "text", "text": "Commit: <code>abc123</code>"},
  {"type": "hardBreak"},
  {"type": "text", "text": "MR: https://git.n.xiaomi.com/..."}
]
```

### 示例 3：@某人

```json
[
  {"type": "text", "text": "问题已修复，请 "},
  {"type": "mention", "id": "qiushiding", "label": "邱诗定", "enableNotification": true},
  {"type": "text", "text": " 确认。"}
]
```

渲染效果：
```
问题已修复，请 @邱诗定 确认。
```

### 示例 4：复杂分析报告

```json
[
  {"type": "text", "text": "<p><b>【根因分析】</b></p>"},
  {"type": "text", "text": "<p><b>现象</b>：用户操作后出现 XXX</p>"},
  {"type": "hardBreak"},
  {"type": "text", "text": "<p><b>根因</b>：代码逻辑问题</p>"},
  {"type": "text", "text": "<code>SomeClass.kt:123</code> 处理异常时返回了 null"},
  {"type": "hardBreak"},
  {"type": "text", "text": "<p><b>修复方案</b></p>"},
  {"type": "text", "text": "1. 添加 null 检查"},
  {"type": "hardBreak"},
  {"type": "text", "text": "2. 增加日志埋点"},
  {"type": "hardBreak"},
  {"type": "hardBreak"},
  {"type": "text", "text": "<p><b>验证结果</b></p>"},
  {"type": "text", "text": "✓ 编译通过"},
  {"type": "hardBreak"},
  {"type": "text", "text": "✓ 测试通过 (25/25)"},
  {"type": "hardBreak"},
  {"type": "hardBreak"},
  {"type": "text", "text": "MR: https://git.n.xiaomi.com/.../6220"},
  {"type": "hardBreak"},
  {"type": "text", "text": "请 "},
  {"type": "mention", "id": "reviewer", "label": "审核人", "enableNotification": true},
  {"type": "text", "text": " review"}
]
```

## 支持的 HTML 标签

在 `text` 节点的 `text` 字段中可以使用：

| 标签 | 用途 | 示例 |
|------|------|------|
| `<b>` | 粗体 | `<b>重要</b>` |
| `<code>` | 行内代码 | `<code>func()</code>` |
| `<p>` | 段落 | `<p>段落内容</p>` |
| `<br>` | 换行（推荐用 hardBreak） | `文本<br>换行` |

## 构造富文本的辅助函数

### Python 示例

```python
def build_comment_content(sections):
    """
    构造 IPD 富文本评论
    
    Args:
        sections: 列表，每个元素是 (type, content)
            type: 'text' | 'break' | 'mention'
            content: 对应的内容
    
    Returns:
        JSON 字符串
    """
    nodes = []
    for section_type, content in sections:
        if section_type == 'text':
            nodes.append({"type": "text", "text": content})
        elif section_type == 'break':
            nodes.append({"type": "hardBreak"})
        elif section_type == 'mention':
            nodes.append({
                "type": "mention",
                "id": content['id'],
                "label": content['label'],
                "enableNotification": True
            })
    return json.dumps(nodes, ensure_ascii=False)

# 使用示例
content = build_comment_content([
    ('text', '<b>【修复完成】</b>'),
    ('break',),
    ('text', 'Commit: <code>abc123</code>'),
    ('break',),
    ('text', '请 '),
    ('mention', {'id': 'qiushiding', 'label': '邱诗定'}),
    ('text', ' 确认')
])
```

### Shell + jq 示例

```bash
# 简单文本
content=$(jq -nc '[
  {"type":"text","text":"<b>【修复完成】</b>"},
  {"type":"hardBreak"},
  {"type":"text","text":"Commit: abc123"}
]')

# 使用变量
commit_hash="abc123"
content=$(jq -nc --arg commit "$commit_hash" '[
  {"type":"text","text":"<b>【修复完成】</b>"},
  {"type":"hardBreak"},
  {"type":"text","text":("Commit: " + $commit)}
]')
```

## 调用 MCP 工具

```bash
# 使用富文本添加评论
mcp__mi-adt__M_saveComment(
  userName="pengyaozong",
  issId="ISS-202608-00051296A",
  content='[{"type":"text","text":"<b>问题已修复</b>"},{"type":"hardBreak"},{"type":"text","text":"详情见 MR"}]'
)
```

## 最佳实践

1. **使用粗体突出关键信息**：
   ```json
   {"type": "text", "text": "<b>【根因分析】</b>"}
   ```

2. **代码/路径用 code 标签**：
   ```json
   {"type": "text", "text": "文件: <code>src/main/Main.kt:123</code>"}
   ```

3. **结构化内容用段落**：
   ```json
   {"type": "text", "text": "<p><b>标题</b></p>"}
   {"type": "text", "text": "<p>内容...</p>"}
   ```

4. **@相关人员**：
   ```json
   {"type": "mention", "id": "username", "label": "显示名", "enableNotification": true}
   ```

5. **分段清晰**：
   多用 `hardBreak` 保持段落间距

## 常见错误

### ❌ 错误：直接传 HTML 字符串

```python
content = "<b>粗体</b><br>换行"  # 错误！会当成纯文本显示
```

### ✅ 正确：使用 JSON 数组

```python
content = json.dumps([
    {"type": "text", "text": "<b>粗体</b>"},
    {"type": "hardBreak"},
    {"type": "text", "text": "换行"}
])
```

### ❌ 错误：mention 缺少必需字段

```json
{"type": "mention", "id": "username"}  // 缺少 label
```

### ✅ 正确：完整的 mention

```json
{"type": "mention", "id": "username", "label": "显示名", "enableNotification": true}
```

## 参考

- 真实示例：IPD 问题单 846723 的评论
- MCP 工具：`mcp__mi-adt__M_saveComment`
- 格式验证：添加评论后在 IPD Web 界面查看渲染效果
