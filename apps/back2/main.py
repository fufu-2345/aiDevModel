from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pdfplumber
import requests
import json
import io

app= FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:latest"


def process_text_with_ollama(text_input: str) -> str:
    """
    ส่งข้อความดิบไปยัง Ollama เพื่อแก้ไขและเพิ่มข้อความ "การบ้าน123"
    """
    
    prompt = (
        f"ข้อความต่อไปนี้ถูกดึงมาจากไฟล์ PDF (ภาษาไทย) อาจมีข้อผิดพลาดด้านการจัดรูปแบบ "
        f"หรือเว้นวรรคผิดพลาด โปรดแก้ไขให้ถูกต้องและอ่านง่ายที่สุด และเพิ่มคำว่า "
        f"'การบ้าน123' ต่อท้ายข้อความที่แก้ไขแล้ว: \n\n"
        f"--- ข้อความจาก PDF ---\n"
        f"{text_input}"
    )
    
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False 
    }

    try:
        response = requests.post(
            OLLAMA_API_URL, 
            headers={"Content-Type": "application/json"}, 
            data=json.dumps(payload),
            timeout=120 
        )
        response.raise_for_status() 
        
        result = response.json()
        return result['response'].strip()

    except requests.exceptions.RequestException as e:
        print(f"Error calling Ollama API: {e}")
        raise HTTPException(status_code=500, 
                            detail=f"Failed to communicate with Ollama or Ollama failed to process: {e}. "
                                   f"Please check if Ollama is running and model '{OLLAMA_MODEL}' is installed.")


@app.post("/process-pdf/")
async def upload_and_process_pdf(file: UploadFile = File(...)):
    """
    Endpoint หลัก: รับไฟล์ PDF, อ่านหน้า 2, และส่งไปให้ Ollama ประมวลผล
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="this is not pdf")
    
    file_content = await file.read()
    
    try:
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            if len(pdf.pages) < 2:
                raise HTTPException(status_code=400, detail="its only  1 page")
            page_2_text = pdf.pages[1].extract_text()
            if not page_2_text:
                raise HTTPException(status_code=400, detail="page 2 is empty")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"pdfplumber cant read PDF with : {e}")

    final_corrected_text = process_text_with_ollama(page_2_text)
    return {
        "filename": file.filename,
        "page_read": 2,
        "corrected_text": final_corrected_text
    }
    
@app.get("/")
def root():
    return "server is worked 111"

@app.get("/test")
def root():
    return "test test 222"

@app.post("/")
def root():
    return "test post 333"

@app.get("/ollama")
def query():
    result = generate_text("this is ollama")
    return {"response": result}

# def main():
#     default_pdf = os.path.join(os.path.dirname(__file__), 'sample.pdf')
#     model_dir = os.environ.get(MODEL_DIR_ENV)
#     if model_dir:
#         logger.info('KHANOMTAN_MODEL_DIR is set to: %s', model_dir)
#     else:
#         logger.info('KHANOMTAN_MODEL_DIR not set; continuing without model path')

#     pdf_path = default_pdf
#     import argparse
#     parser = argparse.ArgumentParser()
#     parser.add_argument('--pdf', help='Path to pdf to inspect', default=pdf_path)
#     args = parser.parse_args()