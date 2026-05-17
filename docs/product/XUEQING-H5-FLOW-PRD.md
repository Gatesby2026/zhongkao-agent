# 学情分析 H5 闭环 — 流程 PRD（当前实现）

> 版本：v1.0 | 更新日期：2026-05-18
> 范围：**当前已实现并上线**的「答题卡照片 → 学情分析报告」H5+API 闭环
> 关系：本文是落地实现 PRD，区别于 `docs/product/PRD.md`（v5.0 微信生态战略愿景）。
> 线上：https://zhongkao.gatesby.xyz （阿里云 ECS，HTTPS）

---

## 一、产品目标

家长用手机拍下孩子的中考一模答题卡，上传后系统自动：
1. 识别这是哪场考试（区/科目/年份/轮次）+ 学生姓名 + 卷面完整性
2. 还原选择题涂卡 + 主观题作答（裁切原图 + 手写 OCR）
3. 判分（老师小分表优先；无则系统自动判分）
4. 对照标准答案逐题归因，产出一份学生向 PDF 学情报告

**核心价值**：把"一张照片"变成"每道失分题错在哪 + 怎么提分"的可执行诊断。

### 用户与场景

| 角色 | 场景 |
|---|---|
| 家长（主用户） | 拿到孩子一模答题卡，想知道丢分在哪、怎么补 |
| 学生 | 报告最终读者，要能照着报告独立做对失分题 |

---

## 二、端到端流程总览

```
家长拍照
   ↓ POST /api/analyses（多图）
[A 检测 detect ~10s]  card_meta(qwen-vl-max 读表头)
   → 考试身份 + 学生 + 卷面完整性
   → 按 slug 重命名学生目录 + student.json
   → status=ready_confirm
   ↓ 家长确认页（可改学生姓名 / 看试卷原卷核对）
   ↓ POST /api/analyses/{aid}/start?student_name=
[B 流水线 pipeline]
   1. detect.detect_card（技能完整三段）
      ├ Phase A 选择题缺字母法（qwen-vl-ocr）
      ├ Phase B 主观题腾讯云方框 + 讯飞手写裁切 → cropped/qNN.png
      └ Phase C qwen-vl-max 看图阅卷 → grade.{matchedPoints,missedPoints,suggestedScore}
   2. _ensure_scores（≤25s 等小分上传）
      ├ 有小分表(xlsx) → parse_scores → scores.json（teacher 权威）
      └ 无 → auto_grade：选择题确定性 + 主观题取 Phase C grade（auto）
   3. pa.run_report → build_report.py 子进程
      schemas.join → aggregate（零 LLM）→ analyze（qwen-max 归因）
      → render MD → md-to-pdf(Chrome headless+KaTeX) → PDF
   → status=done
   ↓ 报告屏（JSON 渲染 + 应用内 PDF 预览）
```

状态机：`detecting → ready_confirm →(/start)→ running → done | failed`

---

## 三、前端（web/，Vue3 + Vite + TS）

单页 SPA，移动端占满视口，桌面端居中限宽 480px。`step` 驱动 5 屏：

| step | 屏 | 关键交互 |
|---|---|---|
| 0 | 首屏引导 | 价值说明 + 4 步流程图 + 准备清单 + 「开始分析」+ **历史报告列表**（done 项点开直接进报告） |
| 1 | 答题卡 | 子阶段 `phase`：pick 选图 / detecting 识别中 / confirm 确认 / failed 失败重拍 |
| 1-confirm | 确认考试 | **学生姓名可编辑**（OCR 必错须可纠正）+ 查看试卷原卷核对 |
| 2 | 判分方式 | 二选一卡片：① 我有老师小分表（最精确）② AI 自动判分（智能估分） |
| 3 | 分析中 | 进度条 + 「预计 1–3 分钟」+ 5 阶段清单；失败 → 统一 state-card |
| 4 | 报告 | 数据来源 banner（teacher 绿 / auto 琥珀「估」）+ 总览 + 失分题精析 + 应用内 PDF 预览 |

- stepper：`答题卡→确认→分析→报告` 4 节点，由 `journeyStage` 计算（confirm 是 step1 子阶段、判分归"确认"）
- PDF 预览：全屏 overlay iframe，不跳新标签，留「新窗口」兜底
- 示例图：脱敏 CSS 示意（无真实学生照片）
- API 封装：`web/src/api.ts`

---

## 四、后端（server/，FastAPI + uvicorn）

### 接口

| 方法 路径 | 职责 |
|---|---|
| POST `/api/analyses` | 上传答题卡图 → submit_detect；无图 → reference 演示 |
| GET `/api/analyses/{aid}/detect` | 检测结果轮询（status/detected） |
| POST `/api/analyses/{aid}/start?student_name=` | 确认后启动流水线；写回纠正姓名 |
| POST `/api/analyses/{aid}/scores` | 上传班小二 xlsx → parse_scores → uploads/{aid}/scores.json |
| GET `/api/analyses/{aid}/status` | 阶段轮询 |
| GET `/api/analyses/{aid}/report` | 结构化报告 JSON |
| GET `/api/analyses/{aid}/report.pdf` | 报告 PDF（缺 Chrome 时 503） |
| GET `/api/analyses/{aid}/paper.pdf` | 试卷原卷 PDF（拼图） |
| GET `/api/analyses` | 历史列表 |

### 两段式后台任务（server/tasks.py）

- **A 检测** `_detect`：`card_meta.extract_card_meta`（qwen-vl-max 读表头）→ `exam_match.slug_from_meta` → 校验 KB yaml；识别不到 → `mark_failed`（提示重拍考生须知页标题行）；识别到 → 按 slug 重命名目录 + 写 student.json + `set_detected(ready_confirm)`
- **B 流水线** `_pipeline`：
  - `_subjective_qnums(KB yaml)` 推导主观题号（非选择题型）
  - `detect.detect_card(imgs, subjective_qnums=, standard_yaml=)` → 跑通技能 Phase A/B/C
  - student.json 姓名**始终覆盖**涂卡区 OCR（表头识别/家长纠正更可靠）
  - `_ensure_scores`：≤25s 等小分；超时走 `auto_grade`
  - `pa.run_report` → PDF；`mark_done`
- **reference** `_reference`：纯 reference 数据演示（无上传）

### 关键模块

| 文件 | 职责 |
|---|---|
| `server/card_meta.py` | qwen-vl-max 读答题卡表头 → 考试身份+学生+完整性 |
| `server/exam_match.py` | 检测元数据 → exam_slug + 校验 KB yaml |
| `server/parse_scores.py` | 班小二「学生成绩单」xlsx → scores.json |
| `server/auto_grade.py` | 无小分自动判分：选择题确定性 + 主观题**复用 Phase C grade**（同源不矛盾） |
| `server/pipeline_adapter.py` | run_report（子进程跑 build_report）/ report_json / paper_pdf |
| `server/db.py` | SQLite analyses 表索引 |

---

## 五、技能流水线集成（核心资产）

报告质量完全依赖三个已沉淀的 SKILL，必须正确接线：

| SKILL | 入口 | 产出 |
|---|---|---|
| exam-image → KB yaml | （离线，知识库建设） | `knowledge-base/mock-exams/<subj>/beijing/<slug>.yaml`：stem/answer/solution/score/knowledge_points/module |
| **answer-card-ocr** | `scripts/answer-card-ocr/detect.py:detect_card()` | `answer-card.json`：选择题 filled + 主观题 regionImage/handwritingText/**grade.missedPoints** |
| student-report | `scripts/student-report/build_report.py:build()` | 学生向 MD/PDF（失分题内嵌答题卡裁切原图） |

**接线铁律**（2026-05-18 修复的根因）：`detect_card()` 必须传
`subjective_qnums`（从 KB yaml 推非选择题号）+ `standard_yaml`（KB yaml 路径），
否则 Phase B/C 不触发，主观题无 `grade.missedPoints` → 报告错因 LLM 无事实输入 → 失真。

**判分一致性铁律**：`scores.json` 与报告引用的 `grade` 必须同源。auto 模式
不再二次判分，直接取 `answer-card.json` 里 Phase C 的 `grade.suggestedScore`
（学情报告 P0 红线：scores↔grade 一处矛盾 → 整份报告信任归零）。

### 凭据（不在源码，GitHub 推送保护脱敏）

| 服务 | 用途 | 来源 |
|---|---|---|
| 阿里云 DashScope | qwen-vl-ocr/vl-max/max | systemd `Environment=DASHSCOPE_API_KEY` |
| 腾讯云 OCR | Phase B 方框检测 | systemd `Environment=TENCENT_OCR_SECRET_ID/KEY`（**重部署必保留**） |
| 科大讯飞 | Phase B 手写 OCR | 仍硬编码 `xfyun_ocr.py DEFAULT_HW`（低敏，未脱敏） |

---

## 六、数据与目录

```
students/_web/<aid>/<exam_slug>/      # H5 上传（gitignore）
├── answer-card-photos/               # 原图 + cropped/qNN.png（Phase B）
├── answer-card.json                  # 选择 filled + 主观 regionImage/handwritingText/grade
├── scores.json                       # 每题 scored/fullScore
├── student.json                      # name/examId
└── .score_source                     # teacher | auto（报告 banner 用）

server/uploads/<aid>/scores.json      # 小分表解析落点（稳定位置）
server/data.sqlite3                   # analyses 任务索引
out/papers/<slug>.pdf                 # 试卷原卷拼图缓存
learning situation/<姓名>_<slug>_学情报告.{md,pdf}
```

报告 JSON（`/report`）：student_name / exam_title / total_scored / full_score /
rate / modules[] / wrong_questions[]（含 why_wrong/fix）/ **score_source**。

---

## 七、部署拓扑

- 阿里云 ECS 39.103.70.47，`/opt/zhongkao-agent`
- systemd `zhongkao` → uvicorn 127.0.0.1:8200（venv `.venv-server`）
- nginx → https://zhongkao.gatesby.xyz（Let's Encrypt，复用 443，零新端口）
- 前端 `web/dist` 由 FastAPI StaticFiles 挂 `/`，后端 `/api/*`
- google-chrome-stable + md-to-pdf skill（Linux 补丁）
- 更新：`git reset --hard origin/main && pip install -r server/requirements.txt && cd web && npm run build && systemctl restart zhongkao`（**勿动 systemd 三个 Environment 行**）

---

## 八、当前状态

✅ 已完成并上线：
- 全链路打通：上传 → 检测 → 确认 → Phase A/B/C → 判分 → 报告 → PDF
- 真实样本验证：贾小淇朝阳一模物理，11/11 主观题产 grade+regionImage；auto 判分主观 38/40 对齐真实班小二
- UI 6 项改版（首屏引导/确认改名/二选一判分/数据来源标签/stepper/PDF 内嵌预览/脱敏示意）
- 后端接入答题卡技能完整流水线 + auto 判分同源（2026-05-18 根因修复）

---

## 九、已知问题 & 待改进路线

### P0 待最终验收
- [ ] 真机从手机完整走一遍真实上传，确认报告非失真（检测/判分已逐段验证，build_report 技能侧同数据验证过，差真机端到端收口）

### P1 待改进
- [ ] `_ensure_scores` 硬等 25s：仅 teacher 模式需等，auto 模式应立即判分（前端 scoreMode 已知，可传给后端跳过等待）
- [ ] report.pdf 子进程写盘竞态：status=done 后头几秒 503，重试即得；应 mark_done 前确认 PDF 落盘
- [ ] 检测失败仅"重拍"一条路：可加"手动选考试"兜底（此前移除，体验生硬，需更好设计）
- [ ] Phase B 依赖腾讯云+讯飞外部 API：失败时主观题降级策略（当前记 0 待复核）需更明确的家长提示

### P2 体验/扩展
- [ ] 多场考试趋势对比（schemas/aggregate 已预留 history 维度）
- [ ] 报告内"错题再练"闭环（生成同类题）
- [ ] 非物理科目验证（数学/语文/英语/化学/道法 KB yaml 已建，端到端未逐科验证）
- [ ] 微信生态接入（对接 docs/product/PRD.md v5.0 服务号+小程序愿景）

### 技术债
- [ ] 源码脱敏后凭据全靠环境变量/硬编码混用，宜统一密钥管理
- [ ] auto_grade.py 残留未用常量（SR_DIR/ROOT）可清理
- [ ] git 仓库 loose objects 过多，需 `git prune`

---

## 十、关键文件索引

| 模块 | 路径 |
|---|---|
| 前端 SPA | `web/src/App.vue` / `web/src/api.ts` |
| 后端入口 | `server/main.py` |
| 后台任务 | `server/tasks.py` |
| 流水线适配 | `server/pipeline_adapter.py` |
| 答题卡技能 | `scripts/answer-card-ocr/detect.py`（+ tencent_split/xfyun_ocr/crop_subjective/subjective_grade） |
| 报告技能 | `scripts/student-report/build_report.py`（+ lib/schemas,aggregate,analyze） |
| 技能记忆 | `~/.claude/projects/.../memory/skill_student_answer_card_ocr.md`、`skill_student_learning_report.md` |
| 部署记忆 | `~/.claude/projects/.../memory/project_deploy_aliyun.md` |
