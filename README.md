# OCR Webhook API

Lightweight FastAPI-based webhook that performs OCR on uploaded PDF/images and attempts to extract bill/invoice line items.

**Project**: `webhook_app_final.py`

## Features
- Accepts `pdf`, `png`, `jpg`, `jpeg` uploads via a multipart `POST /webhook/ocr` endpoint.
- Uses EasyOCR when installed, otherwise falls back to Tesseract (via `pytesseract`).
- Converts PDF pages to images (PyMuPDF / `fitz`) and performs OCR per-page.
- Tries to parse bill/invoice line items using regular expressions and returns structured `pagewise_line_items`.
- Health endpoint at `GET /webhook/health` and Swagger UI at `/docs`.

## Requirements
- Python 3.8+
- Windows (tested)
- Optional: Tesseract OCR (if you don't want EasyOCR or if EasyOCR is not installed)

Python packages (install via pip):
- fastapi
- uvicorn
- PyMuPDF (imported as `fitz`)
- opencv-python
- numpy
- pillow
- easyocr (optional)
- pytesseract (optional)

You can install core dependencies with:

```bash
python -m pip install fastapi uvicorn PyMuPDF opencv-python numpy pillow
# optional OCR libs
python -m pip install easyocr pytesseract
```

Or create a `requirements.txt` with the packages above.

## Tesseract (Windows)
If `easyocr` is not installed, the app will try to use `pytesseract`. On Windows you must install Tesseract OCR separately:

- Download/install from: https://github.com/UB-Mannheim/tesseract/wiki/Downloads
- After installation, ensure the executable is on your PATH or set the `TESSERACT_PATH` environment variable.

The script looks for common install locations and will print instructions if it can't find tesseract.

## Usage
Place `webhook_app_final.py` and this `README.md` in the same directory. The script will create an `uploads/` folder to temporarily store incoming files.

Run directly (the file contains a `__main__` block that starts uvicorn):

For `cmd.exe`:

```cmd
python webhook_app_final.py
```

Alternatively run via uvicorn module (recommended for dev with reload):

```cmd
python -m uvicorn webhook_app_final:app --host 0.0.0.0 --port 8000 --reload
```

Open API docs in your browser:

- http://localhost:8000/docs
- Health check: http://localhost:8000/webhook/health

## API
- POST `/webhook/ocr` — multipart form upload with `file` field
  - Accepts: `pdf`, `png`, `jpg`, `jpeg`
  - Returns JSON with `data.pagewise_line_items` and `total_item_count`.

Example curl (from a shell that has curl):

```bash
curl -X POST "http://localhost:8000/webhook/ocr" -F "file=@C:/path/to/invoice.pdf"
```

Example successful response (trimmed):

```json
{
  "is_success": true,
  "data": {
    "pagewise_line_items": [
      {
        "page_no": "1",
        "page_type": "Bill Detail",
        "bill_items": [
          {"item_name": "Paracetamol 500mg", "item_quantity": 2, "item_rate": 10.0, "item_amount": 20.0}
        ]
      }
    ],
    "total_item_count": 1
  }
}
```

## Notes & Troubleshooting
- The script tries EasyOCR first (if available). EasyOCR may require additional fonts or resources and may take longer on first run.
- If OCR results are noisy, try increasing PDF rasterization DPI in the code (currently using 300 DPI via `fitz.Matrix`).
- If Tesseract is not detected, either install it or set path manually in the environment variable `TESSERACT_PATH` or update the `possible_paths` list in the script.
- Uploaded files are temporarily written to the `uploads/` folder and deleted after processing.

## Extending
- Improve the regex extraction in `extract_bill_items_regex` for your bill formats or replace it with an ML-based line-item parser.
- Add authentication or a queue if you expect high traffic.
- Add Dockerfile if you want containerized deployment (remember to install Tesseract into the image).

## License
This repository contains example code - add your preferred license.
