# 浏览器控制方法（稳定方案）

## 两个 MCP 组合使用

### 1. mcp__Control_Chrome__* — 导航和标签管理
不需要 Claude in Chrome 扩展，直接可用：
- `open_url(url, new_tab)` — 打开/跳转 URL
- `list_tabs()` — 列出所有标签
- `get_current_tab()` — 获取当前标签信息

### 2. mcp__Control_your_Mac__osascript — 页面 JS 交互

**前提（一次性设置，持久有效）**：
Chrome 菜单 → View → Developer → Allow JavaScript from Apple Events ✅

**读取页面状态：**
```applescript
tell application "Google Chrome"
  set theTab to active tab of front window
  set result to execute theTab javascript "JSON.stringify({title: document.title, url: location.href})"
  return result
end tell
```

**点击元素（fire and forget）：**
```applescript
tell application "Google Chrome"
  set theTab to active tab of front window
  execute theTab javascript "document.querySelector('.btn-download').click()"
end tell
delay 1
-- 再单独查询状态
```

**注意**：点击后如果页面跳转，JS 有时返回 `missing value`（undefined）属正常，需拆成两步：先 click，delay 后再查询新页面状态。

## 典型操作流程

1. `open_url` 导航到目标页面
2. `osascript` 执行 JS 读取页面结构，找到目标元素的 CSS selector
3. `osascript` 执行 JS 点击目标元素
4. `delay 1` 等待页面响应
5. `osascript` 执行 JS 查询操作结果

## Claude in Chrome 扩展（不依赖）
- 扩展已安装（ID: fcoeoabgfenejglbffodgkkbkcdhcgfn），native host 可启动
- 但 `mcp__Claude_in_Chrome__list_connected_browsers` 经常报 not connected
- **结论：不依赖此扩展，用 osascript 方案替代**
