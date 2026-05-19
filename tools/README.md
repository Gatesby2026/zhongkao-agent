# tools/

正式工具目录。区别于 `scripts/`（一次性 / 流水线脚本），这里放：
- 长期维护、有版本意识的工具
- 给团队成员/未来自己反复使用的命令行
- 每个子目录是一个独立工具，自带 README + launcher + 测试

## 工具清单

| 工具 | 路径 | 用途 |
|---|---|---|
| `exam-review` | `tools/exam-review/` | Mock-exam YAML 审核（HTML 可视化 + 标注） |

## 约定

每个工具子目录至少包含：

```
tools/<tool-name>/
├── README.md          # 使用说明 + 检测项 / 输入输出格式
├── <tool-name>        # bash launcher（PATH 入口，可执行）
├── <module>.py        # Python 主程序
└── templates/         # 如有 HTML/邮件模板
```

加入 PATH 后所有工具一行可用：

```bash
export PATH="$PATH:$HOME/projects/zhongkao-agent/tools/exam-review"
# 或者用 stow / symlink 到 ~/.local/bin
```
