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
                        # print(f"   >> Processing Page {page_num}...", flush=True)
                        clean_raw_text = clean_thai_pdf_text(raw_text)
                        corrected_chunk = process_text_with_ollama(clean_raw_text)  
                        print(corrected_chunk)
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
    
def fix_header_with_ollama(header_text: str) -> str:
    prompt = (
        f"Correct Thai text errors. Focus on identifying chapter titles like 'ตอนที่'.\n"
        f"Input: {header_text}\n"
        f"Output ONLY the corrected text line."
    )
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": 50,  
            "temperature": 0.1 
        }
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
    except Exception as e:
        print(f"Ollama Error (Header): {e}")
        return header_text 

@app.post("/map-chapters/")
async def map_chapters(
    file: UploadFile = File(...),
    start_chapter: int = Form(...),
    end_chapter: int = Form(...)
):
    print(f"\n========== MAPPING CHAPTERS {start_chapter} to {end_chapter} ==========", flush=True)
    
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="This is not a PDF file")

    file_content = await file.read()
    
    found_chapters = []  # เก็บผลลัพธ์: [{'chapter': 1, 'start_page': 3, 'end_page': 5}, ...]
    
    # ตัวแปรช่วยในการ Mapping
    current_chapter_num = None
    current_chapter_start_page = None
    
    start_time = time.perf_counter()

    try:
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            total_pages = len(pdf.pages)
            
            # วนลูปทุกหน้าเพื่อหาจุดขึ้นต้นตอนใหม่
            for i, page in enumerate(pdf.pages):
                page_num = i + 1
                
                # 1. ดึง Text แค่ส่วนบน (ประมาณ 1/4 หน้าบน หรือ 3-4 บรรทัดแรก)
                # ใช้ crop เพื่อความเร็วและแม่นยำ ไม่ต้อง extract ทั้งหน้า
                width = page.width
                height = page.height
                header_crop = page.crop((0, 0, width, height * 0.2)) # ตัดมาแค่ 20% ด้านบน
                
                raw_text = header_crop.extract_text()
                
                if not raw_text or not raw_text.strip():
                    continue

                # 2. Clean เบื้องต้น
                cleaned_text = clean_thai_pdf_text(raw_text)
                # ตัดเอาแค่ 100 ตัวอักษรแรกเพื่อส่ง AI (ประหยัดเวลา)
                short_header = cleaned_text[:150].replace('\n', ' ') 

                # 3. ส่งให้ Ollama แก้ไข
                corrected_header = fix_header_with_ollama(short_header)
                
                # 4. ใช้ Regex หาคำว่า "ตอนที่ <ตัวเลข>"
                # รองรับกรณีเว้นวรรค เช่น "ตอน ที่ 1" หรือ "ตอนที่1"
                match = re.search(r'ตอน\s*ที่\s*(\d+)', corrected_header)
                
                if match:
                    found_chap_num = int(match.group(1))
                    print(f" -> Found Chapter {found_chap_num} at Page {page_num}", flush=True)

                    # --- LOGIC การตัดจบตอนเก่า ---
                    if current_chapter_num is not None:
                        # บันทึกตอนเก่าลง list
                        # หน้าจบของตอนเก่า คือ หน้าก่อนหน้าปัจจุบัน (page_num - 1)
                        found_chapters.append({
                            "chapter": current_chapter_num,
                            "start_page": current_chapter_start_page,
                            "end_page": page_num - 1
                        })
                    
                    # เริ่มต้นตอนใหม่
                    current_chapter_num = found_chap_num
                    current_chapter_start_page = page_num
            
            # 5. จัดการตอนสุดท้าย (เพราะวนลูปจบแล้ว แต่ตอนสุดท้ายยังไม่ได้บันทึก end_page)
            if current_chapter_num is not None:
                found_chapters.append({
                    "chapter": current_chapter_num,
                    "start_page": current_chapter_start_page,
                    "end_page": total_pages # จบที่หน้าสุดท้ายของไฟล์
                })

    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Processing Error: {e}")

    # 6. Filter เอาเฉพาะช่วงตอนที่ User ต้องการ
    filtered_result = [
        c for c in found_chapters 
        if start_chapter <= c['chapter'] <= end_chapter
    ]
    if not filtered_result and found_chapters:
         print("Warning: Chapters found but not in the requested range.")

    duration = time.perf_counter() - start_time
    print(f"Mapping finished in {duration:.2f} seconds")

    return {
        "filename": file.filename,
        "request_range": f"Chapter {start_chapter} - {end_chapter}",
        "total_pages_scanned": total_pages,
        "processing_time": f"{duration:.2f}s",
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