from sqlmodel import Session, select
import numpy as np
import faiss
from database import engine
from models import chapterContent, ChunkContent, movieTitle
import rag
import traceback
import time

def process_movie_background(movie_id: int):
    """
    งานเบื้องหลัง: อ่าน Chapter -> Chunk -> Embed -> Save FAISS
    """
    with Session(engine) as db:
        try:
            print(f"--- Worker Started: Movie {movie_id} ---")
            
            # 1. โหลด Index
            index = rag.load_or_create_index(movie_id)
            
            # 2. ดึงตอนที่ยังไม่ Process (ใน Production ควรทำทีละ Batch)
            chapters = db.exec(
                select(chapterContent)
                .where(chapterContent.movieId == movie_id)
                # .where(chapterContent.is_processed == False) # ถ้าต้องการทำต่อจากเดิม
            ).all()

            print(f"Processing {len(chapters)} chapters...")
            
            batch_vectors = []
            batch_ids = []
            
            for chap in chapters:
                chap_start_time = time.time() # จับเวลาเริ่มตอน
                
                # หั่นข้อความ
                chunks = rag.split_text_into_chunks(chap.chapterDetail)
                print(f"Start processing Episode {chap.episodeNumber} (ID: {chap.id}) - Found {len(chunks)} chunks")
                
                for idx, txt in enumerate(chunks):
                    chunk_start_time = time.time() # จับเวลาเริ่ม Chunk

                    # Save Chunk ลง DB
                    new_chunk = ChunkContent(
                        chunk_text=txt,
                        chunk_index=idx,
                        chapter_id=chap.id,
                        movie_id=movie_id
                    )
                    db.add(new_chunk)
                    db.commit() 
                    db.refresh(new_chunk)
                    
                    # --- FIX: แก้ไขการสร้าง Vector ---
                    # ตรวจสอบว่าใช้ SentenceTransformer (embedder) หรือ Ollama
                    if hasattr(rag, 'embedder'):
                         # ส่งเป็น list [txt] เพื่อให้ได้ shape (1, 384) เสมอ
                        vec = rag.embedder.encode([txt])
                    else:
                        # กรณีใช้ rag แบบ Ollama/Requests
                        vec = rag.encode_texts([txt])

                    # Ensure float32 (FAISS requirement)
                    vec = vec.astype('float32')
                    
                    # Normalize (FAISS normalize_L2 expects 2D array)
                    if len(vec.shape) == 1:
                        vec = vec.reshape(1, -1)
                        
                    faiss.normalize_L2(vec)
                    
                    # append เฉพาะตัว vector (flatten กลับเป็น 1D เพื่อใส่ list รวม)
                    batch_vectors.append(vec[0])
                    batch_ids.append(new_chunk.id)

                    chunk_duration = time.time() - chunk_start_time
                    print(f"   [Ep.{chap.episodeNumber}] Chunk {idx+1}/{len(chunks)} processed in {chunk_duration:.4f}s")
                
                # Mark as processed
                chap.is_processed = True
                db.add(chap)
                db.commit()
                
                chap_duration = time.time() - chap_start_time
                print(f"--> Finished Episode {chap.episodeNumber} in {chap_duration:.4f}s\n")

            # 3. Save ลง FAISS ทีเดียว
            if batch_vectors:
                print(f"Indexing {len(batch_vectors)} chunks into FAISS...")
                save_start_time = time.time()
                # Convert list of vectors back to 2D numpy array
                vectors_array = np.array(batch_vectors).astype('float32')
                ids_array = np.array(batch_ids).astype('int64')
                
                index.add_with_ids(vectors_array, ids_array)
                rag.save_index(index, movie_id)
                print(f"Saved Index to disk in {time.time() - save_start_time:.4f}s")
            
            # 4. Update Status Movie
            movie = db.get(movieTitle, movie_id)
            if movie:
                movie.status = "ready"
                db.add(movie)
                db.commit()

            print("Worker Finished Successfully!")

        except Exception as e:
            print(f"Worker Error: {e}")
            traceback.print_exc() # ปริ้น Error เต็มๆ เพื่อช่วย Debug