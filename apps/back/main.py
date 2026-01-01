from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import List
import requests
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
from fastapi.staticfiles import StaticFiles

from database import create_db_and_tables, get_session
from models import movieTitle, chapterContent

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
extractModel = "gemma2:9b"
# extractModel = "scb10x/typhoon2.1-gemma3-12b:latest" 
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

@app.get("/extract/{chapter_id}", response_model=chapterContent)
async def get_chapter_translated_summary(chapter_id: int, session: Session = Depends(get_session)):
    start = time.perf_counter()
    chapter = session.get(chapterContent, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    original_text = chapter.chapterDetail 
    full_translated_text = ""
    if original_text:
        chunks = original_text.split("\n\n")
        translated_chunks = []
        for chunk in chunks:
            if chunk.strip():
                try:
                    result = await translator.translate(chunk, dest='en') 
                    translated_chunks.append(result.text)
                except Exception as e:
                    translated_chunks.append(chunk)
            else:
                translated_chunks.append("")
        full_translated_text = "\n\n".join(translated_chunks)
        
    if full_translated_text:
        try:
            prompt = f"Summarize the entire plot of this in one long sentence, return only one sentence.\n\nSource Text:\n{full_translated_text}"
            payload = {
                "model": transModel,
                "prompt": prompt,
                "stream": False
            }
            async with httpx.AsyncClient(timeout=600.0) as client:
                response = await client.post(ollamaURL, json=payload)
                response.raise_for_status()
                ollama_result = response.json().get("response", "")
                chapter.chapterDetailEng = ollama_result
                session.add(chapter)
                session.commit()
                session.refresh(chapter)
        except Exception as e:
            chapter.chapterDetail = full_translated_text
    print(f"extract time: {time.perf_counter() - start:.3f} seconds")
    return chapter

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

@app.get("/chapters/{chapter_id}", response_model=chapterContent)
def get_chapter(chapter_id: int, session: Session = Depends(get_session)):
    chapter = session.get(chapterContent, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter

@app.get("/tempReadPDF")
def readddpdf(file_path: str = "คัมภีร์วิถีเซียน0001-0500.pdf"):
    path = file_path.strip('"').strip("'") 
    try:
        result = ""
        with fitz.open(path) as doc:
            for page_num, page in enumerate(doc):
                if(page_num<=1):
                    continue
                if(page_num>=7):
                    break
                text = clearASCII(page.get_text() or "")
                text = clearThaiTypeing(text)
                result += text      
        result=clearNewline(result)
        return {result}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"error: {str(e)}") 
    
@app.get("/tempReadPDFnoClear")
def readddpdf(file_path: str = "คัมภีร์วิถีเซียน0001-0500.pdf"):
    path = file_path.strip('"').strip("'") 
    try:
        result = ""
        with fitz.open(path) as doc:
            for page_num, page in enumerate(doc):
                if(page_num<=1):
                    continue
                if(page_num>=7):
                    break
                text = clearASCII(page.get_text() or "")
                text = clearThaiTypeing(text)
                result += text      
        return {result}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"error: {str(e)}") 

@app.get("/extractEntities/{chapter_id}")
async def extract_entities(chapter_id: int, session: Session = Depends(get_session)):
    start = time.perf_counter()
    chapterDetail = session.get(chapterContent, chapter_id).chapterDetail
    # chunks = chapterDetail.split("\n")
    # translate = ""
    # if chapterDetail:
    #     chunks = chapterDetail.split("\n")
    #     temp = []
    #     for chunk in chunks:
    #         if chunk.strip():
    #             try:
    #                 result = await translator.translate(chunk, dest='en') 
    #                 temp.append(result.text)
    #             except Exception as e:
    #                 return {"err": e}
    #         else:
    #             temp.append("")
    #     translate = "\n".join(temp)
    # else:
    #     return {"result": "No content found in this chapter."}
    
    # print(f"translate time: {time.perf_counter() - start:.3f} seconds")
    # return translate
    # start=time.perf_counter()   
    
        # ช่วยสกัดชื่อคน ชื่อสถานที่ และชื่อสิ่งของให้หน่อยโดยที่ชื่อคนถ้ามีชื่อรองหรือฉายาให้เอามาใส่ใน altName
    
    # {{
    #     "characters": [
    #         {{
    #             "name": "ชื่อตัวละคร",
    #             "altName": ["ฉายา", "ชื่ออื่นๆ"]
    #         }}
    #     ],
    #     "locations": ["สถานที่ 1", "สถานที่ 2"],
    #     "items": [
    #         {{ "name": "ชื่อสิ่งของ", "description": "คำอธิบายสั้นๆ" }}
    #     ]
    # }}

    # --- เริ่มต้นเนื้อหา ---
    # 
    # --- จบเนื้อหา ---
    prompt = f"""
    Please extract characters, locations, and items from the text below. For characters, if they have an alias or nickname, include it in the "altName" field.

    Return the output in the following JSON format:

    {{
        "characters": [
            {{
                "name": "Character Name",
                "altName": ["Nickname", "Alias"]
            }}
        ],
        "locations": ["Location 1", "Location 2"],
        "items": [
            {{ "name": "Item Name", "description": "Short description" }}
        ]
    }}

    --- Content Start ---
    {chapterDetail}
    --- Content End ---
        """

    payload = {
        "model": extractModel,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": 8192, # เพิ่ม Context Window เผื่อเนื้อหายาว
            "temperature": 0.1 # ลดความมั่ว ให้ตอบตามโครงสร้าง 
        },
        "format": "json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=1800.0) as client:
            response = await client.post(ollamaURL, json=payload)
            response.raise_for_status()
            result_text = response.json().get("response", "")
            
            try:
                cleaned_text = result_text.replace("```json", "").replace("```", "").strip()
                json_data = json.loads(cleaned_text)
                
                alias_map = {}
                
                if "characters" in json_data:
                    for char in json_data["characters"]:
                        main_name = char.get("canonical_name")
                        if main_name:
                            alias_map[main_name] = main_name
                            for alias in char.get("aliases", []):
                                alias_map[alias] = main_name
                json_data["rag_lookup_map"] = alias_map
                print(f"Extraction time: {time.perf_counter() - start:.3f} seconds")
                return json_data
            except json.JSONDecodeError:
                return {"error": "Failed to parse JSON", "raw_output": result_text}
    except Exception as e:
        print(f"Error during extraction: {e}")
        raise HTTPException(status_code=500, detail=f"AI Extraction Error: {e}")
    
@app.get("/")
def root():
    return "server is worked 111"

@app.get("/test")
def root():
    return "test test 222"

@app.post("/")
def root():
    return "test post 333"