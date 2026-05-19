# EXAM-SLUG-SPEC — 试卷唯一标识规范

> 状态：v1.0（2026-05-18）· 强制 · 跨层 join 的对齐键

## 1. 为什么需要它

学情报告靠 slug 把**三方数据**对齐：试卷结构化（knowledge-base）↔ 学生答题卡（students）↔ 小分（scores）。slug 不统一 = join 失败 = 报告错配。当前历史遗留至少 3 套写法（`2026-chaoyang-yi` / `2026-chaoyang-yi-physics` / `2026-朝阳-一模`），本规范收口为唯一真相。

## 2. 规范

### 2.1 试卷级 slug（无科目）

```
<year>-<region>-<round>
```

- `year`：4 位公历年，试卷所属考年（如 `2026`）
- `region`：区县**拼音小写**，单段无连字符（`chaoyang` `daxing` `mentougou` `shijingshan`）。禁止中文、禁止 `chao-yang`
- `round`：轮次枚举 —
  - `yi` = 一模、`er` = 二模、`san` = 三模
  - `zhen` = 真题/中考真题
  （与 `scripts/exam-ocr/paths.py:_TYPE` 一致：`yimo→yi / ermo→er / sanmo→san / zhenti→zhen`）

示例：`2026-chaoyang-yi`、`2025-beijing-zhen`

### 2.2 卷-科目级 slug（带科目）

```
<year>-<region>-<round>-<subject>
```

- `subject`：英文小写枚举 `physics | math | chinese | english | politics`（与 `knowledge-base/mock-exams/<subject>/` 一致）

示例：`2026-chaoyang-yi-physics`

### 2.3 选用规则

| 场景 | 用哪种 |
|---|---|
| `knowledge-base/mock-exams/<subject>/beijing/<slug>/` 目录 | **试卷级**（科目已在路径上，不重复） |
| 跨科目聚合 / 学生数据目录 / 交付物文件名 | **卷-科目级** |
| 程序内对齐键 | 卷-科目级（信息最全，最稳） |

## 3. 硬约束

1. 仅 `[a-z0-9-]`；无空格、无中文、无大写、无下划线作分隔
2. 段数恰为 3（试卷级）或 4（卷-科目级），用单 `-` 连接
3. `region` 拼音以 `scripts/exam-ocr/paths.py` 推导为准；新区县先在该文件登记
4. 目录名、文件名、JSON 内 `slug` 字段三者必须一致

## 4. 唯一真相点

`scripts/exam-ocr/paths.py:derive_out_dir()` 是 slug 的**程序事实标准**。任何脚本/文档与它冲突时改脚本调用方或本规范，不各自硬编码。
