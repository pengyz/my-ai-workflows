# IPD 富文本格式说明

## 概述

IPD 评论的 `content` 字段格式：**直接传 HTML 字符串**

```bash
# 正确 ✅
content="<p><b>标题</b></p><p>内容</p>"

# 错误 ❌ - 不要使用 JSON 数组
content='[{"type":"text","text":"<p>内容</p>"}]'
```

## HTML 标签使用

### 基本标签

- `<p>...</p>` - 段落（段落间有间距）
- `<br>` - 段落内换行
- `<b>...</b>` - 粗体
- `<code>...</code>` - 代码片段（灰色背景）

### 组合示例

```html
<p><b>【标题】</b></p>
<p><b>子标题</b></p>
<p>第一行<br>第二行<br>第三行</p>
<p>代码示例：<code>File.kt:123</code></p>
```

渲染效果：
```
【标题】（粗体）

子标题（粗体）

第一行
第二行
第三行

代码示例：File.kt:123（灰色背景）
```

## 关键要点

### 1. 直接传 HTML 字符串

**正确** ✅
```bash
content="<p><b>【标题】</b></p><p>段落1</p><p>段落2</p>"
```

**错误** ❌
```bash
# 不要使用 JSON 数组格式
content='[{"type":"text","text":"<p>内容</p>"}]'
```

### 2. 段落和换行

**段落分隔**（有间距）：
```html
<p>第一段</p>
<p>第二段</p>
```

**段内换行**（无间距）：
```html
<p>第一行<br>第二行<br>第三行</p>
```

### 3. 代码标记

```html
<code>File.kt:123</code>
<code>HH:MM:SS.mmm</code>
<code>commit_hash</code>
```

效果：灰色背景的代码片段

### 4. 完整示例

```html
<p><b>【根因定谳 + 修复已提交】</b></p>
<p><b>结论</b>：问题的一句话描述</p>
<p><b>根因（实证）</b></p>
<p>日志证据：<br>
<code>15:05:23.456 SearchTool: timeout after 300s</code><br>
<code>15:10:01.567 返回错误: TIMEOUT</code></p>
<p>代码证据：<br>
定位到 <code>SearchTool.kt:123</code><br>
设置了 <code>DEFAULT_TIMEOUT = 300_000</code></p>
<p><b>问题定界</b></p>
<p>主责：<b>Android 端</b><br>
依据：<br>
1. 日志 <code>agent.log:123</code> 显示超时配置 300s<br>
2. PC 端搜索实际耗时 > 300s<br>
3. 无动态调整机制</p>
<p><b>修复方案</b></p>
<p>1. 增加超时时间到 600s<br>
2. 添加增量返回机制</p>
<p><b>验证结果</b></p>
<p>✓ 编译通过<br>
✓ 测试通过 (25/25)</p>
<p>MR: https://git.n.xiaomi.com/...<br>
Commit: <code>abc123def456</code></p>
```

## 在代码中使用

### Bash 脚本中构造

```bash
# 方式 1：直接字符串
content="<p><b>【修复完成】</b></p><p>根因：XXX</p><p>修复：YYY</p>"

# 方式 2：使用 heredoc（推荐，更清晰）
content=$(cat <<'EOF'
<p><b>【根因定谳 + 修复已提交】</b></p>
<p><b>结论</b>：问题一句话描述</p>
<p><b>根因（实证）</b></p>
<p>日志证据：<br>
<code>15:05:23.456 Component: 关键日志</code><br>
<code>15:10:01.567 Component: 错误信息</code></p>
<p>代码证据：<br>
定位到 <code>File.kt:123</code><br>
逻辑说明...</p>
<p><b>问题定界</b></p>
<p>主责：<b>Android 端</b><br>
依据：<br>
1. 日志证据<br>
2. 代码证据</p>
<p><b>修复方案</b></p>
<p>1. 修复点1<br>
2. 修复点2</p>
<p><b>验证结果</b></p>
<p>✓ 编译通过<br>
✓ 测试通过</p>
<p>MR: https://git.n.xiaomi.com/...<br>
Commit: <code>abc123</code></p>
EOF
)

# 调用 MCP 工具
mcp__mi-adt__M_saveComment \
  --userName "pengyaozong" \
  --issId "ISS-xxx" \
  --content "$content"
```

### 注意事项

1. **不要转义 HTML 标签**
   - ✅ 正确：`<p>内容</p>`
   - ❌ 错误：`&lt;p&gt;内容&lt;/p&gt;`

2. **在 heredoc 中使用单引号**
   ```bash
   content=$(cat <<'EOF'  # 注意是 <<'EOF' 不是 <<EOF
   <p><b>标题</b></p>
   EOF
   )
   ```
   这样可以避免变量展开。

3. **特殊字符不需要转义**
   - `<` `>` 直接使用
   - `"` 如果在双引号字符串中需要转义：`\"`
   - 在 heredoc 中都不需要转义

## 完整的 MCP 调用示例

```bash
#!/bin/bash

# 构造评论内容
content=$(cat <<'EOF'
<p><b>【根因定谳 + 修复已提交】</b></p>
<p><b>结论</b>：搜索三方 PC 压缩文件时超时</p>
<p><b>根因（实证）</b></p>
<p>日志证据：<br>
<code>15:10:01.567 SearchTool: timeout after 300s</code><br>
<code>15:10:01.580 返回错误: TIMEOUT</code></p>
<p>代码证据：<br>
定位到 <code>SearchTool.kt:123</code><br>
设置了 <code>DEFAULT_TIMEOUT = 300_000L</code></p>
<p><b>问题定界</b></p>
<p>主责：<b>Android 端</b><br>
依据：<br>
1. 超时配置固定 300s<br>
2. 未考虑三方 PC 大文件量场景<br>
3. 无增量返回机制</p>
<p><b>修复方案</b></p>
<p>1. 增加超时时间到 600s<br>
2. 添加增量返回机制<br>
3. 添加超时日志埋点</p>
<p><b>验证结果</b></p>
<p>✓ 编译通过<br>
✓ 测试通过 (25/25)<br>
✓ 真机验证通过</p>
<p>MR: https://git.n.xiaomi.com/osbot/osbot/-/merge_requests/123<br>
Commit: <code>abc123def456789</code></p>
EOF
)

# 调用 MCP 添加评论
echo "添加 IPD 评论..."
# 实际调用方式取决于你的 MCP 客户端
```

