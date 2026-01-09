from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import List
import requests
from fastapi.staticfiles import StaticFiles
import json
import io
import os
import time
import re
import fitz 
import httpx
from googletrans import Translator
import torch
from diffusers import StableDiffusionPipeline, StableDiffusionXLPipeline
from pythainlp.tag import NER

from database import create_db_and_tables, get_session
from models import movieTitle, chapterContent
import backprocess

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)
translator = Translator()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ollamaURL = "http://localhost:11434/api/generate"
extractModel = "scb10x/typhoon2.1-gemma3-12b:latest" 
transModel = "gemma2:9b"
stabilityModel = "C:\stability matrix\Data\Models\StableDiffusion\juggernautXL_ragnarokBy.safetensors"
app.mount("/static", StaticFiles(directory="public"), name="static")

class ChapterUpdate(BaseModel):
    chapterTitle: str
    chapterDetail: str
    
def clearASCII(text: str) -> str:
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
    clearedText = text
    for pua_char, std_char in replace_dict.items():
        clearedText = clearedText.replace(pua_char, std_char)
    return clearedText

def clearThaiTypeing(text: str) -> str:
    if not text:
        return ""
    corrections = {
        "เปิน": "เป็น",
        "เปญด": "เปิด",
        "ปฐ": "ปี",
        "ปญอม": "ป้อม",
        "ฝฐา": "ฝ่า",
        "ฝญก": "ฝึก",
        "ฝฐาย": "ฝ่าย",
        "ฝฐ": "ฝี",
        "ฟญน": "ฟืน",    
        "ฟญา": "ฟ้า",
        "เฟญง": "เฟิง",
    }
    fixed_text = text
    for wrong_word, correct_word in corrections.items():
        fixed_text = fixed_text.replace(wrong_word, correct_word)    
    return fixed_text

def clearNewline(text: str) -> str:
    def replacer(match):
        if " \n" in match.group():
            return "\n"
        return " "
    return re.sub(r"(?: \n)+|\n", replacer, text)

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
    start_time = time.perf_counter()
    file_content = await file.read()
    
    new_movie = movieTitle(movieTitle=title, episodeAmount=0, picPath="")
    session.add(new_movie)
    session.commit()
    session.refresh(new_movie) 
    
    try:
        found_chapters_data = []
        chapter_map = [] 

        with fitz.open(stream=file_content, filetype="pdf") as doc:
            total_pages = len(doc)
            for i, page in enumerate(doc):
                raw_text = page.get_text()
                if not raw_text or not raw_text.strip():
                    continue
                
                lines = raw_text.split('\n')
                
                for line in lines[:1]:
                    match = re.search(r'ตอนที่\s*(\d+)', line)
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
                    page = doc[p_idx]
                    page_text = clearASCII(page.get_text() or "")
                    page_text = clearThaiTypeing(page_text)
                    page_text = clearNewline(page_text)
                    if p_idx == start_p:
                        lines = page_text.split('\n')
                        header_found = False
                        
                        for line in lines:
                            if not header_found and re.search(r'ตอนที่\s*' + str(chap['num']), line):
                                title_match = re.search(r'ตอนที่\s*\d+\s*(.*)', line)
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
            print(f"Upload time use: {time.perf_counter()-start_time:.3f} seconds", flush=True)
            return {
                "status": "success",
                "movie_id": new_movie.id,
                "total_chapters_found": len(found_chapters_data),
                "chapters": [c.chapterTitle for c in found_chapters_data],
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

# หน้า chapter
@app.get("/movies/{movie_id}", response_model=movieTitle)
def get_movie(movie_id: int, session: Session = Depends(get_session)):
    movie = session.get(movieTitle, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie

# หน้า chapter
@app.get("/movies/{movie_id}/chapters", response_model=List[chapterContent])
def get_movie_chapters(movie_id: int, session: Session = Depends(get_session)):
    return session.exec(select(chapterContent).where(chapterContent.movieId == movie_id).order_by(chapterContent.episodeNumber)).all()#แก้ให้เอาแค่เกือบครบ

@app.get("/genPic/{chapterId}")
def genPic(chapterId: int, session: Session = Depends(get_session)):
    start = time.perf_counter()
    try:
        chapter = session.get(chapterContent, chapterId)
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")
        prompt = getattr(chapter, "chapterDetailEng", None)
        if not prompt:
            print("Warning: chapterDetailEng not found or empty, falling back to chapterTitle")
            prompt = chapter.chapterTitle
        
        if not prompt:
            print(f"Error: no promt for "+chapterId)
            raise HTTPException(status_code=500, detail=f"Error: no promt for "+chapterId)
            
        device = "cuda" if torch.cuda.is_available() else "cpu"
        torch_dtype = torch.float16 if device == "cuda" else torch.float32
        is_xl = "xl" in stabilityModel.lower()
        
        is_safetensors = stabilityModel.endswith(".safetensors")
        PipelineClass = StableDiffusionXLPipeline if is_xl else StableDiffusionPipeline

        ################################################ ช้าถ้าเลือก model ได้แล้วอย่าลืมดึงออกไปไว้ global
        pipe = PipelineClass.from_single_file(
            stabilityModel,
            use_safetensors=is_safetensors,
            torch_dtype=torch_dtype
        )
        ################################################
        
        if hasattr(pipe, "safety_checker"):
            pipe.safety_checker = None
        if hasattr(pipe, "requires_safety_checker"):
            pipe.requires_safety_checker = False
        if hasattr(pipe, "watermarker"):
            pipe.watermarker = None

        pipe.to(device)
        negative_prompt = "blurry, low quality, distorted, text, watermark"

        image = pipe(
            prompt=prompt, 
            negative_prompt=negative_prompt, 
            num_inference_steps=20,
            height=640, # 640/2
            width=1280  # 1280/2
        ).images[0]
        
        outputFilename = f"storage/thumbnail/{chapterId}.png"
        image.save("public/"+outputFilename)
        
        chapter.picPath = outputFilename
        session.add(chapter)
        session.commit()

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Processing Error: {str(e)}")

    print(f"genPic Time: {time.perf_counter() - start:.3f} seconds")
    return {"status": "success", "path": outputFilename}

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

# ข้อมูลทีละ chapter
@app.get("/chapters/{chapter_id}", response_model=chapterContent)
def get_chapter(chapter_id: int, session: Session = Depends(get_session)):
    chapter = session.get(chapterContent, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter

# @app.get("/tempReadPDF")
# def readddpdf(file_path: str = "คัมภีร์วิถีเซียน0001-0500.pdf"):
#     path = file_path.strip('"').strip("'") 
#     try:
#         result = ""
#         with fitz.open(path) as doc:
#             for page_num, page in enumerate(doc):
#                 if(page_num<=1):
#                     continue
#                 if(page_num>=7):
#                     break
#                 text = clearASCII(page.get_text() or "")
#                 text = clearThaiTypeing(text)
#                 result += text      
#         result=clearNewline(result)
#         return {result}

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"error: {str(e)}") 
    
# @app.get("/tempReadPDFnoClear")
# def readddpdf(file_path: str = "คัมภีร์วิถีเซียน0001-0500.pdf"):
#     path = file_path.strip('"').strip("'") 
#     try:
#         result = ""
#         with fitz.open(path) as doc:
#             for page_num, page in enumerate(doc):
#                 if(page_num<=1):
#                     continue
#                 if(page_num>=7):
#                     break
#                 text = clearASCII(page.get_text() or "")
#                 text = clearThaiTypeing(text)
#                 result += text      
#         return {result}

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"error: {str(e)}") 
    
async def processChunk(chunk_text: str, client: httpx.AsyncClient, extractModel: str):
    prompt = f"""
    Role
    คุณคือ AI Assistant ผู้เชี่ยวชาญด้านการสกัดข้อมูลภาพ (Visual Extraction) สำหรับงาน Generative AI

    Task
    อ่านข้อความที่ได้รับ แล้วสกัด Entity 3 ประเภท:
    1. Character (ตัวละคร)
    2. Location (สถานที่)
    3. Item (วัตถุสำคัญ)

    Requirements:
    - Name: ระบุชื่อหลัก (Main Name) ที่เป็นทางการที่สุด
    - Alt Names: ระบุชื่อเล่น ฉายา หรือชื่อเรียกอื่น (ถ้ามี) ใส่ใน List
    - Visual Tags: ขอเฉพาะคำนามหรือคำคุณศัพท์ที่ระบุรูปลักษณ์ (เช่น ผมแดง, ชุดเกราะ, เก่าแก่) ห้ามใส่คำกิริยาหรือการกระทำ (เช่น เดิน, กิน, พูด, ต่อสู้) คั่นด้วยคอมมา

    Output Format (JSON Only):
    {{
        "entities": [
            {{
                "type": "Character", 
                "name": "ชื่อหลัก",
                "altNames": ["ชื่อรอง1", "ชื่อรอง2"],
                "VisualTags": "tag1, tag2, tag3"
            }},
            {{
                "type": "Location",
                "name": "ชื่อสถานที่",
                "altNames": [],
                "VisualTags": "tag1, tag2"
            }}
        ]
    }}

    Input Text:
    {chunk_text}
    """

    payload = {
        "model": extractModel,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": 4096, 
            "temperature": 0.5
        },
        "format": "json"
    }

    try:
        response = await client.post(ollamaURL, json=payload)
        response.raise_for_status()
        result_text = response.json().get("response", "")
        
        cleaned_text = result_text.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_text)
    except Exception as e:
        return None

@app.get("/extractEntities/{chapter_id}")
async def extract_entities2(chapter_id: int, session: Session = Depends(get_session)):
    start = time.perf_counter()
    
    chapter_obj = session.get(chapterContent, chapter_id)
    if not chapter_obj or not chapter_obj.chapterDetail:
        return {"result": "No content found in this chapter."}  
    
    chapterDetail = chapter_obj.chapterDetail
    lines = chapterDetail.split('\n')
    total_lines = len(lines)
    
    if total_lines < 10:
        chunks = [chapterDetail]
    else:
        chunk_size = (total_lines + 9) // 10
        overlap = 2
        step = max(1, chunk_size - overlap)
        chunks = []
        for i in range(0, total_lines, step):
            chunk_lines = lines[i:i + chunk_size]
            chunk_text = "\n".join(chunk_lines)
            chunks.append(chunk_text)
            if i + chunk_size >= total_lines:
                break
            
    print(f"{len(chunks)} chunks")
    results = []
    
    async with httpx.AsyncClient(timeout=1800.0) as client:
        for idx, chunk in enumerate(chunks):
            print(idx)
            print(len(chunk))
            res = await processChunk(chunk, client, extractModel)
            results.append(res)

    merged_entities = {}
    for res in results:
        if not res or not res.get("entities"):
            continue
        
        for entity in res["entities"]:
            e_type = entity.get("type")
            name = entity.get("name")
            
            if not e_type or not name:
                continue
                
            e_type = e_type.strip().capitalize() 
            name = name.strip()
            key = (e_type, name)
            
            current_tags_input = entity.get("VisualTags")
            if current_tags_input is None:
                current_tags = set()
            elif isinstance(current_tags_input, list): 
                current_tags = set(t.strip() for t in current_tags_input if t.strip())
            else:
                current_tags = set(t.strip() for t in str(current_tags_input).split(",") if t.strip())

            current_alts_input = entity.get("altNames")
            if current_alts_input is None:
                current_alts = set()
            elif isinstance(current_alts_input, list):
                current_alts = set(current_alts_input)
            else:
                current_alts = set([str(current_alts_input)])

            if key not in merged_entities:
                merged_entities[key] = {
                    "type": e_type,
                    "name": name,
                    "altNames": current_alts, 
                    "VisualTags": current_tags
                }
            else:
                merged_entities[key]["VisualTags"].update(current_tags)
                merged_entities[key]["altNames"].update(current_alts)

    final_output = {
        "characters": [],
        "locations": [],
        "items": []
    }

    for key, data in merged_entities.items():
        data["VisualTags"] = ", ".join(sorted(list(data["VisualTags"])))
        data["altNames"] = sorted(list(data["altNames"]))
        
        e_type_lower = data["type"].lower()
        
        if "character" in e_type_lower:
            final_output["characters"].append(data)
        elif "location" in e_type_lower:
            final_output["locations"].append(data)
        elif "item" in e_type_lower:
            final_output["items"].append(data)
        else:
            final_output["items"].append(data)
    print(f"Time: {time.perf_counter() - start:.3f} seconds")
    return final_output

# -----------------------------------------------------------------

@app.post("/movies/{movie_id}/process-rag")
async def trigger_rag(
    movie_id: int, 
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    movie = session.get(movieTitle, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    
    # ส่งงานไปให้ backprocess ทำ
    movie.status = "processing"
    session.add(movie)
    session.commit()
    
    background_tasks.add_task(backprocess.process_movie_background, movie_id)
    
    return {"status": "started", "message": "Wobackprocessrker is processing in background"}

import base64
SD_API_URL = "http://127.0.0.1:7860/sdapi/v1/txt2img"

SD_MODEL_CHECKPOINT = "juggernautXL_ragnarokBy.safetensors"

STORAGE_DIR = "storage/thumbnail"
os.makedirs(STORAGE_DIR, exist_ok=True)

def generate_image_internal(prompt: str, output_filename: str):
    start = time.perf_counter()
    
    payload = {
        "prompt": prompt,
        "negative_prompt": "blurry, low quality, distorted, text, watermark, bad anatomy, bad hands, lowres, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, username",
        "steps": 25,                # จำนวนรอบ (20-30 กำลังดี)
        "sampler_name": "Euler a",  # Sampler มาตรฐาน เร็วและสวย
        "width": 1024,              # [Updated] ปรับเป็น 1024 เพราะ JuggernautXL เป็น SDXL
        "height": 1024,
        "cfg_scale": 7,             # ความเชื่อฟัง Prompt (7 คือค่ามาตรฐาน)
        "batch_size": 1,
        
        # [NEW] บังคับให้ WebUI สลับไปใช้ Model นี้
        "override_settings": {
            "sd_model_checkpoint": SD_MODEL_CHECKPOINT
        },
        "override_settings_restore_afterwards": False # True=ใช้เสร็จกลับเป็นตัวเดิม, False=เปลี่ยนแล้วเปลี่ยนเลย
    }

    try:
        # 1. ยิง API Request
        response = requests.post(SD_API_URL, json=payload, timeout=120) # timeout เผื่อเครื่องช้า
        
        if response.status_code == 200:
            r = response.json()
            
            # API จะส่งรูปกลับมาเป็น Base64 String ใน r['images'][0]
            image_b64 = r['images'][0]
            
            # 2. แปลง Base64 กลับเป็นไฟล์รูปภาพ
            save_path = os.path.join(STORAGE_DIR, output_filename)
            
            with open(save_path, "wb") as f:
                f.write(base64.b64decode(image_b64))
            
            duration = time.perf_counter() - start
            print(f"✅ Generated & Saved to {save_path} in {duration:.2f}s")
            return save_path
            
        else:
            print(f"❌ SD API Error: {response.status_code} - {response.text}")
            raise Exception(f"SD API Error: {response.status_code}")

    except requests.exceptions.ConnectionError:
        print("❌ Connection Refused: ตรวจสอบว่า Stability Matrix เปิดอยู่และใส่ --api แล้วหรือยัง")
        raise Exception("Cannot connect to Stability Matrix (Is it running?)")
        
    except Exception as e:
        print(f"❌ Gen Image Error: {e}")
        raise e
    
@app.get("/")
def root():
    return "server is worked 111"

@app.get("/test")
def root():
    return "test test 222"

@app.post("/")
def root():
    return "test post 333"