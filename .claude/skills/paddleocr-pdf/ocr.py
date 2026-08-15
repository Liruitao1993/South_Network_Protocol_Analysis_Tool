#!/usr/bin/env python3
"""PaddleOCR-VL PDF/image OCR helper.

Submits a local file or URL to the PaddleOCR-VL cloud API, polls until the
job finishes, and saves per-page Markdown plus a single combined Markdown
file to an output directory.

The API bearer token is read from the PADDLEOCR_TOKEN environment variable
(or --token). It is intentionally NOT hardcoded here so the token is not
committed to the repository.

Usage:
    set PADDLEOCR_TOKEN=<your_token>
    python ocr.py <local_file_path> [--output-dir DIR] [--images]
    python ocr.py --url <https://...>  [--output-dir DIR] [--images]
"""
import argparse
import json
import os
import sys
import time

try:
    import requests
except ImportError:
    print("ERROR: requests library not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(2)

JOB_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
DEFAULT_MODEL = "PaddleOCR-VL-1.6"


def submit_job(file_path, file_url, token, model):
    """Submit a local file (multipart) or URL (JSON) and return the jobId."""
    headers = {"Authorization": f"bearer {token}"}
    optional_payload = {
        "useDocOrientationClassify": False,
        "useDocUnwarping": False,
        "useChartRecognition": False,
    }
    if file_url:
        headers["Content-Type"] = "application/json"
        payload = {"fileUrl": file_url, "model": model, "optionalPayload": optional_payload}
        resp = requests.post(JOB_URL, json=payload, headers=headers)
    else:
        data = {"model": model, "optionalPayload": json.dumps(optional_payload)}
        with open(file_path, "rb") as f:
            resp = requests.post(JOB_URL, headers=headers, data=data, files={"file": f})
    if resp.status_code != 200:
        print(f"ERROR: submit failed {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)
    return resp.json()["data"]["jobId"]


def poll_job(job_id, token, interval):
    """Poll job status until done; return the JSONL result URL."""
    headers = {"Authorization": f"bearer {token}"}
    while True:
        resp = requests.get(f"{JOB_URL}/{job_id}", headers=headers)
        if resp.status_code != 200:
            print(f"ERROR: poll failed {resp.status_code}: {resp.text}", file=sys.stderr)
            sys.exit(1)
        data = resp.json()["data"]
        state = data.get("state")
        if state == "pending":
            print("  state: pending")
        elif state == "running":
            prog = data.get("extractProgress", {}) or {}
            tp, ep = prog.get("totalPages"), prog.get("extractedPages")
            if tp is not None:
                print(f"  state: running  {ep}/{tp} pages")
            else:
                print("  state: running...")
        elif state == "done":
            prog = data.get("extractProgress", {}) or {}
            print(f"  DONE: extracted {prog.get('extractedPages')} pages")
            return data["resultUrl"]["jsonUrl"]
        elif state == "failed":
            print(f"ERROR: job failed: {data.get('errorMsg')}", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"  state: {state}")
        time.sleep(interval)


def download_and_save(jsonl_url, output_dir, save_images):
    """Download JSONL results, write per-page + combined Markdown. Returns (pages, images)."""
    resp = requests.get(jsonl_url)
    resp.raise_for_status()
    os.makedirs(output_dir, exist_ok=True)
    combined_path = os.path.join(output_dir, "combined.md")
    page_num = 0
    image_count = 0
    with open(combined_path, "w", encoding="utf-8") as combined:
        for line in resp.text.splitlines():
            line = line.strip()
            if not line:
                continue
            result = json.loads(line).get("result", {})
            for res in result.get("layoutParsingResults", []):
                page_num += 1
                md_text = (res.get("markdown") or {}).get("text", "")
                md_path = os.path.join(output_dir, f"page_{page_num:03d}.md")
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(md_text)
                combined.write(f"\n\n<!-- ===== Page {page_num} ===== -->\n\n")
                combined.write(md_text)
                if save_images:
                    for img_path, img_url in (res.get("markdown") or {}).get("images", {}).items():
                        full = os.path.join(output_dir, img_path)
                        os.makedirs(os.path.dirname(full), exist_ok=True)
                        try:
                            r = requests.get(img_url)
                            if r.status_code == 200:
                                with open(full, "wb") as f:
                                    f.write(r.content)
                                image_count += 1
                        except Exception:
                            pass
                    for img_name, img_url in res.get("outputImages", {}).items():
                        fn = os.path.join(output_dir, f"{img_name}_{page_num}.jpg")
                        try:
                            r = requests.get(img_url)
                            if r.status_code == 200:
                                with open(fn, "wb") as f:
                                    f.write(r.content)
                                image_count += 1
                        except Exception:
                            pass
    return page_num, image_count


def main():
    ap = argparse.ArgumentParser(description="PaddleOCR-VL OCR for scanned PDF/images")
    ap.add_argument("file_path", nargs="?", help="local file path to OCR")
    ap.add_argument("--url", help="file URL (alternative to local path)")
    ap.add_argument("--output-dir", help="output directory (default: <file_dir>/_ocr_<stem>)")
    ap.add_argument("--token", default=os.environ.get("PADDLEOCR_TOKEN"),
                    help="API bearer token (or env PADDLEOCR_TOKEN)")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"PaddleOCR model (default: {DEFAULT_MODEL})")
    ap.add_argument("--images", action="store_true", help="download embedded/output images (skipped by default)")
    ap.add_argument("--poll-interval", type=float, default=5.0, help="poll interval seconds (default: 5)")
    args = ap.parse_args()

    if not args.file_path and not args.url:
        ap.error("must provide a local file_path or --url")
    if not args.token:
        print("ERROR: no API token. Set the PADDLEOCR_TOKEN env var or pass --token.",
              file=sys.stderr)
        sys.exit(2)

    file_url = args.url
    file_path = None
    if not file_url:
        file_path = os.path.abspath(args.file_path)
        if not os.path.exists(file_path):
            print(f"ERROR: file not found: {file_path}", file=sys.stderr)
            sys.exit(1)

    # Resolve output directory.
    if args.output_dir:
        output_dir = args.output_dir
    else:
        if file_path:
            stem = os.path.splitext(os.path.basename(file_path))[0]
            output_dir = os.path.join(os.path.dirname(file_path), f"_ocr_{stem}")
        else:
            from urllib.parse import urlparse
            stem = os.path.splitext(os.path.basename(urlparse(file_url).path))[0] or "ocr"
            output_dir = os.path.join(os.getcwd(), f"_ocr_{stem}")

    label = file_url or file_path
    print(f"OCR input : {label}")
    print(f"output dir: {output_dir}")
    print(f"model     : {args.model}")

    print("submitting job...")
    job_id = submit_job(file_path, file_url, args.token, args.model)
    print(f"job id    : {job_id}")

    print("polling...")
    jsonl_url = poll_job(job_id, args.token, args.poll_interval)

    print("downloading results...")
    pages, imgs = download_and_save(jsonl_url, output_dir, args.images)

    print("\n=== DONE ===")
    print(f"pages           : {pages}")
    if args.images:
        print(f"images downloaded: {imgs}")
    else:
        print("images          : skipped (use --images to enable)")
    print(f"combined markdown: {os.path.join(output_dir, 'combined.md')}")
    print(f"per-page markdown: {output_dir}{os.sep}page_001.md .. page_{pages:03d}.md")


if __name__ == "__main__":
    main()
