# 学情报告生成 — 产品功能标准化规格

> **版本**：v1.1（生产框架版）| **更新日期**：2026-05-30
> **关联文档**：[`../product/PRD.md`](../product/PRD.md) · [`EXAM-SLUG-SPEC.md`](EXAM-SLUG-SPEC.md) · [`STUDENT-PROFILE-SPEC.md`](STUDENT-PROFILE-SPEC.md)
> **变更**：v0.1（2026-05-13 草案，五步流水线纸面方案）→ v1.1：生产已上线 https://zhongkao.gatesby.xyz，本文档刻画**已经稳定运行的方案框架**。后续在框架基础上完善细节，不再做架构级的大改动。

---

## 0. 规格使用约定

本规格是「**生产架构的锚点**」，目的是终结"功能实现方案反复横跳"。

- **Locked（🔒）** 标记的章节 = 经过生产验证的稳定方案，**改动需明确理由+回归**
- **Iterating（🔄）** 标记 = 内部参数/阈值在持续调优，但接口/总体策略不变
- **Open（⏳）** 标记 = 已识别的产品缺口，待迭代决策

---

## 1. 产品视图

### 1.1 当前形态 🔒

- **入口**：https://zhongkao.gatesby.xyz （Vue SPA，无小程序版本）
- **用户**：家长直接 Web 上传答题卡，5 分钟内拿到 PDF 报告
- **后端**：阿里云 ECS（39.103.70.47）+ FastAPI + SQLite + 工作线程；详见 §4
- **覆盖**：北京 13 区 · 6 计分科目 · 一模/二模/真题，KB 共 82+ 卷（首页 `/api/coverage` 实时展示）

### 1.2 用户流程 🔒

```
首页 → 拍/选 4 张答题卡 → 上传
   ↓ (后端识别考试 + 学生姓名，5-10 秒)
确认考试页（含 PDF 卷面预览，家长可纠正姓名）→ 点"开始分析"
   ↓
(可选) 上传老师小分 Excel /  跳过让系统自动判分
   ↓ (后端 3-5 分钟)
处理进度页（5 阶段实时推进）
   ↓
报告页（PDF 下载 + 在线浏览）
```

**已经停止支持**的早期设计（v0.1 提过但未实现 / 已弃）：
- ❌ 小程序入口（改 Web SPA，触达更快、迭代更快）
- ❌ 班主任群聊触发（独立产品，与学情分析解耦）
- ❌ 一次性签名 token（暂用 analysis_id URL 隔离，强隔离待商业化阶段做）

### 1.3 实测案例

| 学生 | 考试 | 分数 | 备注 |
|------|------|------|------|
| 关丽涵 | 2026 海淀二模 物理 | 57.5/70 | Path B 选择题零误判，含 Q11/12/13/14/15 难判全对 |
| 贾小淇 | 2026 朝阳一模 物理 | 60/70 | 缺字母法基线，无回归 |

---

## 2. 五阶段流水线（State Machine） 🔒

每个 analysis 在 SQLite `analyses` 表中按以下状态机演化：

```
detecting          ─→ ready_confirm ─→ running ─→ done | failed
(L0 上传识别考试)    (家长确认页)      (L2-L5)     (终态)
```

后端推进阶段：

| stage | name | 主要动作 | 耗时 | 实现文件 |
|-------|------|----------|------|----------|
| 1 | 识别考试信息 | 上传 4 张照片 → vl-max card_meta 抽考试名+学生名 → exam_match 命中 KB yaml | 5-10s | `server/tasks.py::_L0_detect` |
| 2 | 识别答题卡作答 | **Path B → 缺字母法 → Path A → vl-max** 四引擎选择题（§3.1）+ 腾讯云方框检测裁主观题 | 15-30s | `scripts/answer-card-ocr/detect.py` |
| 3 | 对照标准答案 / 系统自动判分 | 若有老师 xlsx → parse_scores；否则 vl-max 并发逐题判 + 整页兜底 | 30-60s | `server/parse_scores.py` / `server/auto_grade.py` |
| 4 | AI 分析失分主因 | 失分题并发归因 LLM（qwen-max，带 cache）+ 模块掌握度统计 | 30-60s | `scripts/student-report/lib/analyze.py` |
| 5 | 生成提分建议 | 整卷诊断 + 行动计划 LLM → MD → KaTeX HTML → Chrome PDF | 30-60s | `scripts/student-report/build_report.py` |

**总耗时目标**：3-5 分钟（含网络 + LLM 调用）。

**子进程边界**：1-2 在主进程跑（共享内存大模型），3 调 LLM API，4-5 是独立 build_report 子进程（stdout 通过 STAGE_MARKERS 推进度，stderr 直透 journalctl）。

---

## 3. 答题卡识别（核心难题，最复杂）

### 3.1 选择题：四引擎合并 🔒

**这是 v1.1 vs v0.1 最大变化**。v0.1 设想"OpenCV CV pipeline 兜底"，实际经过 8 周迭代收敛到**四引擎按优先级合并**。

#### 引擎清单

| 序号 | 引擎 | 实现 | API 成本 | 适用 | 关丽涵卡命中 |
|------|------|------|---------|------|--------------|
| **0** | **Path B 纯像素 blob** 🆕 v1.1 | y 直方图找涂卡行 → 行内 x 扫黑块 → 反推 base_x + 字母 | **0** | 海淀方括号 `1.[A][B][C][D]` | **15/15** |
| 1 | 缺字母法 | qwen-vl-ocr 读字母，涂黑 → OCR 读不到 → 推断填充 | qwen-vl-ocr 1 call | 朝阳裸字母 `1. A B C D` | 8/15（多选） |
| 2 | Path A bbox + 像素 | qwen-vl-max 接地返回 `[X]` bbox → 本地 numpy 密度 | qwen-vl-max 1 call | 海淀（备用） | 9/15 |
| 3 | qwen-vl-max 直接判 | 看图直接给字母 | qwen-vl-max 1 call | 兜底（不稳定） | 不稳 |

#### 合并优先级 🔒

```python
# detect.py:detect_card 中合并逻辑
if blob_choices[qid].filled and conf >= 0.9:   # Path B 强信号
    use blob
elif qid in real_hits:                         # 缺字母法真识别（filled 非空）
    use 缺字母法
elif density_choices[qid].filled and conf >= 0.85:  # Path A 强信号
    use density
elif density_choices[qid].filled:               # Path A 弱
    use density
elif vlmax_choices[qid].filled:                 # vl-max 兜底
    use vl-max
else:                                            # 全空 → no_answer
    use 缺字母法 no_answer 推断
```

每个 answer 记录 `source` 字段（`blob`/`缺字母`/`density`/`vl-max`/`no_answer`）方便事后审计。

#### Path B 原理 🔒

```
1. y 直方图：每行扫 300-2250 列 x 范围内黑像素数
   - 100 < n < 800 → 涂卡行候选
   - 连续 ≥ 24 px 高 → 涂卡行 band（过滤 banner 边缘）
2. 行内 x 直方图：每列扫 band 高度内黑像素数 → 平滑 → 找连续高密度区间
   - 宽 20-80 px → 涂卡 blob 中心
3. 反推 base_x：每个 blob 假设是某列某字母 → 候选 = blob - col*345 - letter*70
   - bin=5 直方图投票最高峰 → 真 base_x
4. blob 中心 → 反推 (qi, letter)：(blob.x - base_x) mod 345 → 字母偏移 70-step
```

**关键参数**（关丽涵卡校准）🔄：
- `COL_STEP_INTER = 345` 题间距
- `LETTER_STEP = 70` 字母间距
- `CELL_W = 75, CELL_H = 50` 计 density 时
- `tol = 18` blob 中心到 letter 位置容差

**Layout 假设** 🔒：海淀/朝阳标准物理答题卡 5×3 单选 + 1 多选行：
```python
_LAYOUT_5x3 = {
    "rows": [{1-5, multi=F}, {6-10, multi=F}, {11-12, multi=F}, {13-15, multi=T}],
    "n_pos_per_row": 5,
}
```
其他学科/区如不匹配 → Path B 返回空 → 自动 fallback。**朝阳卡 Path B 找不到 4 个 row band → 缺字母法接管**（实测无回归）。

#### 已被否决的方案

| 方案 | 否决原因 |
|------|----------|
| 标准答题卡（家长打印 PDF） | 用户摩擦太大，B 端独立产品 |
| 模板匹配 | 海淀/朝阳/西城每区印版略不同，模板维护成本高 |
| qwen-vl-max 主路径直接判 | 模型 prior 把涂黑当 token 噪声补全字母，朝阳卡 -15 分回归 |
| 单一 OCR 引擎 | 任意单引擎都有死角，多引擎按 source 区分置信度才稳 |

### 3.2 主观题：裁切 + 手写 OCR + AI 评分 🔒

#### 流程

```
1. 腾讯云 GeneralAccurateOCR 检测每页方框（粉色/黑色框）
2. 框内题号文本 (qwen-vl-ocr) 识别 → 框 → qid 映射
3. 严格几何 fallback：prev+next qid 都已知且只缺 1 个 → 补中间
4. 框图 → 讯飞手写 OCR 识别学生作答文字
5. 切图 + 文字 → qwen-vl-max 单题打分（带 cropped 图 + 标答 + 步骤 prompt）
6. 兜底：腾讯云裁切失败的题号 → qwen-vl-max 看整页打分
```

**关键文件**：
- `scripts/answer-card-ocr/crop_subjective.py` — 腾讯云方框检测 + 严格 fallback
- `scripts/answer-card-ocr/xfyun_ocr.py` — 讯飞手写
- `scripts/answer-card-ocr/subjective_grade.py` — vl-max 单题/整页打分

#### 评分稳定性 ⏳

主观题 vl-max 评分波动 ±5 分（同一卡跑多次结果不同）。已识别的改善方向（未实施）：
1. 切分质量提升（用户提议：先切分准再上大模型）
2. 多次评分取中位数
3. 教师人工抽查机制

---

## 4. 后端架构 🔒

### 4.1 服务部署

| 组件 | 位置 | 配置 |
|------|------|------|
| FastAPI app | `/opt/zhongkao-agent/server/main.py` | systemd `zhongkao.service`，uvicorn :8200 |
| Web SPA | `/opt/zhongkao-agent/web/dist` | Nginx 反代 |
| HTTPS | https://zhongkao.gatesby.xyz | Let's Encrypt 证书 |
| 知识库 | `/opt/zhongkao-agent/knowledge-base/exams/` | git pull 同步 |
| 存储 | `students/_web/<aid>/` + `out/student-reports/<aid>/` | 本地文件 |
| DB | `server/data.sqlite3` | SQLite，`analyses` 表 |

### 4.2 API 端点 🔒

| Method | Path | 用途 |
|--------|------|------|
| GET | `/api/health` | 健康检查 |
| POST | `/api/analyses` | L0：multipart 上传 1-N 张照片 → 返回 `aid` |
| GET | `/api/analyses/{aid}/detect` | 拉考试识别结果（轮询用） |
| POST | `/api/analyses/{aid}/start` | 家长确认页"开始分析"，可传 `student_name` 覆盖 |
| POST | `/api/analyses/{aid}/scores` | 上传老师小分 xlsx；不传则系统自动判分 |
| GET | `/api/analyses/{aid}/status` | 轮询当前 stage |
| GET | `/api/analyses/{aid}/report` | 返回 report.json |
| GET | `/api/analyses/{aid}/report.pdf` | 下载 PDF |
| GET | `/api/analyses/{aid}/paper.pdf` | 下载试卷原卷（家长核对用） |
| GET | `/api/coverage` | 首页 KB 覆盖范围（1h 内存缓存） |
| GET | `/api/analyses` | 后台分析列表 |

### 4.3 数据契约（核心 JSON 文件）

学生分析目录 `students/_web/<aid>/<exam_slug>/`：

| 文件 | 由谁产出 | 内容 |
|------|---------|------|
| `student.json` | L0 card_meta | `{name, examId}` |
| `answer-card.json` | L2 detect_card | `{student, answers: [{qId, type, filled, confidence, ocrSeen, source, ...}]}` |
| `scores.json` | L3 parse_scores 或 auto_grade | `{examTotal, questions: [{qId, scored, fullScore, ...}]}` |
| `answer-card-photos/` | L0 | 原始照片 + cropped/q{NN}.png 主观题裁切 |
| `.score_source` | L3 | `teacher_xlsx` 或 `auto_grade` 标记 |

报告输出 `out/student-reports/<aid>/<exam_slug>/`：

| 文件 | 内容 |
|------|------|
| `report.md` | Markdown 源 |
| `report.pdf` | 最终 PDF（KaTeX 渲染数学/物理公式） |

### 4.4 LLM 缓存策略 🔒

**Cache key 必含 `student_filled + std_answer` md5**：

```python
sig = f"{q.student_filled or ''}|{q.std_answer or ''}"
qkey = f"{q.qid}-{hashlib.md5(sig.encode()).hexdigest()[:8]}"
cache_key = f"report-v4-{student_name}-{slug}-{qkey}"
```

**v0.1 教训**：早期 cache key 仅 `student_name + slug + qid` 不含作答。当答题卡 OCR 修复重跑后，旧 cache 命中 → 报告还用旧"未作答"分析 → 报告内容与实际作答错位（关丽涵 Q8/10/12 踩坑）。v1.1 修复后，作答任意改动 → cache miss → 自动重算。

### 4.5 容量与故障

**已知问题** ⏳：
- 阿里云 ECS 内存有限，并发跑多份分析 → OOM kill（systemd 自动重启，但当前任务僵死）
- 应对：单 worker 串行执行，或加内存监控提前拒绝

---

## 5. 知识库（exam yaml） 🔒

**结构**（详见 [`KB-LAYOUT.md`](../architecture/KB-LAYOUT.md) + [`EXAM-FORMAT-SPEC.md`](EXAM-FORMAT-SPEC.md)）：

```
knowledge-base/exams/mock/<subject>/beijing/<year>-<district>-<exam_type>.yaml
                  zhenti/<subject>/beijing/...
```

**当前覆盖**（2026-05-30）：
- 13 区 × 6 科目 × 一模 ≈ 60 卷已就绪
- 二模 13 区物理/数学/英语完成；语文道法部分区进行中
- 真题：2024-2025 北京中考 6 科

**yaml 必备字段**：
- `meta`：district / subject / year / examType / duration / fullScore
- `questions`：每题 `{qId, type, score, stem, options?, answer, solution, knowledgePoints, module}`
- `figures`：题面图片（PNG）

**新增卷的生产路径** 🔒：
- docx 路线（首选）：`scripts/exam-docx/{chinese,math,english,physics,politics}_docx_paper.py` + `*_inspect.py`
- 图片路线（无 docx 时）：`scripts/exam-ocr/*_image_paper.py`

---

## 6. 错误预算与回归门控 🔄

### 6.1 选择题识别 SLA 目标

| 指标 | 当前 | 目标 |
|------|------|------|
| 海淀方括号格式准确率 | 100%（关丽涵 15/15） | ≥ 99% |
| 朝阳裸字母准确率 | 100%（贾小淇 baseline） | ≥ 99% |
| 其他区（西城/东城/...） | 未充分测试 | ≥ 95% |

### 6.2 主观题切分 SLA 目标

| 指标 | 当前 | 目标 |
|------|------|------|
| 腾讯云方框命中率 | 4-11/11（不稳定） | ≥ 80% |
| 严格 fallback 触发率 | <20% | <30% |
| vl-max 整页兜底触发 | 0-7/11（与命中率反相关） | < 50% |

### 6.3 回归测试套件 🔒

**测试 case 命名规范**（对齐 `exam_slug` 后缀）：

```
<拼音>-<区>-<场次>-<学科>
       │     │      │
       │     │      └─ math / physics / chinese / english / politics
       │     └────── yi（一模）/ er（二模）/ zhenti（中考真题）
       └─────────── haidian / chaoyang / xicheng / ...
```

例：`guanlihan-haidian-er-physics`（关丽涵 海淀二模 物理）

`scripts/test/e2e_audit.py` 跑端到端：
- `CASES=guanlihan-haidian-er-physics` → 海淀二模 物理（Path B 标准回归）
- `CASES=jiaxiaoqi-chaoyang-yi-physics` → 朝阳一模 物理（缺字母法基线）
- `SCENARIOS=auto` 或 `teacher_xlsx`

**部署后 must run**：双 case 跑通且分数稳定（±2 分）才能合并到 main。
完整 case 清单见 [`test-data/README.md`](../../test-data/README.md)。

---

## 7. 安全 / 隐私 🔒

- `learning situation/`、`students/`、`test-data/_runs/` 全部 gitignore
- 学生数据按 `aid`（随机 12 字节十六进制）隔离，无认证（当前 alpha 阶段）
- API key（DashScope/腾讯云/讯飞）systemd 环境变量注入，不落代码
- GitHub 已开 push protection，禁止 secret 入仓

**待商业化时增加** ⏳：
- 微信 OAuth 登录 + `unionid` 绑定
- 报告 URL 一次性签名 token（1h 过期）
- 学生数据 60 天自动归档

---

## 8. 待办与缺口 ⏳

按优先级：

| 优先级 | 项 | 说明 |
|-------|----|----|
| P0 | 主观题切分质量 | 切分→大模型链路："先切准"，参考 §3.2 改善方向 |
| P1 | KB 覆盖到全 13 区 6 科二模 | 4 类 docx parser 已就绪，按区批跑 |
| P1 | OOM 防御 | 服务并发限流 + 内存监控 |
| P2 | 多卷综合学情（多次考试对比） | PRD 已规划，需要历史数据积累 |
| P2 | 教师后台批量生成 | B 端需求，单租户暂不做 |

---

## 9. 与早期版本（v0.1）的关键差异

| 维度 | v0.1（2026-05-13 草案） | v1.1（2026-05-30 生产） |
|------|------------------------|-----------------------|
| 入口 | 小程序 | Web SPA |
| 涂卡方案 | OpenCV bubble detect（设想） | **4 引擎合并，Path B 像素 blob 首选**（实证） |
| 答案匹配 | answer-key.json（待开发） | KB exam yaml `answer` 字段（已落 80+ 卷） |
| 报告渲染 | MD → HTML → PDF（设想） | MD → KaTeX HTML → Chrome --headless=new（已部署） |
| LLM 缓存 | 未提及 | student_filled+std_answer md5 hash 入 key |
| API | 4 个端点设想 | 12+ 端点已上线 |
| 部署 | 未明确 | 阿里云 ECS + Nginx + HTTPS |

**核心 insight**：v0.1 推断"涂卡 OCR 是最大风险"是对的，但解决路径预测错了 —— **不是 OpenCV bubble detect，而是 4 引擎按 source 区分置信度合并**。Path B 这一招直到 v1.1 才被发明，把海淀格式从 0% 拉到 100%。

---

## 10. 术语表

| 术语 | 含义 |
|------|------|
| exam_slug | `<year>-<district_en>-<exam_type_en>-<subject_en>`，如 `2026-haidian-er-physics` |
| aid | analysis_id，12 位十六进制，本次分析的唯一标识 |
| Phase A / B | A=选择题识别（§3.1）；B=主观题切分+评分（§3.2） |
| Path A / B | 选择题识别的两条像素技术路线：A=vl-max bbox + density；B=纯 blob 检测 |
| 缺字母法 | qwen-vl-ocr 读字母，涂黑 → 看不到字母 → 推断填充 |
| real_hit | 缺字母法识别到非空填充（type=choice/multi_choice），区别于 no_answer |
| KB | knowledge-base/exams 下的标准答案 yaml |
| 五问 | 家长 5 大关切，见 [`PRD.md`](../product/PRD.md) §1.3 |
