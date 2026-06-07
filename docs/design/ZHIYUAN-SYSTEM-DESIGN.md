# 中考志愿填报辅助系统 · 整体方案（基线 v1）

> 最后更新基线 commit：`9efcc034`（2026-06）。本文是后续演进的基准，改动较大时回来更新。
> 线上：https://zhongkao.gatesby.xyz/zhiyuan

---

## 1. 它是什么 / 给谁用

家长向的**北京中考志愿填报辅助**工具。首期聚焦**朝阳区**（作者孩子所在区）。
核心画像：朝阳区、京籍应届、二模区排约 4000–4500、初中=朝阳外国语学校。

**最高原则（不可妥协）**：涉及孩子升学，**绝不编造数据**；拿不到权威数据一律标"待核"，
不用猜测/预估/别校数据顶替。判定方法宁可**偏保守**也不误导。

---

## 2. 架构（B 档·同仓双服务）

志愿系统与"学情分析"系统**同仓、但运行时双服务解耦**（commit `6d6a1124` 拆分）：

| 服务 | 进程 | 端口 | 代码 | systemd |
|---|---|---|---|---|
| **志愿填报** | `server/zhiyuan_app.py` | 127.0.0.1:**8201** | + `scripts/admission/` | `zhiyuan.service` |
| 学情分析 | `server/main.py` | 127.0.0.1:8200 | + db/tasks/pipeline/OCR | `zhongkao.service` |

- **nginx**（`/etc/nginx/sites-available/zhongkao`）按路径分流：
  `/zhiyuan`、`/api/zhiyuan/` → :8201；`/assets/` 直接从磁盘 `web/dist/assets/` 提供（两页共用、不依赖任一后端）；其余 `/` → :8200。
- 志愿依赖很轻：`server/requirements-zhiyuan.txt`（fastapi/uvicorn/pyyaml），不含学情的 OCR/重依赖。
- **前端**：一次 `npm run build`（`web/`，Vite 多页）产出 `index.html`(学情) + `zhiyuan.html`(志愿)；
  `web/src/zhiyuan/` 与学情前端**零交叉引用**，仅共用 `styles/tokens.css`。
- 改志愿只重启 `zhiyuan`、改学情只重启 `zhongkao`，互不牵连。详见 `deploy/README-split.md`。

```
浏览器 ──nginx(443)──┬─ /zhiyuan, /api/zhiyuan/ ─→ :8201 zhiyuan_app.py ─→ scripts/admission/recommend.py
                     ├─ /assets/ ───────────────→ 磁盘 web/dist/assets/
                     └─ /, /api/analyses/ ──────→ :8200 main.py（学情）
```

---

## 3. 数据资产（`knowledge-base/admission/beijing/`）

所有数据带**信源分级 T1–T4**（见 `knowledge-base/admission/ADDRESS-VERIFICATION.md`）与置信度标注。

| 文件 | 内容 | 关键点 / 来源 |
|---|---|---|
| `chaoyang.yaml` | 27 所公办普高：名称/代码/地址/层次/历年线(score+rank)/特色/高考(民间) | 地址经 2025 官方简章印证 23/27 一致；高考标"民间·非官方" |
| `chaoyang_coords.json` | 公办校坐标(GCJ-02) + addr_confidence/geo_status | coarse/low 的标注清楚（北京中学门牌未公开等） |
| `chaoyang_addresses_audit.yaml` | 地址核查证据(T1–T4 逐源) | SOP 见 ADDRESS-VERIFICATION.md |
| `chaoyang_xeddx.yaml` | 校额到校 69 初中→12 优质高中名额 | **69/69 全已核**（合计列自检；14 行据中招大报纸 p57-58 补全） |
| `chaoyang_private.yaml`(+audit) | 19 民办/国际：性质/方向/课程/学费/in_minban/in_intl/坐标 | 学费多为升学平台口径、标参考；均在统招计划内 |
| `chaoyang_vocational.yaml` | 6 中职：类型/专业/地址/坐标/住宿 | |
| `beijing_guantong.yaml` | 全市贯通 27 项目/8 承办院校 + `school_coords` | 2026 起并入统一招生 |
| `2025_sjtongchou_chaoyang.json` | **市级统筹**朝阳可报清单（统筹一15+统筹二11） | 核心数据，见 §3.1 |

### 3.1 市级统筹数据（`2025_sjtongchou_chaoyang.json`）

来源：**《北京中招大报纸·2025 招生简章》官方原件**（`knowledge-original/zhiyuan/`，p32-35）
+ bjeea 网图 + 合计对账**三重印证**。每校字段：

- 基础：`name/campus/district/address/lat/lon/quota_chaoyang(投朝阳名额)/faces_chaoyang/boarding`
- 分数线（置信度分三档）：
  - `score_2025_tongzhao`：2025 统招线，**双源确认**（12 所）
  - `score_ref`：**历年参考**（单源/历史推算，9 所），UI 标"历年线"
  - 都没有 → "线待核"（5 所确无历史的新校：清华附将台路/八中京西/未来科学城/平谷两所）
- `score_lines`：历年线表（2025-510制 + 2024/2023-660制；严格区分本部/分校）
- 结构化：`level/style/tags/gaokao`（对齐普高；gaokao 均据实留空）
- 运行时附加：`dist`（按坐标算到家通勤，仅展示不筛选）

**重要事实**：统筹一里**朝阳本区校也给朝阳投名额**（八十中投朝阳5、陈经纶3）——
即朝阳考生**可经统筹报本区校**（已用官方原表逐格核实）。统筹三 2025 已取消。

---

## 4. 功能模块（前端 `web/src/zhiyuan/Zhiyuan.vue`，单组件）

**表单**：区排名 / 家庭住址 / 通勤方式 / 通勤上限 / **考生身份** / 住宿 / 板块。
缺省值 `user-defaults.ts`（⚠️ 当前为真人数据，对外发布前须脱敏）。

**Tab**（9 个）：志愿地图 / 普高清单 / 民办普高 / 国际学校 / 中职职教 / 贯通培养 / 校额到校 / 市级统筹 / 志愿草表。

**地图图层**（高德底图 GCJ-02）：公办普高(默认开) / 中外合作 / 民办 / 国际 / 中职(默认关) / 贯通-全市(默认关) / **市级统筹**(默认关) / **🎯校额到校**(默认关)。
- 普高=按冲/稳/保大 pin、够不上小图标；
- **市级统筹 & 校额到校**=按各自"研判"着色的大 pin、点击走右侧结构化详情（统一交互，见 §5）；
- 中职/贯通=点击也走右侧详情。

**志愿草表**：三批次 ①提前招生 ②指标分配(校额到校+市级统筹) ③统一招生(12×2专业)，可折叠、复制。

---

## 5. 核心方法学 / 判定逻辑（`recommend.py` + 前端）

### 5.1 统招/普高：冲稳保
`classify()`：`margin = (录取位次 − 学生区排) / 录取位次`。
保 ≥+0.15 / 稳 ≥0 / 冲 ≥−0.25(REACH_MARGIN) / 够不上 <−0.25。用**朝阳区排**（同区可比）。

### 5.2 身份资格（`eligibility_for`）
`identity`：jjyj(京籍应届)/feijing(非京籍)/wangjie(往届回京)。
- 普高统招：非京不可；指标分配(校额/统筹)：仅京籍应届；贯通：仅京籍；中职：都可。
- 各独立 Tab 顶部按资格显示横幅；后端 `eligibility` 字段随结果返回。

### 5.3 市级统筹研判（跨区 → 用**分数**，不用区排百分位）
- 关键洞见：中考全市同卷同分，**分数天然全市可比**；区排跨区不可比，
  "区排百分位"会因强/弱区差异误判郊区校（被否决的方案）。
- `est_score = rank_to_score(区排)`：用本区 27 校(区排,分)锚点插值出考生估中考分。
- `tcJudge`：`Δ = 估分 − 该校统招线`，套：
  **稳 Δ≥+10 / 冲 −10~+10 / 搏(有机会) −30~−10 / 够不上 <−30 / 线待核**。
- **为何放宽到 −30**：统筹实际线**官方不公开、但通常比统招线低（最多约20-30分）**，
  故用统招线判定**偏保守**——"搏"=靠统筹降分仍有机会(长线)，"够不上"才基本无望。
- 线优先 `score_2025_tongzhao`，缺则 `score_ref`(标"历年线"，可信度更低)。

### 5.4 校额到校研判（校内竞争 → 用**统招位次对比**）
- 校额到校是**校内竞争**(在本初中内按校排名录取)，无全区线。
- `xedJudgeByName`：高中统招位次 vs 孩子区排 →
  **值得冲**(ref≤rank×0.95，统招够不上、校额才是机会) / **相当** / **统招可达**(ref≥rank×1.1，统招本可上、占名额浪费)。
- 地图按此着色大 pin + 详情卡显示研判 + 该初中分到本校名额。

---

## 6. 设计原则（贯穿全栈）
1. **不编造**：拿不到→"待核"；新校无历史→如实"无"；高考无权威源→留空。
2. **信源分级 + 置信度可见**：T1（简章/计划册）> T2（学校官网）> T3（zhongkaobj 等）> T4（百科/地图）；UI 区分"双源确认线 / 历年线 / 待核"。
3. **判定偏保守**：宁可低估机会（统筹用统招线）也不误导家长冒进。
4. **诚实标注口径**：统招线≠统筹线、统筹线不公开、估分为插值近似、坐标 coarse/借址等都在界面注明。
5. **本部/分校严格区分**：人大附本部≠通州校区、和平街两校区等，数据合并时显式映射防串味（踩过坑）。

---

## 7. 部署 / 运维
- 常规改动流程：本地改 → `npm run build` 验证 → 提交**指定文件**(不 `git add -A`) → 推 main
  → ECS `git merge --ff-only` → `cd web && npm run build` → 视情况 `systemctl restart zhiyuan`。
- **纯前端改动**：ECS 拉取+构建即可，无需重启（nginx /assets 直出 + zhiyuan_app 每次读 dist）。
- **改了 json/recommend.py**：需 `systemctl restart zhiyuan`（清统筹缓存/重载逻辑）。
- 学情服务(zhongkao)**不要动**；nginx 改动有备份 `zhongkao.bak.split`。
- push 直推 main（不开 PR）；直连失败走代理 `http://127.0.0.1:7890`。

---

## 8. 已知边界 / 数据缺口（演进时认清）
- **统筹实际录取线官方不公开** → 永远只能用统招线近似（偏保守）。
- **5 所新校"线待核"**（清华附将台路28名额、央民大附等热门也在内）：无历史，换方法解决不了，须查《简章》朝外分配名额 + 问初中部。
- **高考数据全留空**（京内名校官方不公布升学率/北清数）。
- **est_score 是插值近似**；统筹/校额研判都是"参考"，非承诺。
- 数据时效=**2025 口径**；2026 计划发布后须整体刷新。

---

## 9. 演进 backlog（按优先级，待定）
- [ ] **上线前脱敏**：`user-defaults.ts` 真人数据(rank/小区/朝外)→占位；做成构建期检查。
- [ ] **其他区扩展**：当前 `district` 写死 chaoyang；数据/逻辑已大体参数化，扩区需补该区数据集 + 一分一段锚点。
- [ ] 统筹"线待核"的新校：待官方/初中数据出来回填 `score_ref`。
- [ ] 贯通/中职是否需要研判着色（目前仅展示，未做冲稳保——它们门槛低、对边缘生意义不同）。
- [ ] 民办/国际：录取分(自主招生无公开线)、是否引入校测口径。
- [ ] 2026 官方计划发布后：统招代码/校额/统筹/贯通全量刷新。
- [ ] （学情侧，不属本系统）`server/main.py` 有一段未提交的 manual-choices WIP。

---

## 10. 关键文件索引
- 后端：`server/zhiyuan_app.py`、`scripts/admission/recommend.py`（build_result/各 load_*/judge）、`scripts/admission/distance.py`（高德路网/多校区/缓存）
- 前端：`web/src/zhiyuan/Zhiyuan.vue`（单组件）、`user-defaults.ts`、`main.ts`
- 数据：见 §3
- 部署：`deploy/README-split.md`、`deploy/zhiyuan.service`
- 规范：`knowledge-base/admission/ADDRESS-VERIFICATION.md`（地址核查 SOP）
