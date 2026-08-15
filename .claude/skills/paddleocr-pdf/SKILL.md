---
name: paddleocr-pdf
description: OCR a scanned PDF or image (no text layer) to Markdown using the PaddleOCR-VL cloud API. Use when a protocol reference document is a scanned PDF and you need its text content for parsing/verification work.
---

# PaddleOCR PDF OCR

Run the helper script `ocr.py` in this skill directory to OCR scanned PDFs/images via the PaddleOCR-VL cloud API and produce Markdown text you can read.

## When to use

- A protocol reference document is a **scanned PDF without a text layer** (e.g. `pypdf` `extract_text()` returns empty, or the Read tool returns nothing useful for the PDF).
- You need the document's text to verify or extend a parser.
- Do NOT use for PDFs that already have a text layer — extract with `pypdf` directly instead. Do NOT use for images you could just Read inline.

## Prerequisites

- `pip install requests`
- The API bearer token must be available. Set it once in the environment:
  - Windows (cmd): `set PADDLEOCR_TOKEN=<token>`
  - PowerShell: `$env:PADDLEOCR_TOKEN="<token>"`
  - Or pass `--token <token>` per run.
  - The token is intentionally NOT hardcoded in the script (keeps it out of git). Do not commit a hardcoded token.

## How to run

```bash
python .claude/skills/paddleocr-pdf/ocr.py "<path-to-pdf-or-image>" [--output-dir DIR] [--images]
```

- Local file: `python .claude/skills/paddleocr-pdf/ocr.py "E:/python/南网解析工具/国网新一代协议/HDC-国网双模协议/双模通信互联互通技术规范 第4-2部分：数据链路层通信协议.pdf"`
- URL: `python .claude/skills/paddleocr-pdf/ocr.py --url "https://..."`

Options:
- `--output-dir DIR` — default `<input_dir>/_ocr_<input_stem>/`
- `--images` — download embedded figures / recognition images (skipped by default; you cannot read them anyway, and skipping is much faster for large PDFs)
- `--model` — default `PaddleOCR-VL-1.6`
- `--poll-interval` — default 5s

## Output

- `<output-dir>/combined.md` — all pages concatenated with `<!-- ===== Page N ===== -->` markers. **Read this file** after OCR completes.
- `<output-dir>/page_001.md` ... `page_NNN.md` — per-page Markdown.

The script prints progress (`extracted/total pages` while running) and a final summary with the absolute path to `combined.md`.

## After OCR

1. Read `<output-dir>/combined.md` to obtain the document text.
2. Cross-reference with the relevant parser (e.g. `gw_new_gen_parser.py` for HDC, `csg_new_gen_parser.py` for 通感一体化).
3. If the document's identity/version was clarified (e.g. HDC 1.0 vs 2.0), update `AGENTS.md` §5 doc mapping.

## Notes

- Large PDFs (100+ pages) take several minutes; the API queues jobs, so just let polling run.
- The API submits a multipart upload for local files and JSON for URLs; both handled by the script.
- If a job fails, the script prints `errorMsg` and exits non-zero — retry, or try `--url` with an uploaded copy.
