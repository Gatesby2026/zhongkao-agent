#!/bin/bash
# run_with_audit.sh — image OCR 路线统一闭环
#
# 跑 OCR pipeline → enrich → inspect → 输出"深度审核 prompt" 模板
# (用户在 Claude Code 内说"审核 <yaml>" 即可触发 Agent() 自动启子 agent)
#
# 用法：
#   ./run_with_audit.sh <region> <subject> [type]
#   region   chaoyang/xicheng/pinggu/...
#   subject  chinese/physics/politics (image OCR 路线 3 学科)
#   type     er/yi/san（默认 er 二模）
#
# 示例：
#   ./run_with_audit.sh pinggu chinese
#   ./run_with_audit.sh chaoyang physics er
#   ./run_with_audit.sh xicheng politics

set -e
REGION=${1:?用法: $0 <region> <subject> [type=er]}
SUBJECT=${2:?用法: $0 <region> <subject> [type=er]}
TYPE=${3:-er}

[ -z "$TENCENT_OCR_SECRET_ID" ] && { echo "❌ 缺 TENCENT_OCR_SECRET_ID 环境变量"; exit 1; }
[ -z "$DASHSCOPE_API_KEY" ]    && { echo "❌ 缺 DASHSCOPE_API_KEY 环境变量"; exit 1; }

case "$SUBJECT" in
    chinese)  SCRIPT="scripts/exam-ocr/chinese_image_paper.py" ;;
    physics)  SCRIPT="scripts/exam-ocr/physics_image_paper.py" ;;
    politics) SCRIPT="scripts/exam-ocr/politics_image_paper.py" ;;
    *) echo "❌ 不支持 subject=$SUBJECT (仅 chinese/physics/politics)"; exit 1 ;;
esac

case "$TYPE" in
    yi)  DIR="yimo" ;;
    er)  DIR="ermo" ;;
    san) DIR="sanmo" ;;
    *) echo "❌ 不支持 type=$TYPE (仅 yi/er/san)"; exit 1 ;;
esac

ROOT="/Users/jiakui/projects/zhongkao-agent"
cd "$ROOT"

SRC="knowledge-original/beijing-mock-2026/${DIR}/${REGION}/${SUBJECT}"
SLUG="2026-${REGION}-${TYPE}"
FJ="knowledge-base/exams/_staging/${SUBJECT}/${SLUG}/structured-cloud/final.json"
YAML="knowledge-base/exams/mock/${SUBJECT}/beijing/${SLUG}.yaml"
PATCHFILE="knowledge-base/exams/_patches/${SUBJECT}/${SLUG}.yaml"
PDFCAND="knowledge-original/gaokzx-downloads/2026-${DIR/mo/mu}-${SUBJECT}/${REGION}_${SUBJECT}.pdf"

[ ! -d "$SRC/images" ] && { echo "❌ 源图缺: $SRC/images/"; exit 1; }

echo "=== [${REGION}_${SUBJECT}_${TYPE}] $(date) ==="

# Step 1: OCR + parse
echo "--- Step 1: OCR + parse ($SCRIPT) ---"
T0=$(date +%s)
python3 "$SCRIPT" "$SRC" --subject "$SUBJECT"
[ ! -f "$FJ" ] && { echo "❌ MISSING final.json"; exit 1; }

# Step 2: enrich
echo "--- Step 2: enrich → yaml ---"
rm -rf "scripts/knowledge-base/.cache/${SUBJECT}-${SLUG}"* 2>/dev/null
python3 scripts/knowledge-base/enrich_to_mock_exam.py --input "$FJ" --output "$YAML"
T1=$(date +%s)
echo "[${REGION}_${SUBJECT}_${TYPE}] OCR+enrich done $((T1-T0))s"

# Step 3: inspect
echo "--- Step 3: inspect ---"
INSPECT="scripts/exam-inspect/${SUBJECT}_inspect.py"
[ -f "$INSPECT" ] && python3 "$INSPECT" "$YAML" -v || echo "(skip: $INSPECT not found)"

# Step 4: 输出深度审核 prompt
echo ""
echo "=== ✅ pipeline 完成 ==="
echo ""
echo "🤖 R1 审核（在 Claude Code 内对我说："
echo "      \"审核 ${YAML}\""
echo "   我会自动 Agent() 启子 agent，无需 paste prompt）"
echo ""
echo "如需自行 paste，下面是完整 prompt："
cat <<PROMPT

────────── 深度审核 prompt（subagent_type=general-purpose） ──────────
任务：**逐题**审核 2026 北京${REGION}区${SUBJECT}**${TYPE}模** yaml，挖 P0+P1+P2 全部问题。

文件：
- yaml: \`${YAML}\`
- patches（若存在）: \`${PATCHFILE}\`
- 源 PDF: \`${PDFCAND}\`
- 源 PNG（OCR 输入）: \`${SRC}/images/page-NN.png\`
- OCR 中间产物: \`knowledge-base/exams/_staging/${SUBJECT}/${SLUG}/tencent-cache/general/page-NN.txt\`

**重要前提**：image OCR 路线（${SUBJECT}_image_paper.py + 5 层 fallback），
有 OCR 误差风险。**严禁标记为 bug 的"题目设计本身"**：
- 拼音注音 (zhù) / 故意错字 / 错别字辨析题（语文）
- 干扰项语义偏离（出题人设计）
- 西城选择题 3 选项（西城卷面真就 3 选项设计，inspect false positive）
- 名著作文 answer 字段空（作文/主观题正常）

**审核步骤（必做）**：
1. **核对题数 + 总分**：用 \`python3 -c "import fitz; doc = fitz.open('${PDFCAND}'); ...\` 抽源 PDF 全部 (N分) 标记，对比 yaml 找差异
2. **逐题过 stem**：用 Read 工具看 yaml 全部题，检查每题 stem 完整 + 无水印 + 无题号融合（如 Q12 stem 末尾粘 Q13 内容）
3. **逐题过 options**：选择题 4 选项齐全（除西城 3 选项设计），无吞下一段 passage 文字
4. **逐题过 answer/solution**：答案与题号对位、solution 非空（作文除外）、无文字损坏（"挂安慰"之类 OCR artifact）
5. **逐题过 KP**：知识点合理且无跨学科污染（不应含力学/化学方程式/历史朝代等）
6. **type 字段**：单选/判断/材料分析/默写/名著/现代文 等是否合理（如物理 Q24 标"作文"是误判）
7. **passage（语文专属）**：6-9 篇，q_range 正确，无"第二篇 passage 文字粘 Q23 stem 末"

**输出格式**（无字数限制，要详尽）：
\`\`\`
## 卷面元数据
- 题数 / 总分 / 时长 / 类型分布
- 与卷面规范差异（如有）

## 逐题问题清单
| Q | 严重 | 维度 | 诊断 | 建议 patch |
|---|---|---|---|---|
| Q1 | P0 | stem | OCR 漏读第二行，应是"..."（核对 page-02.png） | stem: "..." |
| Q5 | P1 | options | D 选项被吞下一段 passage 文字（177 字应 4 字） | options.D: "..." |
| ... |

## 跨题模式（如有）
- "水印 X 漏过 NOISE_LINE 黑名单"等可推父级 parser 加规则的发现

## OVERALL: CLEAN / MINOR / NEEDS_FIX
- 总评 + 关键 P0 数量
\`\`\`

输出可写到 \`knowledge-base/exams/_audits/${SLUG}-R1.md\`（如有 _audits 目录）。
────────────────────────────────────────────────────────────────
PROMPT

echo ""
echo "📋 patch 应用流程："
echo "   1. 把审核报告里的 patches 整理到 ${PATCHFILE}"
echo "   2. 重跑 \`$0 ${REGION} ${SUBJECT} ${TYPE}\` (patch 自动应用 + inspect)"
echo "   3. 跑 R2 复审验证收敛: 对我说 \"R2 审核 ${YAML}\""
