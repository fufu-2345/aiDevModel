import os
import faiss
import numpy as np
import requests

FAISS_INDEX_DIR = "./faiss_indices"
os.makedirs(FAISS_INDEX_DIR, exist_ok=True)
OLLAMA_API_URL = "http://localhost:11434/api/embeddings"
OLLAMA_EMBED_MODEL = 'nomic-embed-text' 

# [สำคัญ] Dimension ต้องตรงกับ Model
# nomic-embed-text = 768
# all-minilm = 384
EMBEDDING_DIM = 768 

def get_index_path(movie_id: int):
    return os.path.join(FAISS_INDEX_DIR, f"movie_{movie_id}.index")

def load_or_create_index(movie_id: int):
    path = get_index_path(movie_id)
    if os.path.exists(path):
        try:
            return faiss.read_index(path)
        except:
            return faiss.IndexIDMap(faiss.IndexFlatIP(EMBEDDING_DIM))
    else:
        return faiss.IndexIDMap(faiss.IndexFlatIP(EMBEDDING_DIM))

def save_index(index, movie_id: int):
    path = get_index_path(movie_id)
    faiss.write_index(index, path)

def split_text_into_chunks(text, chunk_size=800, overlap=150):
    if not text: return []
    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = text[start:end]
        chunks.append(chunk)
        start += (chunk_size - overlap)
        if start >= text_len: break
    return chunks

def encode_texts(texts):
    embeddings = []
    for text in texts:
        try:
            payload = {
                "model": OLLAMA_EMBED_MODEL,
                "prompt": text
            }
            response = requests.post(OLLAMA_API_URL, json=payload)
            
            if response.status_code == 200:
                # แกะ JSON เอาค่า 'embedding'
                embedding = response.json().get('embedding')
                embeddings.append(embedding)
            else:
                print(f"❌ API Error: {response.status_code} - {response.text}")
                embeddings.append([0.0] * EMBEDDING_DIM)

        except Exception as e:
            print(f"❌ Connection Error: {e}")
            embeddings.append([0.0] * EMBEDDING_DIM)
    
    # แปลงเป็น Numpy Array เพื่อใส่ FAISS
    vectors = np.array(embeddings, dtype='float32')
    
    # Normalize
    faiss.normalize_L2(vectors)
    return vectors

# (ฟังก์ชันเสริม) ไว้ดึง Visual Tags โดยใช้ Model Chat ปกติ
def ai_extract_visuals_prompt(text_chunk):
    # สำหรับ Chat ต้องใช้ endpoint /api/generate
    chat_url = "http://localhost:11434/api/generate"
    # ... implementation using requests.post(chat_url, ...) ...
    pass