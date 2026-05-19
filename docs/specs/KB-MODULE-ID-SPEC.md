# KB-MODULE-ID-SPEC — 知识模块唯一标识规范

> 状态：v1.0（2026-05-18）· 强制 · pedagogy 域跨层 join 的对齐键
> 配套：[KB-LAYOUT.md](./KB-LAYOUT.md)、[EXAM-SLUG-SPEC.md](./EXAM-SLUG-SPEC.md)

## 1. 为什么需要它

`diagnostics`（量规）/ `mistakes`（易错）/ `learning-paths`（路径）/ `quick-tests`（测评）
四层**按模块逐一对应**，是私人教研组推理内核的 join 键。现状有 **3 种写法**冲突：

- 文件名：kebab-case `statistics-and-probability.yaml`
- `module_id:` 字段：camelCase `statisticsAndProbability`
- quick-test `target_modules:`：camelCase `numbersAndExpressions`

key 不统一 = 四层 join 必碎。本规范收口为唯一真相。

## 2. 规范

### 2.1 格式

- **kebab-case**（小写 + 连字符），与文件名、EXAM-SLUG-SPEC 一致
- 仅 `[a-z-]`；无大写、无下划线、无中文
- **subject 命名空间**：完整键 = `<subject>/<module-id>`（`writing` 在
  chinese 与 english 各一，靠 subject 区分）
- 文件名（去 `.yaml`）、`meta.module_id` 字段、跨层引用三者**必须一致**

### 2.2 模块全集（26，5 科）

| subject | module-id |
|---|---|
| `math` | `numbers-and-expressions` `equations-and-inequalities` `functions` `triangles` `quadrilaterals` `circles` `geometry-comprehensive` `statistics-and-probability` |
| `chinese` | `basic-usage` `classical-reading` `masterpiece-reading` `modern-reading` `writing` |
| `english` | `grammar-basics` `grammar-advanced` `cloze` `reading` `writing` |
| `physics` | `sound-light-heat` `mechanics` `electricity` `experiments` `calculation` |
| `politics` | `moral-law` `national-conditions` `current-affairs` `answer-techniques` |

新增模块先在此表登记，再建文件。

## 3. 硬约束

1. pedagogy 四层每文件 `meta.module_id` 必填且属上表
2. 跨层引用模块一律用 `<subject>/<module-id>`，禁裸 camelCase
3. 文件名即 module-id（`<module-id>.yaml`）

## 4. 迁移（现状 → 规范）

现存 camelCase `module_id:` 字段需批量改 kebab（KB-LAYOUT 阶段 3）：
`statisticsAndProbability → statistics-and-probability` 等，配 `kb_lint.py` 校验。
文件名已是 kebab，无需动。

## 5. 唯一真相点

本表。任何脚本/数据与之冲突，改数据或本表，不另立。
