from sqlmodel import Session, select
import numpy as np
import faiss
from database import engine
from models import chapterContent, ChunkContent, movieTitle, EntityContent
import rag
import traceback
import time

def process_movie_background(movie_id: int):
    """
    งานเบื้องหลัง: 
    1. อ่าน Chapter ทั้งหมด -> Chunk -> Embed
    2. Extract Entities (5 ตอนแรก)
    3. Save ลง DB และ FAISS ทุกๆ 25 ตอน (Batch Commit)
    """
    BATCH_SIZE = 25 # จำนวนตอนที่จะบันทึกทีเดียว

    with Session(engine) as db:
        try:
            print(f"--- Worker Started: Movie {movie_id} ---")
            
            # 1. โหลด Index
            index = rag.load_or_create_index(movie_id)
            
            # 2. เตรียม Cache รายชื่อ Entity
            existing_entities = db.exec(
                select(EntityContent).where(EntityContent.movie_id == movie_id)
            ).all()
            existing_names = {e.name for e in existing_entities}
            print(f"Loaded {len(existing_names)} existing entities.")

            # 3. ดึงตอนที่จะทำ
            chapters = db.exec(
                select(chapterContent)
                .where(chapterContent.movieId == movie_id)
            ).all()

            total_chapters = len(chapters)
            print(f"Processing {total_chapters} chapters...")
            
            # ตัวแปรสำหรับเก็บข้อมูลชั่วคราว (Buffer)
            batch_vectors = []
            batch_ids = []
            
            for i, chap in enumerate(chapters, 1):
                chap_start_time = time.time()
                
                # ==========================================
                # A. RAG Process (Embedding)
                # ==========================================
                chunks = rag.split_text_into_chunks(chap.chapterDetail)
                print(f"Start Ep.{chap.episodeNumber} (ID: {chap.id}) - Total {len(chunks)} chunks")
                
                for idx, txt in enumerate(chunks):
                    # Save Chunk (ลง Memory ของ DB Session ไว้ก่อน)
                    new_chunk = ChunkContent(
                        chunk_text=txt,
                        chunk_index=idx,
                        chapter_id=chap.id,
                        movie_id=movie_id
                    )
                    db.add(new_chunk)
                    
                    # flush() เพื่อเอา ID มาใช้กับ FAISS (แต่ยังไม่ commit ลง Disk)
                    db.flush() 
                    db.refresh(new_chunk)
                    
                    # Embed Vector
                    if hasattr(rag, 'embedder'): 
                        vec = rag.embedder.encode([txt])
                    else: 
                        vec = rag.encode_texts([txt])

                    vec = vec.astype('float32')
                    if len(vec.shape) == 1: vec = vec.reshape(1, -1)
                    faiss.normalize_L2(vec)
                    
                    # เก็บใส่ Buffer
                    batch_vectors.append(vec[0])
                    batch_ids.append(new_chunk.id)
                
                # ==========================================
                # B. Entity Extraction (5 ตอนแรก)
                # ==========================================
                if chunks and chap.episodeNumber <= 5:
                    target_chars = 1500
                    print(f"   🔎 [Ep.{chap.episodeNumber}] Extracting Entities...")
                    
                    extract_text = chap.chapterDetail[:target_chars]
                    found_entities_json = rag.extract_entities_from_text(extract_text)
                    
                    if found_entities_json:
                        for item in found_entities_json:
                            name = item.get('name')
                            if name and name not in existing_names:
                                new_ent = EntityContent(
                                    name=name,
                                    category=item.get('category', 'Unknown'),
                                    description=item.get('description', ''),
                                    visual_tags=item.get('visual_tags', ''),
                                    movie_id=movie_id,
                                    chapter_found_id=chap.id
                                )
                                db.add(new_ent)
                                existing_names.add(name) 

                # Mark as processed
                chap.is_processed = True
                db.add(chap)
                
                print(f"--> Ep.{chap.episodeNumber} processed in {time.time() - chap_start_time:.2f}s")

                # ==========================================
                # C. Checkpoint: Save ทุกๆ 25 ตอน หรือ ตอนสุดท้าย
                # ==========================================
                if i % BATCH_SIZE == 0 or i == total_chapters:
                    print(f"\n💾 Checkpoint Reached ({i}/{total_chapters}). Saving to DB & FAISS...")
                    save_start = time.time()

                    # 1. บันทึก Index FAISS
                    if batch_vectors:
                        vectors_array = np.array(batch_vectors).astype('float32')
                        ids_array = np.array(batch_ids).astype('int64')
                        index.add_with_ids(vectors_array, ids_array)
                        rag.save_index(index, movie_id)
                        
                        # เคลียร์ Buffer
                        batch_vectors = []
                        batch_ids = []

                    # 2. บันทึก Database (Commit ทีเดียว 25 ตอน)
                    db.commit()
                    
                    print(f"✅ Saved Checkpoint in {time.time() - save_start:.2f}s\n")
            
            # Update Movie Status ตอนจบ
            movie = db.get(movieTitle, movie_id)
            if movie:
                movie.status = "ready"
                db.add(movie)
                db.commit()

            print("Worker Finished Successfully!")

        except Exception as e:
            print(f"Worker Error: {e}")
            traceback.print_exc()