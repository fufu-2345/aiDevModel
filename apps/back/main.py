from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import List
import pdfplumber
import requests
import json
import io
import time
import re

from database import create_db_and_tables, get_session
from models import movieTitle, chapterContent

try:
    import torch
    from diffusers import StableDiffusionPipeline
    HAS_AI_LIB = True
except ImportError:
    HAS_AI_LIB = False
    print("Warning: 'diffusers' or 'torch' not found. AI Image Generation will not work.")
    
@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ollamaURL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "scb10x/typhoon2.1-gemma3-4b:latest"

class ChapterUpdate(BaseModel):
    chapterTitle: str
    chapterDetail: str
    
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

@app.get("/movies/", response_model=List[movieTitle])
def get_movies(session: Session = Depends(get_session)):
    movies = session.exec(select(movieTitle)).all()
    return movies

@app.post("/upload-movie/")
async def upload_movie(
    title: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="This is not a PDF file")
    start = time.perf_counter()
    file_content = await file.read()
    new_movie = movieTitle(movieTitle=title, episodeAmount=0, picPath="")
    session.add(new_movie)
    session.commit()
    session.refresh(new_movie) 
    try:
        found_chapters_data = []
        chapter_map = []
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            total_pages = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                raw_text = page.extract_text()
                if not raw_text or not raw_text.strip():
                    continue
                
                cleaned_text = clean_thai_pdf_text(raw_text)
                lines = raw_text.split('\n')
                for line in lines[:2]:
                    match = re.search(r'ตอนท ี่\s*(\d+)', line)
                    if match:
                        found_chap_num = int(match.group(1))
                        if not chapter_map or chapter_map[-1]['num'] != found_chap_num:
                            chapter_map.append({
                                'num': found_chap_num,
                                'start_page': i
                            })
                        break 
            for idx, chap in enumerate(chapter_map):
                start_p = chap['start_page']
                end_p = chapter_map[idx+1]['start_page'] - 1 if (idx + 1 < len(chapter_map)) else total_pages - 1
                chapter_full_content = []
                chapter_title_text = ""
                
                for p_idx in range(start_p, end_p + 1):
                    page = pdf.pages[p_idx]
                    page_text = clean_thai_pdf_text(page.extract_text() or "")                    
                    if p_idx == start_p:
                        lines = page_text.split('\n')
                        header_found = False                       
                        for line in lines:
                            if not header_found and re.search(r'ตอนท ี่\s*' + str(chap['num']), line):
                                title_match = re.search(r'ตอนท ี่\s*\d+\s*(.*)', line)
                                if title_match:
                                    chapter_title_text = title_match.group(1).strip()
                                header_found = True
                            else:
                                chapter_full_content.append(line)
                    else:
                        chapter_full_content.append(page_text)
                final_title = chapter_title_text if chapter_title_text else f"ตอนที่ {chap['num']}"               
                new_chapter = chapterContent(
                    episodeNumber=float(chap['num']),
                    chapterTitle=final_title,
                    chapterDetail="\n".join(chapter_full_content).strip(),
                    movieId=new_movie.id
                )
                session.add(new_chapter)
                found_chapters_data.append(new_chapter)
            new_movie.episodeAmount = len(found_chapters_data)
            session.add(new_movie)
            session.commit()   
            print(f"total time: {time.perf_counter() - start:.3f} seconds")
            return {
                "status": "success",
                "movie_id": new_movie.id,
                "total_chapters_found": len(found_chapters_data),
                "chapters": [c.chapterTitle for c in found_chapters_data]
            }
    except Exception as e:
        print(f"Error processing PDF: {e}")
        session.delete(new_movie)
        session.commit()
        raise HTTPException(status_code=500, detail=f"PDF Processing Error: {e}")

@app.delete("/movies/{movie_id}")
def delete_movie(movie_id: int, session: Session = Depends(get_session)):
    movie = session.get(movieTitle, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    
    chapters = session.exec(select(chapterContent).where(chapterContent.movieId == movie_id)).all()
    for chapter in chapters:
        session.delete(chapter)
    session.delete(movie)
    session.commit()
    return {"ok": True}

@app.get("/movies/{movie_id}", response_model=movieTitle)
def get_movie(movie_id: int, session: Session = Depends(get_session)):
    movie = session.get(movieTitle, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie

@app.get("/movies/{movie_id}/chapters", response_model=List[chapterContent])
def get_movie_chapters(movie_id: int, session: Session = Depends(get_session)):
    return session.exec(select(chapterContent).where(chapterContent.movieId == movie_id).order_by(chapterContent.episodeNumber)).all()
    
@app.put("/chapters/{chapter_id}")
def update_chapter(chapter_id: int, chapter_data: ChapterUpdate, session: Session = Depends(get_session)):
    chapter = session.get(chapterContent, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    chapter.chapterTitle = chapter_data.chapterTitle
    chapter.chapterDetail = chapter_data.chapterDetail
    session.add(chapter)
    session.commit()
    session.refresh(chapter)
    return chapter

@app.get("/chapters/{chapter_id}", response_model=chapterContent)
def get_chapter(chapter_id: int, session: Session = Depends(get_session)):
    chapter = session.get(chapterContent, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    # print(f"T{chapter.chapterTitle}")
    # preview_content = chapter.chapterDetail[:100] + "..." if chapter.chapterDetail else "No Content"
    # print(f"{preview_content}")
    
    return chapter

# def process_text_with_ollama(text_input: str) -> str:
#     prompt = (
#         f"Correct the Thai vowel and tone mark encoding errors in the text below. Rules:\n"
#         f"1. Fix all 'sara-loi' (floating vowels) and misplaced tone marks to standard Thai grammar.\n"
#         f"2. Maintain the original meaning and writing style.\n"
#         f"3. CRITICAL: Output ONLY the corrected text. Do not include any introduction, preamble, notes, or conclusion."
#         f"--- my text ---\n"
#         f"{text_input}\n"
#         f"Output ONLY the result."
#     )
#     payload = { "model": OLLAMA_MODEL, "prompt": prompt, "stream": False }
#     try:
#         response = requests.post(
#             ollamaURL, 
#             headers={"Content-Type": "application/json"}, 
#             data=json.dumps(payload),
#             timeout=1500
#         )
#         response.raise_for_status() 
#         result = response.json()
#         return result['response'].strip()
#     except requests.exceptions.RequestException as e:
#         print(f"Error calling Ollama API: {e}")
#         raise HTTPException(status_code=500, detail=f"Failed to communicate with Ollama or Ollama failed to process: {e}. "f"Please check if Ollama is running and model '{OLLAMA_MODEL}' is installed.")

# @app.post("/process-pdf/")
# async def upload_and_process_pdf(file: UploadFile = File(...), start: int = Form(...), end: int = Form(...)):
#     if not file.filename.endswith(".pdf"):
#         raise HTTPException(status_code=400, detail="This is not a PDF file")
#     # start_time = time.perf_counter()
#     file_content = await file.read()
#     correctedPages = [] 
#     total_pages = 0
#     try:
#         with pdfplumber.open(io.BytesIO(file_content)) as pdf:
#             total_pages = len(pdf.pages)
#             if start < 1:
#                 raise HTTPException(status_code=400, detail="Start page must be at least 1")
#             if total_pages < end:
#                 raise HTTPException(status_code=400, detail=f"PDF has only {total_pages} pages")

#             for page_num in range(start, end + 1):
#                 page_index = page_num - 1     
#                 if 0 <= page_index < total_pages:
#                     raw_text = pdf.pages[page_index].extract_text()
                    
#                     if raw_text and raw_text.strip():
#                         cleanText = process_text_with_ollama(clean_thai_pdf_text(raw_text)) 
#                         print(cleanText, flush=True)
#                         correctedPages.append(cleanText)
#                     else:
#                         print(f"   >> Page {page_num} is empty or image only.", flush=True)
#                         correctedPages.append(f"--- Page {page_num} ---\n[Empty Page]\n")
#     except HTTPException as he:
#         raise he
#     except Exception as e:
#         print(f"ERROR: {e}", flush=True)
#         raise HTTPException(status_code=500, detail=f"PDF Error: {e}")
#     correctedChapter = "\n".join(correctedPages)
#     # duration = time.perf_counter() - start_time
#     # print(f"Total time use: {duration:.3f} seconds", flush=True)
#     return {
#         "filename": file.filename,
#         "pages_processed": f"{start}-{end}",
#         "corrected_text": correctedChapter
#     }

# @app.post("/map-chapters/")
# async def map_chapters(file: UploadFile = File(...), startChapter: int = Form(...), endChapter: int = Form(...)):
#     # start_time = time.perf_counter()
#     if not file.filename.endswith(".pdf"):
#         raise HTTPException(status_code=400, detail="This is not a PDF file")
#     file_content = await file.read()
#     found_chapters = [] 
#     currentChapter = None
#     currentStart = None
#     try:
#         with pdfplumber.open(io.BytesIO(file_content)) as pdf:
#             width = pdf.pages[0].width
#             height = pdf.pages[0].height # *0.1
#             for i, page in enumerate(pdf.pages):
#                 raw_text = page.extract_text()
#                 # raw_text = page.crop((0, 0, width, height)).extract_text()
#                 if not raw_text or not raw_text.strip():
#                     continue
                
#                 cleaned_text = clean_thai_pdf_text(raw_text)               
#                 # short_header = cleaned_text[:20].replace('\n', ' ')      
#                 # corrected_header = fix_header_with_ollama(short_header)
#                 match = re.search(r'ตอนท ี่\s*(\d+)', cleaned_text)
                
#                 if match:
#                     found_chap_num = int(match.group(1))
#                     # ถ้ามีตอนเก่าค้างอยู่ (เช่นเจอตอน 2 แล้วกำลังจะเริ่มตอน 2) -> ให้บันทึกตอนที่ 1
#                     if currentChapter is not None:
#                         found_chapters.append({
#                             "chapter": currentChapter,
#                             "start_page": currentStart,
#                             "end_page": i
#                         })
#                         # [จุดแก้ไขสำคัญ]: เช็คว่าตอนที่เพิ่งบันทึกจบไป ใช่ตอนสุดท้ายที่ต้องการไหม?
#                         if currentChapter >= endChapter:
#                             print(f"DEBUG: Found end of requested chapter {endChapter}. Stopping scan.", flush=True)
#                             currentChapter = None # Reset เพื่อไม่ให้ไปบันทึกซ้ำด้านล่าง
#                             break      
#                     # เริ่มต้น track ตอนใหม่ที่เพิ่งเจอ
#                     currentChapter = found_chap_num
#                     currentStart = i+1                
#                     # หา 500 เจอ 501
#                     if found_chap_num > endChapter:
#                         currentChapter = None
#                         break
#             # จัดการกรณีวนลูปจบเล่ม หรือ Break ออกมาแล้วยังมีตอนค้างอยู่ (กรณีตอนสุดท้ายของไฟล์)
#             if currentChapter is not None:
#                 # ตรวจสอบอีกครั้งว่าตอนที่ค้างอยู่ อยู่ใน range ที่ต้องการไหม
#                 if currentChapter <= endChapter:
#                     found_chapters.append({
#                         "chapter": currentChapter,
#                         "start_page": currentStart,
#                         "end_page": len(pdf.pages) 
#                     })
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Processing Error: {e}")
#     # Filter ผลลัพธ์ (เผื่อมีหลุดมา)
#     filtered_result = [
#         c for c in found_chapters 
#         if startChapter <= c['chapter'] <= endChapter
#     ]
#     if not filtered_result and found_chapters:
#         print("Warning: Chapters found but not in the requested range.")
#     # duration = time.perf_counter() - start_time
#     # print(f"Mapping finished in {duration:.3f} seconds")
#     return {
#         "chapters": filtered_result
#     }
    
@app.get("/")
def root():
    return "server is worked 111"

@app.get("/test")
def root():
    return "test test 222"

@app.post("/")
def root():
    return "test post 333"