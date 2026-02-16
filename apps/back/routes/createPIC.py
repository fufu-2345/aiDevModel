import asyncio
import time
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, create_engine, SQLModel 
import httpx
from dotenv import load_dotenv 

# ✅ แก้ไขการ Import ที่ถูกต้องตามคำขอ (จาก .services.ai_engine)
try:
    from .services.ai_engine import SDEngine, analyze_scene, unload_ollama, flush_memory, wait_for_memory
except ImportError:
    # Fallback กรณีโครงสร้างไฟล์ต่างกัน
    from services.ai_engine import SDEngine, analyze_scene, unload_ollama, flush_memory, wait_for_memory

# ==========================================
# 1. IMPORTS & SETUP
# ==========================================
try:
    from models import (
        movieTitle,
        chapterContent,
        chunkContent,
        entity,
        altEntity,
        character,
        altCharacter
    )
except ImportError:
    print("Error: models.py not found.")

load_dotenv()

postgres_user = os.getenv("POSTGRES_USER")
postgres_password = os.getenv("POSTGRES_PASSWORD")
postgres_server = os.getenv("POSTGRES_SERVER", "localhost")
postgres_port = os.getenv("POSTGRES_PORT", "5432")
postgres_db = os.getenv("POSTGRES_DB")

pg_url = f"postgresql://{postgres_user}:{postgres_password}@{postgres_server}:{postgres_port}/{postgres_db}"
engine = create_engine(pg_url)

def get_session():
    with Session(engine) as session:
        yield session

router = APIRouter(
    prefix="/createPic",
    tags=["createPic"]
)

@router.on_event("startup")
def on_startup():
    try:
        SQLModel.metadata.create_all(engine)
    except Exception as e:
        print(f"Database connection error: {e}")

# ==========================================
# 2. CONFIGURATION
# ==========================================

OUTPUT_DIR = "public/storage/pic/"
CHAR_DIR = "public/storage/characters/" 
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==========================================
# 3. DB HELPER
# ==========================================

def get_character_data(session: Session, movie_id: int, name_query: str):
    if not name_query: return None
    name_query = name_query.strip()

    def check_file(p):
        return p if p and os.path.exists(p) else None

    def check_id_files(char_id):
        if p := check_file(os.path.join(CHAR_DIR, f"{char_id}.png")): return p
        if p := check_file(os.path.join(CHAR_DIR, f"{char_id}.jpg")): return p
        return None

    # Search Logic
    char = session.exec(select(character).where(character.movieId == movie_id, character.name.ilike(f"%{name_query}%"))).first()
    if char:
        return check_file(char.refpath) or check_id_files(char.id)

    alt = session.exec(select(character).join(altCharacter).where(character.movieId == movie_id, altCharacter.altName.ilike(f"%{name_query}%"))).first()
    if alt:
        return check_file(alt.refpath) or check_id_files(alt.id)
    
    return None

# ==========================================
# 4. MAIN ENDPOINT
# ==========================================

@router.get("/generate-images/{chapter_id}")
async def generate_images_for_chapter(
    chapter_id: int, 
    session: Session = Depends(get_session)
):
    chunks = session.exec(select(chunkContent).where(chunkContent.chapterId == chapter_id)).all()
    chapter_info = session.get(chapterContent, chapter_id)
    
    if not chunks or not chapter_info:
        return {"status": "error", "message": "No data found."}

    success_count = 0
    
    # Initialize Engine
    sd_engine = SDEngine()

    async with httpx.AsyncClient(timeout=120.0) as client:
        for chunk in chunks:
            if chunk.picRef:
                print(f"Skipping Chunk {chunk.chunkNumber}: Exists.")
                continue

            print(f"\n--- Processing Chunk {chunk.chunkNumber} ---")
            
            try:
                # 1. PLAN SCENE
                text_input = chunk.chunkDetailEng if chunk.chunkDetailEng else chunk.chunkDetail
                if not text_input: continue

                scene_plan = await analyze_scene(text_input, client)
                await unload_ollama(client)
                flush_memory()
                
                if not scene_plan: continue

                # 2. PREPARE CHARACTERS
                char_refs = []
                for char_info in scene_plan.get('characters', []):
                    ref_path = get_character_data(session, chapter_info.movieId, char_info['name'])
                    if ref_path:
                        char_info['ref_path'] = ref_path
                        char_refs.append(char_info)
                    else:
                        print(f"   ⚠️ No ref image for {char_info['name']}, skipping.")

                # 3. GENERATE
                await wait_for_memory(threshold=85)
                filename = f"ch{chapter_id}_chunk{chunk.chunkNumber}_{int(time.time())}.png"
                full_path = os.path.join(OUTPUT_DIR, filename)
                
                # Run Sync in Thread
                is_generated = await asyncio.to_thread(
                    sd_engine.run, 
                    scene_plan, 
                    full_path,
                    char_refs
                )
                
                if is_generated:
                    chunk.picRef = full_path
                    session.add(chunk)
                    session.commit()
                    success_count += 1
            
            except Exception as e:
                print(f"⚠️ Chunk {chunk.chunkNumber} Failed: {e}")
                import traceback
                traceback.print_exc()

    return {
        "status": "completed",
        "generated": success_count
    }