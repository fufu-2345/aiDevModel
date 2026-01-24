from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Depends, BackgroundTasks, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import List
from fastapi.staticfiles import StaticFiles
import asyncio
import requests
import json
import os
import time
import gc
import re
import fitz 
import httpx
from googletrans import Translator
import torch
from diffusers import StableDiffusionPipeline, StableDiffusionXLPipeline
from pythainlp.tag import NER
from services import save_extraction_result

from database import create_db_and_tables, get_session
from models import movieTitle, chapterContent, character, altCharacter, entity, altEntity

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
extractModel = "gemma3:12b"
transModel = "gemma3:4b"
stabilityModel = "C:\\stability matrix\\Data\\Models\\StableDiffusion\\juggernautXL_ragnarokBy.safetensors"
lora = r"C:\stability matrix\Data\Models\Lora\Wuxia-PONY-PAseer.safetensors"
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
        found = match.group()
        if found.count('\n') > 1:
            return '\n'
        if ' \n' in found:
            return '\n'
        return ' '
    pattern = r"[ ]*\n[ \n]*"
    return re.sub(pattern, replacer, text).strip()

def parse_tags_to_set(tags_input):
    if not tags_input:
        return set()
    if isinstance(tags_input, str):
        return set(t.strip() for t in tags_input.split(',') if t.strip())
    return set()

def load_image_pipe():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch_dtype = torch.float16 if device == "cuda" else torch.float32
    is_xl = "xl" in stabilityModel.lower()
    is_safetensors = stabilityModel.endswith(".safetensors")
    PipelineClass = StableDiffusionXLPipeline if is_xl else StableDiffusionPipeline
    
    if is_safetensors:
            pipe = PipelineClass.from_single_file(
            stabilityModel,
            use_safetensors=True,
            torch_dtype=torch_dtype
        )
    else:
        pipe = PipelineClass.from_pretrained(
            stabilityModel,
            torch_dtype=torch_dtype,
            use_safetensors=True
        )

    if hasattr(pipe, "safety_checker"):
        pipe.safety_checker = None
    if hasattr(pipe, "requires_safety_checker"):
        pipe.requires_safety_checker = False
    if hasattr(pipe, "watermarker"):
        pipe.watermarker = None
        
    pipe.to(device)    
    pipe.load_lora_weights(lora)
    return pipe

def generate_images_for_missing_refpaths(session: Session, movie_id: int):
    print(f"🎨 Starting Image Generation for Movie ID: {movie_id}")
    
    # 1. Fetch Characters with empty refpath
    char_statement = select(character).where(
        character.movieId == movie_id,
        (character.refpath == "") | (character.refpath == None)
    )
    chars_to_gen = session.exec(char_statement).all()

    # 2. Fetch Entities (Locations/Items) with empty refpath
    ent_statement = select(entity).where(
        entity.movieId == movie_id,
        (entity.refpath == "") | (entity.refpath == None)
    )
    ents_to_gen = session.exec(ent_statement).all()

    if not chars_to_gen and not ents_to_gen:
        print("✨ No missing images found.")
        return

    pipeline = None
    try:
        pipeline = load_image_pipe()
    except Exception as e:
        print(f"❌ Failed to load Image Pipeline: {e}")
        return
    
    os.makedirs("public/storage/characters", exist_ok=True)
    os.makedirs("public/storage/entities", exist_ok=True)

    try:
        for char_obj in chars_to_gen:
            try:
                desc = f"{char_obj.IdentityTags}, {char_obj.ModifierTags}"
                prompt = f"ancient chinese style, {desc}, front view, full body shot:1.3, looking directly at camera, neutral expression, soft studio lighting, no shadows on face, high quality, simple white background"
                negative_prompt = "shadows, harsh lighting, cropped, cinematic lighting, hands on face, distorted face, profile view, looking away, busy background, blurry, low quality, nsfw"
                
                print(f"Generating Character: {char_obj.name}...")
                image = pipeline(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=20,
                    height=832, 
                    width=1216,
                    guidance_scale=7.0
                ).images[0]
                
                filename = f"storage/characters/{char_obj.id}.png"
                image.save(f"public/{filename}")
                
                char_obj.refpath = filename
                session.add(char_obj)
                session.commit() 
            except Exception as e:
                print(f"❌ Error generating character {char_obj.name}: {e}")

        for ent_obj in ents_to_gen:
            try:
                desc = ent_obj.visual_tags
                e_type_lower = ent_obj.type.lower()
                
                if "item" in e_type_lower:
                    prompt = f"ancient chinese style object, {desc}, product photography, centered shot, isolated on white background, studio lighting, soft shadows, high detail, 8k, sharp focus, realistic texture, professional lighting"
                    negative_prompt = "human, hands, holding, fingers, person, messy background, text, watermark, blurry, low quality, distortion, nsfw, cropped, out of frame"
                else: # Location
                    prompt = f"ancient chinese architecture, {desc}, establishing shot, wide angle view, highly detailed, realistic, 8k, cinematic lighting, depth of field, interior design, atmosphere, sharp focus"
                    negative_prompt = "people, crowd, humans, animals, text, watermark, blurry, low quality, distortion, simple background, white background, flat lighting"

                print(f"Generating Entity ({ent_obj.type}): {ent_obj.name}...")
                image = pipeline(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=25,
                    height=1024, 
                    width=1024,
                    guidance_scale=7.0
                ).images[0]
                
                # บันทึกเป็น storage/entities/{id}.png
                filename = f"storage/entities/{ent_obj.id}.png"
                image.save(f"public/{filename}")
                
                # Save path ลง DB
                ent_obj.refpath = filename
                session.add(ent_obj)
                session.commit()
            except Exception as e:
                print(f"❌ Error generating entity {ent_obj.name}: {e}")
                
    finally:
        # Cleanup memory
        print("🧹 Cleaning up model from memory...")
        if pipeline:
            del pipeline
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("✅ RAM Freed.")

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
        print(device)
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

# async def processChunk(chunk_text: str, client: httpx.AsyncClient, extractModel: str):
#     prompt = f"""
#     Role:
#     คุณคือ AI Visual Director ผู้เชี่ยวชาญด้านการถอดรหัสภาพจากนิยายเพื่อนำไปสร้างภาพประกอบ

#     Task:
#     อ่านข้อความ Input Text แล้วสกัดข้อมูล Entity (Character, Location, Item) ออกมาเป็น JSON

#     ต้องแยกคุณลักษณะออกเป็น 2 ส่วนให้ชัดเจน:
#     1. "IdentityTags": ลักษณะทางกายภาพที่ติดตัว เปลี่ยนแปลงยาก (เช่น สีผม, สีตา, ทรงผมหลัก, สีผิว, เพศ, รูปร่าง, อายุ, เผ่าพันธุ์)
#     2. "ModifierTags": สิ่งที่เปลี่ยนแปลงได้ตามสถานการณ์ (เช่น เสื้อผ้า, เครื่องประดับ, คราบเลือด, รอยเปื้อน, อารมณ์, ท่าทาง)
#     **Important Rule:** หากมีหลายรูปลักษณ์ ให้ยึด "รูปลักษณ์แรก" ที่ปรากฏ

#     Requirements:
#     - Name: ชื่อหลักที่เป็นทางการ ภาษาไทย
#     - AltNames: ชื่อเล่น หรือฉายา ภาษาไทย (ถ้ามี)
#     - Visual Tags: ขอเฉพาะคำนามหรือคำคุณศัพท์ที่ระบุรูปลักษณ์ (เช่น ผมแดง, ชุดเกราะ, เก่าแก่) ห้ามใส่คำกิริยาหรือการกระทำ (เช่น เดิน, กิน, พูด, ต่อสู้) คั่นด้วยคอมมา 
    
#     Output Format (JSON Only):
#     {{
#         "entities": [
#             {{
#                 "type": "Character", 
#                 "name": "ชื่อตัวละคร",
#                 "altNames": ["ชื่อเรียกอื่น"],
#                 "IdentityTags": "tag1, tag2", 
#                 "ModifierTags": "tag1, tag2"
#             }},
#             {{
#                 "type": "Location",
#                 "name": "ชื่อสถานที่",
#                 "altNames": [],
#                 "VisualTags": "tag1, tag2"
#             }},
#             {{
#                 "type": "Item",
#                 "name": "ชื่อวัตถุ",
#                 "altNames": [],
#                 "VisualTags": "tag1, tag2"
#             }}
#         ]
#     }}

#     Input Text:
#     {chunk_text}
#     """

#     payload = {
#         "model": extractModel,
#         "prompt": prompt,
#         "stream": False,
#         "options": {
#             "num_ctx": 4096, 
#             "temperature": 0.75
#         },
#         "format": "json"
#     }

#     print(len(prompt))
#     try:
#         response = await client.post(ollamaURL, json=payload)
#         response.raise_for_status()
#         result_text = response.json().get("response", "")
        
#         cleaned_text = result_text.replace("```json", "").replace("```", "").strip()
#         return json.loads(cleaned_text)
#     except Exception as e:
#         return None

def parse_tags_to_set(tag_input):
    if not tag_input:
        return set()
    if isinstance(tag_input, list):
        return set(t.strip() for t in tag_input if t.strip() and isinstance(t, str))
    
    tag_str = str(tag_input)
    return set(t.strip() for t in tag_str.split(",") if t.strip())

async def processChunk(chunk_text: str, client: httpx.AsyncClient, extractModel: str):
    prompt = f"""
    Role:
    You are an AI Visual Director.

    Task:
    Extract Entity information (Character, Location, Item) from the Input Text into a valid JSON format.

    Rules:
    1. "IdentityTags": Fixed physical traits (hair color, eye color, race, gender).
    2. "ModifierTags": Changeable traits (clothing, emotions, dirt, poses).
    3. Use the "first appearance" for changing traits.
    4. Tags must be nouns/adjectives only. No verbs.
    5. English output only.

    Output JSON Format:
    {{
        "entities": [
            {{
                "type": "Character",
                "name": "Name",
                "altNames": [],
                "IdentityTags": "tag1, tag2",
                "ModifierTags": "tag1, tag2"
            }},
            {{
                "type": "Location",
                "name": "Name",
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
        match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if match:
            json_str = match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                try:
                    corrected = re.sub(r',\s*([\]}])', r'\1', json_str)
                    return json.loads(corrected)
                except:
                    print(f"JSON Broken: {result_text[:50]}...")
                    return None
        else:
            print("No JSON found in response.")
            return None

    except Exception as e:
        print(f"Process Error: {e}")
        return None

@app.get("/extractEntities/{chapter_id}")
async def extract_entities(chapter_id: int, session: Session = Depends(get_session)):
    start = time.perf_counter()
    chapter_obj = session.get(chapterContent, chapter_id)
    if not chapter_obj or not chapter_obj.chapterDetail:
        return {"result": "No content found."}
    
    current_movie_id = chapter_obj.movieId
    
    chapterDetail = chapter_obj.chapterDetail
    lines = chapterDetail.split('\n')
    total_lines = len(lines)
    
    LINES_PER_CHUNK = 10  
    OVERLAP = 3          
    
    chunks = []
    if total_lines <= LINES_PER_CHUNK:
        chunks = [chapterDetail]
    else: 
        step = LINES_PER_CHUNK - OVERLAP
        for i in range(0, total_lines, step):
            chunk_lines = lines[i : i + LINES_PER_CHUNK]
            if len(chunk_lines) < 3 and len(chunks) > 0:
                break
            chunk_text = "\n".join(chunk_lines)
            chunks.append(chunk_text)

    results = []
    translator = Translator()

    async with httpx.AsyncClient(timeout=1800.0) as client:
        for idx, chunk in enumerate(chunks):
            print(f"Chunk {idx+1}/{len(chunks)} (Length: {len(chunk)} chars)")
            translator = Translator()
            await asyncio.sleep(1) 

            text_to_process = chunk
            try:
                translated = await translator.translate(chunk, src='th', dest='en')
                if translated and translated.text:
                    text_to_process = translated.text
            except Exception as e:
                print(f"Trans Warning Ch {idx+1}: {e}")

            res = await processChunk(text_to_process, client, extractModel) 
            if res:
                results.append(res)
            else:
                print(f"Chunk {idx+1} Failed")

    merged_entities = {}
    for res in results:
        if not res or not res.get("entities"):
            continue
        for entity_item in res["entities"]:
            e_type = entity_item.get("type")
            name = entity_item.get("name")
            if not e_type or not name:
                continue   
            e_type = e_type.strip().capitalize() 
            name = name.strip()
            key = (e_type, name)
            
            current_alts_input = entity_item.get("altNames")
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
                i_set = parse_tags_to_set(entity_item.get("IdentityTags"))
                m_set = parse_tags_to_set(entity_item.get("ModifierTags"))
                merged_entities[key]["IdentityTags"].update(i_set)
                merged_entities[key]["ModifierTags"].update(m_set)
            else:
                v_set = parse_tags_to_set(entity_item.get("VisualTags"))
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

    print(f"Extract Entities Time: {time.perf_counter() - start:.3f} seconds")

    # Save to Database
    try:
        saved_status = save_extraction_result(session, chapter_id, final_output)
        if saved_status:
            print("✅ Data successfully saved/updated in Database.")
        else:
            print("⚠️ Failed to save data to Database.")
    except Exception as e:
        print(f"❌ Error saving to database: {e}")

    # ------------------------------------------------------------------
    # POST-PROCESSING: Generate Images for Missing Refpaths
    # ------------------------------------------------------------------
    if current_movie_id:
        print("💤 Sleeping 1 sec before image generation...")
        await asyncio.sleep(1)
        try:
            generate_images_for_missing_refpaths(session, current_movie_id)
        except Exception as e:
            print(f"❌ Error during image generation: {e}")

    return final_output

# -----------------------------------------------------------------
# -----------------------------------------------------------------
# -----------------------------------------------------------------

CHUNK_SIZE_LIMIT = 1000 
SLEEP_BETWEEN_CHUNKS = 1
DEFAULT_CHUNK_SIZE = 600.0

def smart_chunker(text: str, max_length: int) -> List[str]:
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

def clean_json_string(json_str: str) -> str:
    """
    ฟังก์ชันช่วยทำความสะอาด String ก่อนแปลงเป็น JSON
    (เผื่อ AI ตอบมามี markdown ```json ... ``` ติดมาด้วย)
    """
    pattern = r"```json(.*?)```"
    match = re.search(pattern, json_str, re.DOTALL)
    if match:
        return match.group(1).strip()
    return json_str.strip()

def call_ollama_via_http(prompt_text: str, model: str) -> str:
    system_prompt = (
        "You are an expert AI art director and Named Entity Recognition (NER) system. "
        "Analyze the following story segment. "
        "Perform two tasks:\n"
        "1. Generate 'visual_tags': A comma-separated Stable Diffusion prompt describing the scene visually (lighting, environment, style, character appearance).\n"
        "2. Extract 'entities': A list of specific names of characters (e.g., 'Alice', 'John') or unique named items present in the segment.\n\n"
        "IMPORTANT: You MUST return ONLY a raw JSON object. Do not add any markdown formatting or explanation.\n"
        "JSON Format example: { \"visual_tags\": \"1girl, sitting, cafe, sunset\", \"entities\": [\"Alice\"] }"
    )

    payload = {
        "model": model,
        "prompt": f"Story segment: {prompt_text}",
        "system": system_prompt,
        "stream": False,
        "format": "json"
    }
    try:
        response = requests.post(
            ollamaURL, 
            json=payload, 
            timeout=DEFAULT_CHUNK_SIZE
        )
        response.raise_for_status() 
        result_json = response.json()
        raw_response = result_json['response']
        try:
            cleaned_response = clean_json_string(raw_response)
            parsed_data = json.loads(cleaned_response)
            
            return {
                "visual_tags": parsed_data.get("visual_tags", ""),
                "entities": parsed_data.get("entities", [])
            }
        except json.JSONDecodeError:
            print(f"⚠️ JSON Parse Error. Raw: {raw_response}")
            return {
                "visual_tags": raw_response,
                "entities": []
            }
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Ollama Connection Error: {e}")
        raise e

from transformers import pipeline
@app.get("/extractEntities2/{chapter_id}")
async def extract_entities_2(chapter_id: int, session: Session = Depends(get_session)):
    start = time.perf_counter()
    
    # ดึงข้อมูล Chapter
    chapter_obj = session.get(chapterContent, chapter_id)
    if not chapter_obj or not chapter_obj.chapterDetail:
        return {"result": "No content found."}
    
    chapterDetail = chapter_obj.chapterDetail
    
    # ---------------------------------------------------------
    # PART 1: LOAD TRANSLATION MODEL LOCALLY (ภายใน Function)
    # ---------------------------------------------------------
    print("⏳ Loading Translation Model (TH -> EN)...")
    try:
        # ใช้ asyncio.to_thread เพราะการโหลด Model เป็น Blocking I/O
        # Model ที่แนะนำ: Helsinki-NLP/opus-mt-th-en (เล็กและเร็ว)
        translator_pipe = await asyncio.to_thread(
            pipeline, 
            "translation", 
            model="Helsinki-NLP/opus-mt-th-en"
        )
        print("✅ Model Loaded.")
    except Exception as e:
        print(f"❌ Failed to load model: {e}")
        return {"error": "Translation model failed to load"}

    # ---------------------------------------------------------
    # PART 2: PREPARE CHUNKS
    # ---------------------------------------------------------
    lines = chapterDetail.split('\n')
    total_lines = len(lines)
    
    LINES_PER_CHUNK = 10  
    OVERLAP = 3          
    
    chunks = []
    if total_lines <= LINES_PER_CHUNK:
        chunks = [chapterDetail]
    else: 
        step = LINES_PER_CHUNK - OVERLAP
        for i in range(0, total_lines, step):
            chunk_lines = lines[i : i + LINES_PER_CHUNK]
            if len(chunk_lines) < 3 and len(chunks) > 0:
                break
            chunk_text = "\n".join(chunk_lines)
            chunks.append(chunk_text)

    # ---------------------------------------------------------
    # PART 3: PROCESS LOOP
    # ---------------------------------------------------------
    results = []
    extractModel = "llama3" # หรือ model ที่คุณใช้
    ollamaURL = "http://localhost:11434/api/generate" # URL ของ Ollama

    async with httpx.AsyncClient(timeout=1800.0) as client:
        for idx, chunk in enumerate(chunks):
            print(f"Processing Chunk {idx+1}/{len(chunks)} (Len: {len(chunk)})")
            
            # --- Translation Phase (Local Pipe) ---
            text_to_process = chunk
            try:
                # รัน Pipeline ใน Thread แยก เพื่อไม่ให้ Server ค้าง
                translated_output = await asyncio.to_thread(translator_pipe, chunk)
                # Pipeline return เป็น list ของ dict: [{'translation_text': '...'}]
                if translated_output and isinstance(translated_output, list):
                    text_to_process = translated_output[0].get('translation_text', chunk)
            except Exception as e:
                print(f"⚠️ Translation Warning Ch {idx+1}: {e}")
                # ถ้าแปลไม่ได้ ให้ใช้ text เดิม (ภาษาไทย) ส่งไปเสี่ยงดวง

            # --- Extraction Phase (Ollama) ---
            res = await processChunk(text_to_process, client, extractModel, ollamaURL) 
            if res:
                results.append(res)
            else:
                print(f"Chunk {idx+1} Failed to extract JSON")

    # ---------------------------------------------------------
    # PART 4: MERGE LOGIC
    # ---------------------------------------------------------
    merged_entities = {}
    for res in results:
        if not res or not res.get("entities"):
            continue
        for entity_item in res["entities"]:
            e_type = entity_item.get("type")
            name = entity_item.get("name")
            
            if not e_type or not name:
                continue   
            
            e_type = e_type.strip().capitalize() 
            name = name.strip()
            # ใช้ Tuple (Type, Name) เป็น Key เพื่อป้องกันชื่อซ้ำแต่คนละประเภท
            key = (e_type, name)
            
            # Handle AltNames
            current_alts_input = entity_item.get("altNames")
            current_alts = set()
            if current_alts_input:
                if isinstance(current_alts_input, list):
                    current_alts = set(str(a).strip() for a in current_alts_input if str(a).strip())
                else:
                    current_alts = set([str(current_alts_input).strip()])
            
            # Init Dict structure if new
            if key not in merged_entities:
                merged_entities[key] = {
                    "type": e_type,
                    "name": name,
                    "altNames": set(),
                    "VisualTags": set(),    
                    "IdentityTags": set(),   
                    "ModifierTags": set()   
                }
            
            # Update data
            merged_entities[key]["altNames"].update(current_alts)
            
            if "Character" in e_type:
                i_set = parse_tags_to_set(entity_item.get("IdentityTags"))
                m_set = parse_tags_to_set(entity_item.get("ModifierTags"))
                merged_entities[key]["IdentityTags"].update(i_set)
                merged_entities[key]["ModifierTags"].update(m_set)
            else:
                v_set = parse_tags_to_set(entity_item.get("VisualTags"))
                merged_entities[key]["VisualTags"].update(v_set)

    # ---------------------------------------------------------
    # PART 5: FORMAT OUTPUT & SAVE
    # ---------------------------------------------------------
    final_output = {
        "characters": [],
        "locations": [],
        "items": []
    }
    
    for key, data in merged_entities.items():
        # Convert Sets back to Lists/Strings for JSON
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

    elapsed = time.perf_counter() - start
    print(f"Extract Entities 2 Finished in: {elapsed:.3f} seconds")

    # Save to Database
    try:
        saved_status = save_extraction_result(session, chapter_id, final_output)
        if saved_status:
            print("✅ Data successfully saved/updated in Database.")
        else:
            print("⚠️ Failed to save data to Database.")
    except Exception as e:
        print(f"❌ Error saving to database: {e}")
        
    return final_output

@app.get("/generate-prompts/{chapter_id}")
async def generate_prompts(
    chapter_id: int,
    session: Session = Depends(get_session)
):  
    start=time.perf_counter()
    chapter = session.get(chapterContent, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail=f"Chapter ID {chapter_id} not found")
    text = chapter.chapterDetail
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Chapter content is empty")
    translator = Translator()
    chunks = smart_chunker(text, CHUNK_SIZE_LIMIT)
    print(f"Chunks: {len(chunks)}")
    final_results = []
    for index, chunk in enumerate(chunks):
        print(f"{index + 1}")
        chunk_result = {
            "chunk_id": index + 1,
            "thai_text": chunk,
            "english_text": "",
            "sd_prompt": "",
            "entities": [],
            "error": None
        }
        try:
            translation = await translator.translate(chunk, src='th', dest='en')
            english_text = translation.text
            # chunk_result["english_text"] = english_text
            ollama_data = call_ollama_via_http(english_text, extractModel)
            
            chunk_result["sd_prompt"] = ollama_data["visual_tags"]
            chunk_result["entities"] = ollama_data["entities"]
            time.sleep(SLEEP_BETWEEN_CHUNKS)
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            chunk_result["error"] = str(e)
            chunk_result["sd_prompt"] = "Error generating prompt"
        final_results.append(chunk_result)
        print("Time: ", time.perf_counter() - start)
    return final_results

# --------------------------------------------------------------

import base64
import uuid

MODEL_PATH = r"C:\stability matrix\Data\Models\StableDiffusion\juggernautXL_ragnarokBy.safetensors"
STORAGE_DIR = "storage/thumbnail"

os.makedirs(STORAGE_DIR, exist_ok=True)

# Global Variables
pipe = None
startup_error = None # เพิ่มตัวแปรเก็บ Error เพื่อแจ้ง User
device = "cuda" if torch.cuda.is_available() else "cpu"

@app.on_event("startup")
def load_model_global():
    """
    โหลด Model ครั้งเดียวตอนเปิด Server (แก้ปัญหาช้า)
    เลียนแบบ Logic จากโค้ดเก่าของคุณ
    """
    global pipe, MODEL_PATH, startup_error
    
    print(f"\n⚙️  Starting System on: {device}")
    print(f"📂 Loading Model: {MODEL_PATH}")

    try:
        start_time = time.perf_counter()
        
        # 1. ตรวจสอบว่าเป็น SDXL หรือไม่ (ตาม Logic โค้ดเก่า)
        is_xl = "xl" in MODEL_PATH.lower()
        is_safetensors = MODEL_PATH.endswith(".safetensors")
        
        PipelineClass = StableDiffusionXLPipeline if is_xl else StableDiffusionPipeline
        torch_dtype = torch.float16 if device == "cuda" else torch.float32

        print(f"   Using Pipeline: {PipelineClass.__name__}")

        # 2. โหลด Model (ใช้ diffusers หาไฟล์เอง ไม่ต้องใช้ os.path เช็คดักหน้า)
        pipe = PipelineClass.from_single_file(
            MODEL_PATH,
            use_safetensors=is_safetensors,
            torch_dtype=torch_dtype,
            local_files_only=True # บังคับหาในเครื่องเท่านั้น
        )
        
        # 3. ปิด Safety Checker & Watermark (ตามโค้ดเก่าเพื่อความเร็ว)
        if hasattr(pipe, "safety_checker"):
            pipe.safety_checker = None
        if hasattr(pipe, "requires_safety_checker"):
            pipe.requires_safety_checker = False
        if hasattr(pipe, "watermarker"):
            pipe.watermarker = None

        # ย้ายไป GPU
        pipe.to(device)
        
        # เพิ่มเติม: เปิด Memory Efficient Attention ถ้าใช้ xformers ได้
        try:
            pipe.enable_xformers_memory_efficient_attention()
        except:
            pass

        print(f"✅ Model Loaded Successfully in {time.perf_counter() - start_time:.2f}s")
        startup_error = None # เคลียร์ Error ถ้าโหลดสำเร็จ

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error Loading Model: {error_msg}")
        print("   (Server will start, but /generate will fail)")
        # เก็บ Error ไว้บอก User ตอนเรียก API
        startup_error = error_msg

@app.get("/generate")
def generate_image(prompt: str = "A futuristic city"):
    print("a")
    global pipe, startup_error
    
    if pipe is None:
        error_detail = "Model setup failed."
        if startup_error:
            error_detail += f" Reason: {startup_error}"
            print("b")
        else:
            error_detail += " Check console logs for more info."
            print("c")
            
        raise HTTPException(status_code=500, detail=error_detail)

    start = time.perf_counter()
    print(f"🎨 Generating: {prompt}")
    
    try:
        negative_prompt = "blurry, low quality, distorted, text, watermark"

        # ขนาดรูปตามโค้ดเก่าของคุณ (640x1280)
        # หมายเหตุ: SDXL แนะนำ 1024x1024 แต่ถ้าคุณชอบ Ratio นี้ก็ตามนี้ครับ
        image = pipe(
            prompt=prompt, 
            negative_prompt=negative_prompt, 
            num_inference_steps=20,
            height=1024, # ปรับเป็น 1024 เพื่อคุณภาพที่ดีที่สุดของ SDXL (หรือแก้กลับเป็น 640 ตามเดิมได้)
            width=1024   # ปรับเป็น 1024 (หรือแก้กลับเป็น 1280 ตามเดิมได้)
        ).images[0]
        
        filename = f"{uuid.uuid4()}.png"
        file_path = os.path.join(STORAGE_DIR, filename)
        
        image.save(file_path)
        
        print(f"✅ Done in {time.perf_counter() - start:.3f}s -> {file_path}")
        return FileResponse(file_path, media_type="image/png")

    except Exception as e:
        if "out of memory" in str(e).lower():
            torch.cuda.empty_cache()
            raise HTTPException(status_code=500, detail="GPU OOM")
        raise HTTPException(status_code=500, detail=str(e))
        
# ---------------------------------------------------------------

# @app.get("/generate_image_internal")
# def generate_image_internal(prompt: str, output_filename: str):
#     start = time.perf_counter()
    
#     payload = {
#         "prompt": prompt,
#         "negative_prompt": "blurry, low quality, distorted, text, watermark, bad anatomy, bad hands, lowres, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, username",
#         "steps": 20,               
#         "sampler_name": "Euler a", 
#         "width": 1024,            
#         "height": 1024,
#         "cfg_scale": 7,            
#         "batch_size": 1,
        
#         # [NEW] บังคับให้ WebUI สลับไปใช้ Model นี้
#         "override_settings": {
#             "sd_model_checkpoint": SD_MODEL_CHECKPOINT
#         },
#         "override_settings_restore_afterwards": False # True=ใช้เสร็จกลับเป็นตัวเดิม, False=เปลี่ยนแล้วเปลี่ยนเลย
#     }

#     try:
#         # 1. ยิง API Request
#         response = requests.post(SD_API_URL, json=payload, timeout=600) # timeout เผื่อเครื่องช้า
        
#         if response.status_code == 200:
#             r = response.json()
            
#             # API จะส่งรูปกลับมาเป็น Base64 String ใน r['images'][0]
#             image_b64 = r['images'][0]
            
#             # 2. แปลง Base64 กลับเป็นไฟล์รูปภาพ
#             save_path = os.path.join(STORAGE_DIR, output_filename)
            
#             with open(save_path, "wb") as f:
#                 f.write(base64.b64decode(image_b64))
            
#             duration = time.perf_counter() - start
#             print(f"✅ Generated & Saved to {save_path} in {duration:.2f}s")
#             return save_path
            
#         else:
#             print(f"❌ SD API Error: {response.status_code} - {response.text}")
#             raise Exception(f"SD API Error: {response.status_code}")

#     except requests.exceptions.ConnectionError:
#         print("❌ Connection Refused: ตรวจสอบว่า Stability Matrix เปิดอยู่และใส่ --api แล้วหรือยัง")
#         raise Exception("Cannot connect to Stability Matrix (Is it running?)")
        
#     except Exception as e:
#         print(f"❌ Gen Image Error: {e}")
#         raise e
    
@app.get("/")
def root():
    return "server is worked 111"

@app.get("/test")
def root():
    return "test test 222"

@app.post("/")
def root():
    return "test post 333"