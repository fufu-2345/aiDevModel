from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import List
import requests
from fastapi.staticfiles import StaticFiles
import json
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

import re

def clearNewline(text: str) -> str:
    def replacer(match):
        found = match.group()
        if found.count('\n') > 1:
            return '\n'
        if ' \n' in found:
            return '\n'
        return ' '
    pattern = r"[ ]*\n[ \n]*"
    return re.sub(pattern, replacer, text).strip()

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
    
# ----------------------------------------------- Entity

async def processChunk(chunk_text: str, client: httpx.AsyncClient, extractModel: str):
    prompt = f"""
    Role:
    คุณคือ AI Visual Director ผู้เชี่ยวชาญด้านการถอดรหัสภาพจากนิยายเพื่อนำไปสร้างภาพประกอบ

    Task:
    อ่านข้อความ Input Text แล้วสกัดข้อมูล Entity (Character, Location, Item) ออกมาเป็น JSON

    ต้องแยกคุณลักษณะออกเป็น 2 ส่วนให้ชัดเจน:
    1. "IdentityTags": ลักษณะทางกายภาพที่ติดตัว เปลี่ยนแปลงยาก (เช่น สีผม, สีตา, ทรงผมหลัก, สีผิว, เพศ, รูปร่าง, อายุ, เผ่าพันธุ์)
    2. "ModifierTags": สิ่งที่เปลี่ยนแปลงได้ตามสถานการณ์ (เช่น เสื้อผ้า, เครื่องประดับ, คราบเลือด, รอยเปื้อน, อารมณ์, ท่าทาง)
    **Important Rule:** หากมีหลายรูปลักษณ์ ให้ยึด "รูปลักษณ์แรก" ที่ปรากฏ

    Requirements:
    - Name: ชื่อหลักที่เป็นทางการ ภาษาไทย
    - AltNames: ชื่อเล่น หรือฉายา ภาษาไทย (ถ้ามี)
    - Visual Tags: ขอเฉพาะคำนามหรือคำคุณศัพท์ที่ระบุรูปลักษณ์ (เช่น ผมแดง, ชุดเกราะ, เก่าแก่) ห้ามใส่คำกิริยาหรือการกระทำ (เช่น เดิน, กิน, พูด, ต่อสู้) คั่นด้วยคอมมา 
    
    Output Format (JSON Only):
    {{
        "entities": [
            {{
                "type": "Character", 
                "name": "ชื่อตัวละคร",
                "altNames": ["ชื่อเรียกอื่น"],
                "IdentityTags": "tag1, tag2", 
                "ModifierTags": "tag1, tag2"
            }},
            {{
                "type": "Location",
                "name": "ชื่อสถานที่",
                "altNames": [],
                "VisualTags": "tag1, tag2"
            }},
            {{
                "type": "Item",
                "name": "ชื่อวัตถุ",
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
            "temperature": 0.75
        },
        "format": "json"
    }

    print(len(prompt))
    try:
        response = await client.post(ollamaURL, json=payload)
        response.raise_for_status()
        result_text = response.json().get("response", "")
        
        cleaned_text = result_text.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_text)
    except Exception as e:
        return None

def parse_tags_to_set(tag_input):
    if not tag_input:
        return set()
    if isinstance(tag_input, list):
         return set(t.strip() for t in tag_input if t.strip() and isinstance(t, str))
    
    tag_str = str(tag_input)
    return set(t.strip() for t in tag_str.split(",") if t.strip())

@app.get("/extractEntities/{chapter_id}")
async def extract_entities2(chapter_id: int, session: Session = Depends(get_session)):
    start = time.perf_counter()
    chapter_obj = session.get(chapterContent, chapter_id)
    if not chapter_obj or not chapter_obj.chapterDetail:
        return {"result": "No content found."}
    
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
            
    results = []

    async with httpx.AsyncClient(timeout=1800.0) as client:
        for idx, chunk in enumerate(chunks):
            print(f"{idx+1}")
            res = await processChunk(chunk, client, extractModel) 
            if res:
                results.append(res)
            else:
                print(f"Chunk {idx+1} err")
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
            current_alts_input = entity.get("altNames")
            current_alts = set()
            if current_alts_input:
                if isinstance(current_alts_input, list):
                    current_alts = set(str(a).strip() for a in current_alts_input if str(a).strip())
                else:
                    current_alts = set([str(current_alts_input).strip()])
            if key not in merged_entities:
                merged_entities[key] = {
                    "type": e_type,
                    "name": name,
                    "altNames": set(),
                    "VisualTags": set(),    
                    "IdentityTags": set(),   
                    "ModifierTags": set()   
                }
            merged_entities[key]["altNames"].update(current_alts)
            if "Character" in e_type:
                i_set = parse_tags_to_set(entity.get("IdentityTags"))
                m_set = parse_tags_to_set(entity.get("ModifierTags"))
                merged_entities[key]["IdentityTags"].update(i_set)
                merged_entities[key]["ModifierTags"].update(m_set)
            else:
                v_set = parse_tags_to_set(entity.get("VisualTags"))
                merged_entities[key]["VisualTags"].update(v_set)
    final_output = {
        "characters": [],
        "locations": [],
        "items": []
    }
    for key, data in merged_entities.items():
        data["altNames"] = sorted(list(data["altNames"]))
        e_type_lower = data["type"].lower()
        if "character" in e_type_lower:
            data["IdentityTags"] = ", ".join(sorted(list(data["IdentityTags"])))
            data["ModifierTags"] = ", ".join(sorted(list(data["ModifierTags"])))
            data.pop("VisualTags", None) 
            final_output["characters"].append(data)
        else:
            data["VisualTags"] = ", ".join(sorted(list(data["VisualTags"])))
            data.pop("IdentityTags", None)
            data.pop("ModifierTags", None)
            
            if "location" in e_type_lower:
                final_output["locations"].append(data)
            else:
                final_output["items"].append(data)
    print(f"Time: {time.perf_counter() - start:.3f} seconds")
    return final_output

# -----------------------------------------------------------------

CHUNK_SIZE_LIMIT = 1500 
SLEEP_BETWEEN_CHUNKS = 1

class StoryRequest(BaseModel):
    text: str
    chunk_size: Optional[int] = DEFAULT_CHUNK_SIZE

class SceneResult(BaseModel):
    chunk_id: int
    thai_text: str
    english_text: str
    sd_prompt: str
    error: Optional[str] = None

# ==========================================
# Helper Functions
# ==========================================
def smart_chunker(text: str, max_length: int) -> List[str]:
    """
    แบ่งข้อความเป็น chunk โดยตัดที่ 'ย่อหน้า' (\n)
    """
    paragraphs = text.split('\n')
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
            
        if len(current_chunk) + len(para) <= max_length:
            current_chunk += para + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = para + "\n\n"
    
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    return chunks

# ==========================================
# API Endpoints
# ==========================================
@app.post("/generate-prompts", response_model=List[SceneResult])
def generate_prompts(request: StoryRequest):
    """
    รับ Text นิยาย -> ตัดแบ่ง -> แปล -> สร้าง Prompt ด้วย Ollama
    """
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    translator = Translator()
    
    # 1. แบ่ง Text เป็น Chunk
    print(f"✂️  Splitting text... (Limit: {request.chunk_size})")
    chunks = smart_chunker(request.text, request.chunk_size)
    print(f"📦 Total Chunks: {len(chunks)}")
    
    final_results = []

    for index, chunk in enumerate(chunks):
        print(f"--- Processing Chunk {index + 1}/{len(chunks)} ---")
        chunk_result = SceneResult(
            chunk_id=index + 1,
            thai_text=chunk,
            english_text="",
            sd_prompt=""
        )
        
        try:
            # 2. แปลไทยเป็นอังกฤษ
            translation = translator.translate(chunk, src='th', dest='en')
            english_text = translation.text
            chunk_result.english_text = english_text
            
            # 3. ใช้ Ollama สกัด Visual Description
            system_prompt = (
                "You are an expert AI art director for Stable Diffusion. "
                "Read the following story segment. "
                "Describe the SINGLE most important visual scene that represents this segment. "
                "Focus on: Character appearance, Environment/Background, Lighting, and Art Style. "
                "Format output as a comma-separated Stable Diffusion prompt list. "
                "Do NOT include explanation, just the prompt tags."
            )
            
            response = ollama.chat(model=OLLAMA_MODEL, messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': f"Story segment: {english_text}"},
            ])
            
            chunk_result.sd_prompt = response['message']['content']
            
            # พักกันโดน Google Block
            time.sleep(SLEEP_BETWEEN_CHUNKS)

        except Exception as e:
            print(f"❌ Error: {str(e)}")
            chunk_result.error = str(e)
            chunk_result.sd_prompt = "Error generating prompt"

        final_results.append(chunk_result)

    return final_results

# --------------------------------------------------------------

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