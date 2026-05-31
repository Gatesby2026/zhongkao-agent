# test-data — 学情分析回归测试集

每个目录 = 一份学生答题卡测试 case。

## 目录命名规范 🔒

**`<拼音>-<区>-<场次>-<学科>`**（对齐 `exam_slug` 后缀）

- 拼音：学生姓名小写拼音（如 `guanlihan`、`jiaxiaoqi`）。脱敏卡用 `tuominde`
- 区：`haidian` / `chaoyang` / `xicheng` / `shijingshan` / `dongcheng` / ...
- 场次：`yi`（一模）/ `er`（二模）/ `zhenti`（中考真题）
- 学科：`math` / `physics` / `chinese` / `english` / `politics` / `chemistry` / `history`

例：
- `guanlihan-haidian-er-physics` = 关丽涵 · 海淀二模 · 物理
- `jiaxiaoqi-chaoyang-yi-math` = 贾小淇 · 朝阳一模 · 数学

每个 case 内容：

```
<case>/
├── README.md            # 学生 + 试卷 + 来源说明
├── page-01.jpg          # 答题卡照片（imgnorm 处理后，2250×3000）
├── ...                  # 通常 4 张，多页扫描可能 5-8 张
├── page-NN.jpg
└── *.xlsx               # 可选：老师小分表（teacher_xlsx 场景需要）
```

跑测：

```bash
# 跑指定 case
CASES=<case-name> SCENARIOS=auto python3 scripts/test/e2e_audit.py

# 跑全部
python3 scripts/test/e2e_audit.py

# 多 case 并行（注意：阿里云 ECS 内存有限，并发 >2 易 OOM）
CASES=<case1>,<case2> SCENARIOS=auto python3 scripts/test/e2e_audit.py
```

输出在 `test-data/_runs/<timestamp>/<case>/<scenario>/` —— 含 detect.json、report.json、report.pdf、audit.json。

---

## 当前 case 清单

### 开发基线（贾小淇，多科目深度测试）

| Case | 学生 | 试卷 | 备注 |
|------|------|------|------|
| `jiaxiaoqi-chaoyang-yi-physics` | 贾小淇 | 朝阳一模 物理 | 缺字母法 baseline 59-60/70 |
| `jiaxiaoqi-chaoyang-yi-math` | 贾小淇 | 朝阳一模 数学 | |
| `jiaxiaoqi-chaoyang-yi-chinese` | 贾小淇 | 朝阳一模 语文 | |
| `jiaxiaoqi-chaoyang-er-physics` | 贾小淇 | 朝阳二模 物理 | |
| `jiaxiaoqi-chaoyang-er-math` | 贾小淇 | 朝阳二模 数学 | |
| `jiaxiaoqi-chaoyang-er-chinese` | 贾小淇 | 朝阳二模 语文 | |
| `jiaxiaoqi-chaoyang-er-english` | 贾小淇 | 朝阳二模 英语 | |
| `jiaxiaoqi-chaoyang-er-politics` | 贾小淇 | 朝阳二模 道法 | |

### 生产真实 case（从 https://zhongkao.gatesby.xyz 拉取）

| Case | 学生 | 试卷 | 来源 aid | 用途 |
|------|------|------|---------|------|
| `guanlihan-haidian-er-physics` | 关丽涵 | 2026 海淀二模 物理 | `9cf5379f8880` | **Path B 标准回归**（57/70，选择题 15/15） |
| `zhangjingqi-haidian-er-physics` | 张靖奇 | 2026 海淀二模 物理 | `5c2eb2b03cd3` | 海淀方括号 同区不同学生 |
| `zhangyiran-shijingshan-yi-chinese` | 张伊冉 | 2026 石景山一模 语文 | `341037ff62d3` | 跨区 + 跨学科（语文） |
| `tuominde-chaoyang-yi-physics` | 脱敏的 | 2026 朝阳一模 物理 | `9ccb20332f23` | 学生名脱敏的真实卡 |

### 2026-05-31 新增（4 个数学卷，多页扫描）

| Case | 学生 | 试卷 | 来源 aid | 照片 |
|------|------|------|---------|------|
| `shixinran-xicheng-yi-math` | 史欣然 | 2026 西城一模 数学 | `abfb5885bad6` | 8 张 |
| `zhangyizhang-haidian-er-math` | 张益彰 | 2026 海淀二模 数学 | `ad6e683c21c9` | 8 张 |
| `fangshiyao-xicheng-yi-math` | 房诗尧 | 2026 西城一模 数学 | `ff9c14cf1e37` | 5 张 |
| `shenyueran-haidian-er-math` | 沈跃然 | 2026 海淀二模 数学 | `5cc9fc718753` | 4 张 |

### 已 skipped（数据不全或重复）

- 李小琪 朝阳一模物理 — 服务器照片丢失（aid `6c0f4d1f8e7e` 文件夹空）
- 尹凯程 通州一模物理 — 仅 2 张照片（不完整）
- YKC 通州一模数学 — 仅 2 张照片
- 关雨涵 海淀二模物理 — 是关丽涵 OCR 误识，跟现有 case 重
- 贾小棋 朝阳一模物理 — 同上，是贾小淇 OCR 误识
- 考生 朝阳二模物理（2026-05-31）— 学生名是默认占位
- 沈跃然 海淀二模英语（2026-05-31）— 仅 2 张照片

---

## 数据隐私

- 所有 jpg 已经过 imgnorm 处理（去 EXIF + 缩放 ≤3000px）
- 真实学生姓名保留，但仅本机/git private 仓库使用，不外传
- "脱敏的" 这个 case 是用户主动脱敏过的名字
- `.gitignore` 默认排除 `test-data/_runs/`（每次跑产生的临时输出）

---

## 回归门控规则

修改 `detect.py` / `pipeline_adapter.py` / `build_report.py` 后，**至少必须跑通**：

1. `guanlihan-haidian-er-physics` — Path B 海淀代表
2. `jiaxiaoqi-chaoyang-yi-physics` — 缺字母法 朝阳代表

两个分数 ±2 才能合并到 main。

完整回归再加 3 个生产 case：

3. `zhangjingqi-haidian-er-physics`
4. `zhangyiran-shijingshan-yi-chinese`（跨学科）
5. `tuominde-chaoyang-yi-physics`

数学多页扫描验证（5-8 张）：

6. `shixinran-xicheng-yi-math`
7. `zhangyizhang-haidian-er-math`

---

## 维护

新增生产 case：

```bash
# 1. 在服务器查 aid
ssh root@39.103.70.47
sqlite3 /opt/zhongkao-agent/server/data.sqlite3 \
  "SELECT id, student_name, exam_slug FROM analyses WHERE status='done' ORDER BY created_at DESC LIMIT 20"

# 2. 拉取照片到本机（命名 <拼音>-<区>-<场次>-<学科>）
sshpass -p '...' scp 'root@39.103.70.47:/opt/zhongkao-agent/students/_web/<aid>/<slug>/answer-card-photos/page-*.jpg' \
  test-data/<new-case-name>/

# 3. 写 case README + 加入 e2e_audit.py 的 PER_CASE_NAME map
```
