#!/bin/bash
# run_with_audit.sh — image OCR 路线统一闭环
#
# 跑 OCR pipeline → enrich → inspect → 启 Claude 大模型审核子 agent
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
#
# 输出：
#   - knowledge-base/exams/_staging/<subject>/2026-<region>-<type>/structured-cloud/final.json
#   - knowledge-base/exams/mock/<subject>/beijing/2026-<region>-<type>.yaml
#   - 自动启 Claude R1 审核子 agent（出 patch 建议报告）
#
# 依赖环境变量：
#   TENCENT_OCR_SECRET_ID / TENCENT_OCR_SECRET_KEY  腾讯云 OCR
#   DASHSCOPE_API_KEY                              阿里云百炼 (enrich + qwen-vl)

set -e
REGION=${1:?用法: $0 <region> <subject> [type=er]}
SUBJECT=${2:?用法: $0 <region> <subject> [type=er]}
TYPE=${3:-er}

[ -z "$TENCENT_OCR_SECRET_ID" ] && {
    echo "❌ 缺 TENCENT_OCR_SECRET_ID 环境变量"; exit 1; }
[ -z "$DASHSCOPE_API_KEY" ] && {
    echo "❌ 缺 DASHSCOPE_API_KEY 环境变量"; exit 1; }

# 学科 → 脚本映射
case "$SUBJECT" in
    chinese)  SCRIPT="scripts/exam-ocr/chinese_image_paper.py" ;;
    physics)  SCRIPT="scripts/exam-ocr/tencent_paper.py" ;;
    politics) SCRIPT="scripts/exam-ocr/politics_image_paper.py" ;;
    *) echo "❌ 不支持 subject=$SUBJECT (仅 chinese/physics/politics)"; exit 1 ;;
esac

# type → 目录映射
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
INSPECT="scripts/exam-docx/${SUBJECT}_inspect.py"
if [ -f "$INSPECT" ]; then
    python3 "$INSPECT" "$YAML" -v || true
else
    echo "(skip: $INSPECT not found)"
fi

# Step 4: Claude 大模型审核（启子 agent 但提示在 SDK 层手工执行）
echo ""
echo "=== ✅ pipeline 完成 ==="
echo ""
echo "🤖 下一步：启 Claude R1 审核（推荐复制以下 prompt 给 Agent tool）："
cat <<PROMPT

────────── 复制以下到 Agent 工具（subagent_type=general-purpose） ──────────
审核 2026 北京${REGION}区${SUBJECT}**${TYPE}模** yaml：
\`${YAML}\`

源 PDF：\`${SRC}/../source.pdf\` 或 \`knowledge-original/gaokzx-downloads/...\`
源 PNG：\`${SRC}/images/page-NN.png\`
${SUBJECT} OCR 路线（image OCR + dual-OCR + 5 层 fallback），**有 OCR 误差风险**。
拼音/故意错字/错别字辨析题 **严禁标记为 bug**（题目设计本身）。

审核重点：
1. 题数 / 总分匹配卷面规范
2. 题号连续无缺失 / 无错位融合（如 Q12 吞 Q13）
3. options OCR 漏读最后选项
4. 答案 / sol 完整性
5. 题型分类合理
6. 水印残留 (gaokzx / 京考一点通 / 学科网 等)
7. KP 跨学科污染

输出格式：
\`\`\`
Q{n} | P{0/1/2} | 诊断（含源 PDF 核对结论） | 建议 patch (_patches/${SUBJECT}/${SLUG}.yaml 格式)
\`\`\`
末行 OVERALL: CLEAN / MINOR / NEEDS_FIX。300 字内。
────────────────────────────────────────────────────────────────
PROMPT
