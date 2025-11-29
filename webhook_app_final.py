from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
from pathlib import Path
import uvicorn
import fitz  # PyMuPDF
import cv2
try:
    import easyocr
    HAS_EASYOCR = True
except ImportError:
    HAS_EASYOCR = False
    import pytesseract
import numpy as np
from PIL import Image
import io

# Configure pytesseract - try multiple paths (fallback if EasyOCR not available)
pytesseract_configured = False
if not HAS_EASYOCR:
    try:
        # Try to find tesseract in common Windows locations
        possible_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            r"C:\Users\Kashish Verma\AppData\Local\Tesseract-OCR\tesseract.exe",
            r"C:\Tesseract-OCR\tesseract.exe",
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.pytesseract_cmd = path
                print(f"✓ Found tesseract at: {path}")
                pytesseract_configured = True
                break
        
        if not pytesseract_configured:
            print("⚠️  Tesseract OCR not found in standard locations.")
            print("   Please install from: https://github.com/UB-Mannheim/tesseract/wiki/Downloads")
            print("   Or set TESSERACT_PATH environment variable")
            
    except Exception as e:
        print(f"Warning: Could not configure pytesseract path: {e}")

# ---------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------
app = FastAPI(title="OCR Webhook API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# Config
# ---------------------------------------------------------
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}

Path(UPLOAD_FOLDER).mkdir(exist_ok=True)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------
# API ROOT
# ---------------------------------------------------------
@app.get("/")
async def root():
    return {
        "message": "OCR Webhook API",
        "version": "1.0.0",
        "endpoints": {
            "POST /webhook/ocr": "Submit file for OCR",
            "GET /webhook/health": "Health check",
            "GET /docs": "Swagger UI"
        }
    }


@app.get("/webhook/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "ocr_webhook",
        "supported_formats": list(ALLOWED_EXTENSIONS)
    }


# ---------------------------------------------------------
# OCR Helpers
# ---------------------------------------------------------
_ocr_reader = None

def get_ocr_reader():
    """Get or initialize EasyOCR reader"""
    global _ocr_reader
    if _ocr_reader is None and HAS_EASYOCR:
        print("Initializing EasyOCR reader (first run, may take a moment)...")
        _ocr_reader = easyocr.Reader(['en'], gpu=False)
    return _ocr_reader

def simple_pdf_ocr(pdf_path):
    pdf_doc = fitz.open(pdf_path)
    all_text = {}

    if HAS_EASYOCR:
        reader = get_ocr_reader()
        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
            img_data = pix.tobytes("ppm")
            img_pil = Image.open(io.BytesIO(img_data))
            img_cv = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
            
            results = reader.readtext(img_cv)
            text = "\n".join([detection[1] for detection in results])
            all_text[page_num + 1] = text
    else:
        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
            img_data = pix.tobytes("ppm")
            img_pil = Image.open(io.BytesIO(img_data))
            img_cv = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
            
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(
                gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
            
            text = pytesseract.image_to_string(thresh, config="--psm 6")
            all_text[page_num + 1] = text

    pdf_doc.close()
    return all_text


def simple_image_ocr(image_bytes):
    img = Image.open(io.BytesIO(image_bytes))
    img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    if HAS_EASYOCR:
        reader = get_ocr_reader()
        results = reader.readtext(img_cv)
        text = "\n".join([detection[1] for detection in results])
    else:
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(
            gray, 0, 255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        text = pytesseract.image_to_string(thresh, config="--psm 6")
    
    return text

import re

def extract_bill_items_regex(text: str):
    patterns = [
        # Pharmacy style: SL + Description + Qty + Rate + Amount
        re.compile(
            r"(?:\d+\s+)?(?P<name>[A-Za-z0-9\-\(\)\/\., ]+?)\s+"
            r"(?P<qty>\d+(?:\.\d+)?)\s+"
            r"(?P<rate>\d+(?:\.\d+)?)\s+"
            r"(?P<amount>\d+(?:\.\d+)?)"
        ),

        # Hospital style: Description + Qty + Rate + Net Amount
        re.compile(
            r"(?P<name>[A-Za-z0-9\-\|\.\(\)\/, ]+?)\s+"
            r"(?P<qty>\d+(?:\.\d+)?)\s+"
            r"(?P<rate>\d+(?:\.\d+)?)\s+"
            r"(?P<amount>\d+(?:\.\d+)?)"
        ),

        # Investigation style: Description + Date + Qty + Rate + Amount
        re.compile(
            r"(?P<name>[A-Za-z0-9\-\(\)\/\., ]+?)\s+"
            r"\d{1,2}\/\d{1,2}\/\d{2,4}\s+"
            r"(?P<qty>\d+(?:\.\d+)?)\s+"
            r"(?P<rate>\d+(?:\.\d+)?)\s+"
            r"(?P<amount>\d+(?:\.\d+)?)"
        )
    ]

    items = []

    for pattern in patterns:
        for m in pattern.finditer(text):
            name = re.sub(r"\s+", " ", m.group('name')).strip()

            qty = float(m.group("qty"))
            rate = float(m.group("rate"))
            amount = float(m.group("amount"))

            items.append({
                "item_name": name,
                "item_quantity": qty,
                "item_rate": rate,
                "item_amount": amount
            })

    return items



# ---------------------------------------------------------
# OCR Webhook Endpoint
# ---------------------------------------------------------
@app.post("/webhook/ocr")
async def ocr_webhook(file: UploadFile = File(...)):
    try:
        if not allowed_file(file.filename):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            )

        # Save temp file
        file_path = os.path.join(UPLOAD_FOLDER, file.filename)
        file_bytes = await file.read()

        with open(file_path, "wb") as f:
            f.write(file_bytes)

        ext = file.filename.rsplit(".", 1)[1].lower()

        # OCR extraction
        if ext == "pdf":
            extracted = simple_pdf_ocr(file_path)
        else:
            extracted = {"page_1": simple_image_ocr(file_bytes)}

        # Cleanup temp file
        if os.path.exists(file_path):
            os.remove(file_path)

        # --------------------------
        # STRUCTURE THE FINAL OUTPUT
        # --------------------------
        page_items = []
        total_item_count = 0

        for idx, (page_no, text) in enumerate(extracted.items()):
            bill_items = extract_bill_items_regex(text)   # regex extraction

            total_item_count += len(bill_items)

            page_items.append({
                "page_no": str(idx + 1),
                "page_type": "Bill Detail",   # placeholder
                "bill_items": bill_items
            })

        # Final response
        return {
            "is_success": True,
            "token_usage": {
                "total_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0
            },
            "data": {
                "pagewise_line_items": page_items,
                "total_item_count": total_item_count
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Run server
# ---------------------------------------------------------
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 OCR Webhook Server Starting...")
    print("="*60)
    print("📍 http://localhost:8000")
    print("📚 http://localhost:8000/docs")
    print("🏥 http://localhost:8000/webhook/health")
    print("="*60 + "\n")

    uvicorn.run(app, host="0.0.0.0", port=8000)
