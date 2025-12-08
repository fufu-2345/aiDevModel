from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
import pdfplumber
import requests
import json
import io
import time
import re

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
    payload = { "model": OLLAMA_MODEL, "prompt": prompt, "stream": False }
    try:
        response = requests.post(
            OLLAMA_API_URL, 
            headers={"Content-Type": "application/json"}, 
            data=json.dumps(payload),
            timeout=1500
        )
        response.raise_for_status() 
        result = response.json()
        return result['response'].strip()
    except requests.exceptions.RequestException as e:
        print(f"Error calling Ollama API: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to communicate with Ollama or Ollama failed to process: {e}. "f"Please check if Ollama is running and model '{OLLAMA_MODEL}' is installed.")

def clean_thai_pdf_text(text: str) -> str:
    if not text:
        return ""
    replace_dict = {
        '\uf700': 'ฐ', '\uf701': 'ญ', '\uf702': 'ฐ', '\uf703': 'ญ',
        '\uf704': 'ญ', '\uf705': 'ฐ', '\uf706': 'ญ', '\uf707': 'ฐ',
        '\uf708': 'ญ', '\uf709': 'ญ', '\uf70a': '่', '\uf70b': '้',
        '\uf70c': '๊', '\uf70d': '๋', '\uf70e': '์', '\uf70f': 'ํ',
        '\uf710': 'ั', '\uf711': '็', '\uf712': 'ิ', '\uf713': 'ี',
        '\uf714': 'ึ', '\uf715': 'ื', '\uf716': 'ุ', '\uf717': 'ู',
        '\uf718': 'ุ', '\uf719': 'ู', '\uf71a': '็',
    }
    cleaned_text = text
    for pua_char, std_char in replace_dict.items():
        cleaned_text = cleaned_text.replace(pua_char, std_char)
    return cleaned_text

@app.post("/process-pdf/")
async def upload_and_process_pdf(file: UploadFile = File(...), start: int = Form(...), end: int = Form(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="This is not a PDF file")
    
    file_content = await file.read()
    correctedPages = [] 
    total_pages = 0
    # start_time = time.perf_counter()
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
                        cleanText = process_text_with_ollama(clean_thai_pdf_text(raw_text)) 
                        print(cleanText, flush=True)
                        correctedPages.append(cleanText)
                    else:
                        print(f"   >> Page {page_num} is empty or image only.", flush=True)
                        correctedPages.append(f"--- Page {page_num} ---\n[Empty Page]\n")
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"PDF Error: {e}")
    correctedChapter = "\n".join(correctedPages)
    # duration = time.perf_counter() - start_time
    # print(f"Total time use: {duration:.3f} seconds", flush=True)
    return {
        "filename": file.filename,
        "pages_processed": f"{start}-{end}",
        "corrected_text": correctedChapter
    }
    
def fix_header_with_ollama(header_text: str) -> str:
    prompt = (
        f"Correct Thai text errors. Focus on identifying chapter titles like 'ตอนที่'.\n"
        f"Input: {header_text}\n"
        f"Output ONLY the corrected text line."
    )
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "options": { "num_predict": 50, "temperature": 0.1 }}
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
    except Exception as e:
        print(f"Ollama Error (Header): {e}")
        return header_text 

@app.post("/map-chapters/")
async def map_chapters(file: UploadFile = File(...), startChapter: int = Form(...), endChapter: int = Form(...)):
    # start_time = time.perf_counter()
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="This is not a PDF file")
    file_content = await file.read()
    found_chapters = [] 
    currentChapter = None
    currentStart = None
    try:
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            width = pdf.pages[0].width
            height = pdf.pages[0].height*0.1
            for i, page in enumerate(pdf.pages):
                raw_text = page.crop((0, 0, width, height)).extract_text()
                
                if not raw_text or not raw_text.strip():
                    continue
                
                cleaned_text = clean_thai_pdf_text(raw_text)               
                short_header = cleaned_text[:20].replace('\n', ' ')      
                # corrected_header = fix_header_with_ollama(short_header)
                match = re.search(r'ตอนท ี่\s*(\d+)', short_header)
                
                if match:
                    found_chap_num = int(match.group(1))
                    # ถ้ามีตอนเก่าค้างอยู่ (เช่นเจอตอน 2 แล้วกำลังจะเริ่มตอน 2) -> ให้บันทึกตอนที่ 1
                    if currentChapter is not None:
                        found_chapters.append({
                            "chapter": currentChapter,
                            "start_page": currentStart,
                            "end_page": i
                        })
                        # [จุดแก้ไขสำคัญ]: เช็คว่าตอนที่เพิ่งบันทึกจบไป ใช่ตอนสุดท้ายที่ต้องการไหม?
                        # ถ้าใช่ (เช่น เพิ่งบันทึกตอน 5 จบ เพราะเจอตอน 6) -> หยุดทันที!
                        if currentChapter >= endChapter:
                            print(f"DEBUG: Found end of requested chapter {endChapter}. Stopping scan.", flush=True)
                            currentChapter = None # Reset เพื่อไม่ให้ไปบันทึกซ้ำด้านล่าง
                            break      
                    # เริ่มต้น track ตอนใหม่ที่เพิ่งเจอ
                    currentChapter = found_chap_num
                    currentStart = i+1                
                    # หา 500 เจอ 501
                    if found_chap_num > endChapter:
                        currentChapter = None
                        break
            # จัดการกรณีวนลูปจบเล่ม หรือ Break ออกมาแล้วยังมีตอนค้างอยู่ (กรณีตอนสุดท้ายของไฟล์)
            if currentChapter is not None:
                # ตรวจสอบอีกครั้งว่าตอนที่ค้างอยู่ อยู่ใน range ที่ต้องการไหม
                if currentChapter <= endChapter:
                    found_chapters.append({
                        "chapter": currentChapter,
                        "start_page": currentStart,
                        "end_page": len(pdf.pages) 
                    })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing Error: {e}")
    # Filter ผลลัพธ์ (เผื่อมีหลุดมา)
    filtered_result = [
        c for c in found_chapters 
        if startChapter <= c['chapter'] <= endChapter
    ]
    if not filtered_result and found_chapters:
        print("Warning: Chapters found but not in the requested range.")
    # duration = time.perf_counter() - start_time
    # print(f"Mapping finished in {duration:.3f} seconds")
    return {
        "chapters": filtered_result
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