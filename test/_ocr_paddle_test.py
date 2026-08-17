

import asyncio
import _path_setup  # noqa: E402

import json
import os
import sys
from pathlib import Path

from paddleocr._api_client.async_client import AsyncPaddleOCRClient
from paddleocr._api_client.models import PaddleOCRVLOptions


def load_token():
    token = os.environ.get("PADDLEOCR_ACCESS_TOKEN")
    if token:
        return token
    cfg = Path.home() / ".pdf_ocr_config" / "config.json"
    if cfg.exists():
        return json.loads(cfg.read_text(encoding="utf-8"))["online_ocr_token"]
    raise RuntimeError("missing PADDLEOCR_ACCESS_TOKEN or ~/.pdf_ocr_config/config.json")


async def main():
    pdf_path = sys.argv[1]
    page_ranges = sys.argv[2] if len(sys.argv) > 2 else None
    client = AsyncPaddleOCRClient(
        token=load_token(),
        request_timeout=600.0,
        poll_timeout=1800.0,
    )
    options = PaddleOCRVLOptions(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_chart_recognition=True,
        use_seal_recognition=True,
    )
    try:
        result = await client.parse_document(
            model="PaddleOCR-VL-1.6",
            file_path=pdf_path,
            page_ranges=page_ranges,
            options=options,
        )
        print("PAGES:", result.pages)
        print(result.markdown)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
