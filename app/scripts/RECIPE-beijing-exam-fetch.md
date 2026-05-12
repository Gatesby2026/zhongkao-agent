# 北京中考一模/二模 试卷检索方法

> 实战方法记录 · 2026-05-09 朝阳一模检索  
> 用于复用：每年 4 月（一模）/ 5 月（二模）/ 中考真题发布时重做

## 一句话

**北京高考在线（gaokzx.com）** 是目前唯一已验证、**无需会员/付费/CAPTCHA** 的批量来源。
其他 4 大题库站（课外100、鲸题优、21cnjy、教习网）调研后发现**都需要会员**。

## 调研结果速查（2026-05 时点）

| 来源 | 状态 | 备注 |
|------|------|------|
| **gaokzx.com** | ✅ **公开 + 无门槛** | 试卷以图片嵌 HTML，CDN 直链可下 |
| kewai100.com（课外100） | ⛔ 会员限定 | "家长/学生-初三"会员才能下载 |
| jingtiyou.cn（鲸题优） | ⛔ 会员限定 | — |
| zy.21cnjy.com（21世纪教育网） | ⛔ 付费 | — |
| 51jiaoxi.com（教习网） | ⚠️ VIP + 滑块 | 需人工滑滑块绕 WAF，详见 Codex `~/.openclaw/workspace/memory/2026-04-11.md` |

调研脚本：`paper-scout.js`（已 commit），跑完写入 `<集合>-target.json`。

## 实战流程：从零开始拿到一套朝阳一模 5 科试卷

### 第 1 步 - 定位汇总页

打开 gaokzx.com 的"一模二模"频道，找当前年份的"北京各区初三一模试题及答案汇总"。
2026 年的汇总页 URL：`https://www.gaokzx.com/gk/zhongkao/154???.html` 这一系列。

汇总页结构 = 大表格，每行一个区，每列一个科目，单元格里是该区该科目的详情页链接。

实操中可以**直接保存这一页的整个 HTML**（`summary.html`，已存 ~290KB），后续脚本从里面 grep 详情页 URL。

### 第 2 步 - 识别 5 科详情页 URL

各区各科目对应一个详情页。朝阳 2026 一模的 5 个 URL 已验证：

| 科目 | URL |
|------|-----|
| 语文 | https://www.gaokzx.com/gk/zhongkao/154679.html |
| 数学 | https://www.gaokzx.com/gk/zhongkao/154691.html |
| 物理 | https://www.gaokzx.com/gk/zhongkao/154733.html |
| 英语 | https://www.gaokzx.com/gk/zhongkao/154734.html |
| 道法 | https://www.gaokzx.com/gk/zhongkao/154809.html |

存到 `manifest.json` 的 `pages` 字段，作为复现起点。

### 第 3 步 - 抓详情页 HTML

详情页是普通 HTML，直接 `curl -A "Mozilla/5.0" -o <科目>.html <URL>` 即可。**不需要 cookie、不需要登录、不需要绕 WAF**。

详情页里：
- 试卷正文 **以图片形式嵌入**（不是 PDF，也不是文字）
- 图片托管在 `cdn.gaokzx.com/zixunzhan/*.png`
- 每个 png 一页，10-14 页不等
- URL 包含**完整中文文件名**（`026北京朝阳初三一模物理_0428144903_01...png`），URL-encoded

### 第 4 步 - 从 HTML 提取图片 URL

```bash
# 简单 grep
grep -oE 'https://cdn\.gaokzx\.com/zixunzhan/[^"]+\.png' physics.html > physics.urls
```

或用 Python BeautifulSoup 解析 `<img src="...">`，更鲁棒。

### 第 5 步 - 批量下载

```bash
mkdir -p physics-images
i=1
while read url; do
  curl -s -o "physics-images/page-$(printf '%02d' $i).png" "$url"
  i=$((i+1))
done < physics.urls
```

### 第 6 步 - 写 manifest

`manifest.json` 记录：
- 每科目的源 URL（gaokzx 详情页）
- 每个 page-NN.png 的相对路径
- generatedAt 时间戳
- source 标注（"北京高考在线公开页面"）

这一步看似冗余，但**下次重做 / 排查问题时**就靠它对账。

### 第 7 步 - OCR + 结构化

见 [`README-exam-ocr.md`](README-exam-ocr.md)。

简单说：每科目跑 `cloud-ocr-exam.py`（Qwen + Aliyun Education OCR + Cut 三引擎），
然后 `structure-exam-cloud.py` + `structure-exam-final.py` 融合输出到 `processed/<科目>/structured-cloud/final.{md,json}`。

朝阳 2026 一模 5 科已验证 OCR 质量：
- 语文 27/27、数学 28/28、物理 26/26、英语 38/38、道法 25/25。

## gaokzx 的局限（提前知道避免重做时踩坑）

1. **覆盖范围**：gaokzx 只整理"重点区/重点学校"。2026 年的汇总页上：
   - 海淀、西城、东城、朝阳、丰台、石景山、顺义、北师大实验中学、二中、四中、人朝分校、北师大附中、人大附中、陈经纶、汇文、东直门、三十五中  
   - 有的区某些科目（如化学/历史）缺答案，标 `—— 适应性试题丨答案`
2. **更新时差**：考完一周到两周才更新完毕，刚考完 1-2 天去找可能只有部分科目。
3. **CDN 短链可能过期**：URL 里有时间戳（`_1777359811727_...`），未来某天可能 404，**抓完立刻本地保存**。
4. **每页一张图，文字不可选**：必须走 OCR，不能直接复制文字。

## 已验证产出（chaoyang-2026-yimo）

服务器路径：`/opt/zhongkao-agent/app/data/chaoyang-2026-yimo/`（已 gitignore，~35 MB tar.gz 备份）

```
chaoyang-2026-yimo/
├── manifest.json              # 5 个源 URL + 文件清单
├── summary.html               # gaokzx 汇总页 HTML（备份）
├── <科目>.html                # 5 份详情页 HTML 备份
├── <科目>.urls                # 5 份图片 URL 清单
├── <科目>-images/             # page-NN.{png|jpg}
└── processed/
    ├── <科目>/
    │   ├── pages/             # 每页 OCR 文本
    │   ├── cloud-ocr/         # 三引擎原始结果
    │   ├── structured-cloud/
    │   │   ├── final.md       # ⭐ 干净的题目 + 答案 Markdown
    │   │   ├── final.json     # 结构化（含题型、选项、分值）
    │   │   └── validation-report.json
    │   ├── questions.draft.json
    │   └── raw.txt
    └── structured-cloud-index.json   # 全集统计
```

## 下次复用清单

二模来时（5 月底），按这个流程复用：

```bash
# 1. 找汇总页（手工，在 gaokzx 一模二模频道）
# 2. 从汇总页 HTML 提取 5/9 个区的 5 科目详情页 URL
# 3. 跑：
node app/scripts/paper-scout.js --target gaokzx --district chaoyang --exam ermo
# （需扩展 paper-scout.js 加 gaokzx adapter）

# 4. 抓 HTML + 抽图片 URL + 下载
# 5. 跑 OCR pipeline（见 README-exam-ocr.md）
```

⚠️ **paper-scout.js 当前还没有 gaokzx adapter**，朝阳一模这次是混合手工 + 临时脚本完成的。
下次复用前，建议把 gaokzx 适配器加进 paper-scout 让流程自动化。

## 关联文档

- [`README-paper-scout.md`](README-paper-scout.md) — paper-scout 通用工具说明
- [`README-exam-ocr.md`](README-exam-ocr.md) — OCR 流水线最佳实践
- [`README-answer-card-ocr.md`](README-answer-card-ocr.md) — 学生答题卡识别
- [`build-student-analysis-report.py`](build-student-analysis-report.py) — 用 final.md + 答题卡生成学情报告
