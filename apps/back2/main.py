from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
import pdfplumber
import requests
import json
import io
import time

app= FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "scb10x/typhoon2.1-gemma3-4b:latest"

def process_text_with_ollama(text_input: str) -> str:
    prompt = (
        f"Correct the Thai vowel and tone mark encoding errors in the text below. Rules:\n"
        f"1. Fix all 'sara-loi' (floating vowels) and misplaced tone marks to standard Thai grammar.\n"
        f"2. Maintain the original meaning and writing style.\n"
        f"3. CRITICAL: Output ONLY the corrected text. Do not include any introduction, preamble, notes, or conclusion."
    
        f"--- my text ---\n"
        f"{text_input}\n"
        f"Output ONLY the result."
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
            timeout=1200
        )
        response.raise_for_status() 
        
        result = response.json()
        return result['response'].strip()

    except requests.exceptions.RequestException as e:
        print(f"Error calling Ollama API: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to communicate with Ollama or Ollama failed to process: {e}. "f"Please check if Ollama is running and model '{OLLAMA_MODEL}' is installed.")

@app.post("/process-pdf/")
async def upload_and_process_pdf(
    file: UploadFile = File(...),
    start: int = Form(...),
    end: int = Form(...) 
):
    print(f"\n========== NEW REQUEST ==========", flush=True)
    print(f"DEBUG: Received request -> Start: {start}, End: {end}", flush=True)

    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="This is not a PDF file")
    
    file_content = await file.read()
    corrected_pages_list = [] 
    total_pages = 0
    start_time = time.perf_counter()
    
    try:
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            total_pages = len(pdf.pages)
            if start < 1:
                 raise HTTPException(status_code=400, detail="Start page must be at least 1")
            if total_pages < end:
                raise HTTPException(status_code=400, detail=f"PDF has only {total_pages} pages")

            for page_num in range(start, end + 1):
                page_index = page_num - 1     
                if 0 <= page_index < total_pages:
                    raw_text = pdf.pages[page_index].extract_text()
                    
                    if raw_text and raw_text.strip():
                        print(f"   >> Processing Page {page_num}...", flush=True)
                        corrected_chunk = process_text_with_ollama(raw_text)  
                        formatted_output = f"--- Page {page_num} ---\n{corrected_chunk}\n"
                        corrected_pages_list.append(formatted_output)
                    else:
                        print(f"   >> Page {page_num} is empty or image only.", flush=True)
                        corrected_pages_list.append(f"--- Page {page_num} ---\n[Empty Page]\n")
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"PDF Error: {e}")
    final_corrected_text = "\n".join(corrected_pages_list)
    end_time = time.perf_counter()
    duration = end_time - start_time
    print(f"Total time use: {duration:.2f} seconds", flush=True)
    
    return {
        "filename": file.filename,
        "pages_processed": f"{start}-{end}",
        "total_pages_in_pdf": total_pages,
        "processing_time_seconds": round(duration, 2),
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