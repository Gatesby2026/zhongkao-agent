# Answer Card OCR Notes

This note records the answer-card recognition plan for handwritten student answer cards.

## Current Inputs

- `knowledge-original/初三一模-数学`
  - 8 HEIC phone photos.
  - `数学一模小分.xlsx`.
- `knowledge-original/初三一模-语文`
  - 4 HEIC phone photos.
  - `一模。语文。小分.xlsx`.

The sample is one student's answer card and score breakdown. The photos are high resolution, but they include perspective skew, page curvature, shadows, and EXIF orientation metadata.

## Recommended Production Pipeline

1. Convert HEIC to normalized PNG/JPG and apply EXIF orientation.
2. Detect answer-card anchors:
   - black registration blocks
   - page border lines
   - QR/barcode area
3. Deskew and perspective-correct each page into a canonical template coordinate system.
4. Segment by subject-specific answer-card template:
   - identity region
   - objective-choice bubbles
   - fill-in blanks
   - solution-writing regions
   - essay/long-response regions
5. Use task-specific recognition:
   - choice bubbles: local image blackness detection, not OCR
   - student identity: QR/barcode first, OCR second
   - math blanks: handwriting OCR with formula normalization to LaTeX
   - math solutions: crop-level multimodal OCR, preserving reasoning steps
   - Chinese answers: crop-level handwriting OCR plus low-confidence marking
6. Cross-check every extracted answer with the score spreadsheet.
7. Store low-confidence items with crop images for manual review.

## Important Lesson From The POC

Fixed pixel coordinates are not enough for phone photos. Even with the same answer-card template, skew and page curvature shift the choice boxes enough to break blackness detection. The next implementation must normalize the image by anchors before applying fixed template ROIs.

## Alibaba Cloud Capability Check

Available through the current Alibaba Cloud CLI:

- `ocr-api recognize-handwriting`
  - Official handwriting OCR.
  - Supports Chinese, English, and numeric handwriting.
  - Supports image URL input.
  - CLI advertises `--body-file`, but the current plugin returned `imageUrlOrBodyEmpty` when tested with local binary files, so URL input is the reliable path.
- `ocr-api recognize-all-text --type Advanced`
  - General high-accuracy OCR.
  - Can enable handwriting table/paragraph/character options.
- `ocr-api recognize-document-structure`
  - Layout/document structure OCR.
  - Useful for page layout, less targeted at handwritten answer extraction.
- Education APIs such as `recognize-edu-paper-ocr`, `recognize-edu-paper-cut`, and `recognize-edu-paper-structed`
  - Strong for printed exam papers and question segmentation.
  - Not sufficient alone for student answer-card handwriting.

Alibaba Cloud Marketplace has answer-card subjective-question recognition products, but these are not exposed as the current `aliyun marketplace` CLI product. They likely require separate marketplace purchase/authorization and product-specific API invocation.

Test result:

- OSS is now available. The tested path is:
  - create a temporary private bucket
  - upload crop images
  - generate short-lived signed URLs
  - invoke `recognize-handwriting`
  - delete objects and bucket
- A reusable wrapper exists at `aliyun-handwriting-ocr.py`.
- The API calls succeeded, but the current crop quality is still poor, so OCR recognized surrounding printed labels instead of the intended handwritten answer.
- Conclusion: cloud handwriting OCR is available, but crop normalization must be fixed before OCR quality can be fairly evaluated.

## DashScope Qwen OCR Test

Alibaba Cloud Model Studio provides `qwen-vl-ocr-latest` through the OpenAI-compatible chat completions endpoint. A reusable test wrapper now exists:

- `qwen-answer-card-ocr.py`

The wrapper:

- uploads local answer-card images to a temporary private OSS bucket
- signs short-lived image URLs
- calls DashScope `qwen-vl-ocr-latest`
- prompts the model to return structured answer-card JSON
- saves raw response, text response, parsed JSON, and a manifest
- deletes the temporary OSS bucket unless `--keep-bucket` is set

Test inputs:

- `data/answer-card-poc/math/qwen-answer-card-inputs/math-page1-fill-band-q09-q16.jpg`
- `data/answer-card-poc/math/qwen-answer-card-inputs/math-page1-choice-fill-band.jpg`
- `data/answer-card-poc/math/qwen-answer-card-inputs/math-page1-solution-band-q17-q18.jpg`
- tight crops from `data/answer-card-poc/math/crops/fill-answer/`

Observed results:

- For the coarse fill-in band covering questions 9-16, Qwen OCR correctly extracted:
  - 9: `x>=1`
  - 10: `3(a+b)^2`
  - 11: `x=3`
  - 12: `x=1, y=-10`
  - 13: `13000`
  - 14: `340`
  - 15: `1.5`
  - 16-(2): `4`
- Question 16-(1) was read as `9 3` or `3` depending on context. The original handwriting is heavily overwritten, so it should be routed to manual review.
- Tight single-question crops for 9, 10, 11 were all correctly recognized by Qwen OCR.
- A larger choice+fill band still extracted fill-in answers well, but failed on choice questions: it treated visible printed option letters as answers (`BCD`, `ABC`, etc.). Choice questions should continue using deterministic filled-bubble detection, not large-model OCR.
- The solution band for questions 17-18 was read well enough to preserve solution steps and final answers:
  - 17 final answer: `sqrt(3)`
  - 18 final interval: `2<x<4`

Updated production direction:

1. Do not pursue pixel-perfect per-blank crop as the main production path.
2. Normalize/deskew each answer-card page using anchors.
3. Crop stable large semantic regions:
   - choice region
   - fill-in region
   - solution-writing regions
   - essay/long-answer regions
4. Use deterministic image processing for choice bubbles.
5. Use Qwen OCR on fill-in and solution regions, with a strict JSON schema prompt.
6. Use per-question tight crop only as a fallback when the large-region result is missing or conflicts with scoring expectations.
7. Route overwritten, low-confidence, or conflicting answers to manual review.

## Full Math And Chinese Answer-Card Run

Full-page normalized inputs were generated under:

- `data/answer-card-poc/math/qwen-full-page-inputs/`
- `data/answer-card-poc/chinese/qwen-full-page-inputs/`

Qwen OCR outputs:

- `data/answer-card-poc/math/qwen-full-page-test/`
- `data/answer-card-poc/chinese/qwen-full-page-test/`

Best-current combined structured outputs:

- `data/answer-card-poc/combined-structured/math-best-current.json`
- `data/answer-card-poc/combined-structured/math-best-current.md`
- `data/answer-card-poc/combined-structured/chinese-best-current.json`
- `data/answer-card-poc/combined-structured/chinese-best-current.md`

Math result:

- Choices 1-8 are still best handled by deterministic bubble detection.
- Fill-in questions 9-16 are best handled by the Qwen fill-band crop. It extracted 9-15 and 16-(2) well. Question 16-(1) is overwritten and should be reviewed.
- Questions 17-18 from a solution-band crop were extracted well enough for downstream analysis.
- Full-page OCR covered later solution pages, but long geometry/algebra questions still need review. It sometimes:
  - includes printed question text in the answer field
  - puts a visible answer into `unassigned_handwriting`
  - misreads dense geometry notation or fractions
- Current math best output has 34 answer entries, with review flags on weak long-answer areas.

Chinese result:

- Full-page OCR extracted the first page short-answer content and the reading response on page 2.
- Essay pages were readable as continuous text, split across the two photographed pages.
- The essay OCR is useful for coarse learning-analysis features such as topic, structure, vocabulary, and obvious writing problems, but it contains handwriting OCR typos and must keep the page image for audit.
- Choice-like outputs such as `BCD` / `ACD` should be validated against the original selection format and score sheet.
- Current Chinese best output has 20 answer entries, with essay pages flagged for review.

Follow-up crop test:

- Math page 1 now has tight `fill-answer` crops for questions 9-16.
- Multi-blank items are split into subfields:
  - `q12-x`, `q12-y`
  - `q16-1`, `q16-2`
- Tight raw crops are the current canonical input for OCR because they preserve the handwritten context without unrelated printed labels.
- An experimental `fill-answer-clean` output removes long horizontal rules, adds white padding, and upscales the crop. This is not yet the default. In the Alibaba handwriting test it helped some cases but harmed others:
  - raw `q11` returned roughly `X x=3`, while clean `q11` degraded to `-3`
  - raw `q12-y` returned `-10`, while clean degraded to `11 0`
  - single-character crops such as `q12-x` remain difficult for handwriting OCR
- Current best practice: keep both raw tight crop and clean candidate, but feed the raw crop to OCR first and use the clean crop only as a fallback/ensemble input.

## Current POC Script

- `answer-card-poc.py`
- `aliyun-handwriting-ocr.py`

It currently:

- parses the score spreadsheet
- converts HEIC images using `sips`
- applies EXIF transpose when loading images
- cuts math page-1 fill/solution regions
- cuts tight math page-1 handwritten fill-answer regions
- creates experimental fill-answer-clean crops for OCR fallback testing
- attempts fixed-coordinate choice detection
- writes debug images for visual QA

Current output:

- `data/answer-card-poc/math/answer-card-poc.json`
- `data/answer-card-poc/math/math-choice-debug.jpg`
- `data/answer-card-poc/math/math-fill-debug.jpg`
- `data/answer-card-poc/math/math-fill-answer-debug.jpg`
- `data/answer-card-poc/math/math-solution-debug.jpg`
- `data/answer-card-poc/math/crops/`

## Next Step

Replace fixed coordinates with anchor-based normalization:

1. Detect black registration blocks with connected components.
2. Fit the answer-card rectangle or local section rectangle.
3. Warp the page to canonical coordinates.
4. Re-run choice detection on normalized images.
5. Add Qwen/Alibaba OCR only after crop quality is stable.
