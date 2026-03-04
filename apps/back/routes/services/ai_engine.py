import os
import gc
import json
import re
import asyncio
from PIL import Image, ImageOps
import httpx
import torch
from diffusers import StableDiffusionXLPipeline
from dotenv import load_dotenv

try:
    import psutil
except ImportError:
    psutil = None

load_dotenv()

IMG_WIDTH = 1280
IMG_HEIGHT = 720

ollamaURL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
ollamaModel = os.getenv("OLLAMA_MODEL", "gemma3:12b")
stabilityModel = "C:\\stability matrix\\Data\\Models\\StableDiffusion\\juggernautXL_ragnarokBy.safetensors"

def flush_memory():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

def log_memory():
    if psutil:
        mem = psutil.virtual_memory()
        print(f"RAM: {mem.percent}%")

def clean_prompt_text(text):
    text = re.sub(r"[\[\]\{\}\"']", "", text)
    text = text.replace("\n", " ")
    return text.strip()

async def analyze_script_content(chunk_text: str, client: httpx.AsyncClient):
    """
    Phase 1: อ่านบทเพื่อดูว่า 'ใคร' อยู่ 'ที่ไหน'
    """
    prompt = f"""
    Role: Visual Novel Director.
    Task: Analyze script for logistics.
    Input Story: "{chunk_text}"
    
    Rules:
    1. 'location_name': Specific, consistent name of the location (e.g. "Village Entrance", "Han Li's Room").
    2. 'characters': List Names of characters present (Max 3 key characters).
    
    Output JSON: {{ "location_name": "...", "characters": ["Name1", "Name2"] }}
    """
    try:
        res = await client.post(ollamaURL, json={"model": ollamaModel, "prompt": prompt, "stream": False, "format": "json"}, timeout=300.0)
        clean_json = re.sub(r'```json\s*', '', res.json().get("response", "")).replace('```', '')
        match = re.search(r'\{.*\}', clean_json, re.DOTALL)
        return json.loads(match.group(0)) if match else None
    except Exception as e:
        print(f"❌ Meta Analysis Failed: {e}")
        return None

async def generate_location_prompt(location_name: str, context_text: str, client: httpx.AsyncClient):
    """
    Phase 2: ให้ AI ออกแบบ Visual Prompt
    """
    prompt = f"""
    Role: Environment Artist.
    Task: Write keywords for a REALISTIC background image.
    Location: "{location_name}"
    Context: "{context_text}"
    
    Rules:
    1. Output KEYWORDS only, comma separated. **Max 15 keywords**.
    2. Style: **Photorealistic, Cinematic, 8k**. NO anime style.
    3. NO CHARACTERS, NO PEOPLE. Just the scenery.
    4. Atmosphere, lighting, time of day.
    
    Output string: "keyword1, keyword2, ..."
    """
    try:
        print(f"   [Ollama] Designing Location: {location_name}...")
        res = await client.post(ollamaURL, json={"model": ollamaModel, "prompt": prompt, "stream": False}, timeout=300.0)
        raw_prompt = res.json().get("response", "").strip()
        
        cleaned = clean_prompt_text(raw_prompt)
        tags = [t.strip() for t in cleaned.split(',') if t.strip()]
        if len(tags) > 10:
            tags = tags[:10]
        
        return ", ".join(tags)

    except Exception as e:
        print(f"❌ Design Failed: {e}")
        return f"cinematic background, {location_name}, realistic, no humans"

async def unload_ollama(client: httpx.AsyncClient):
    try:
        await client.post(ollamaURL, json={"model": ollamaModel, "keep_alive": 0})
        print("   ✅ Ollama Unloaded.")
    except: pass

class BGGenerator:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.pipe = None

    def load_pipeline(self):
        if self.pipe: return self.pipe
        
        print(f"Loading Background ({self.device})...")
        try:
            if stabilityModel.endswith(".safetensors"):
                self.pipe = StableDiffusionXLPipeline.from_single_file(stabilityModel, torch_dtype=self.dtype, use_safetensors=True)
            else:
                self.pipe = StableDiffusionXLPipeline.from_pretrained(stabilityModel, torch_dtype=self.dtype)
        except Exception as e:
            print(f"   ⚠️ Load failed: {e}")
            return None

        if self.device == "cuda":
            if hasattr(self.pipe, "safety_checker"):
                self.pipe.safety_checker = None
            if hasattr(self.pipe, "requires_safety_checker"):
                self.pipe.requires_safety_checker = False
            if hasattr(self.pipe, "watermarker"):
                self.pipe.watermarker = None
            self.pipe.enable_model_cpu_offload()
            self.pipe.enable_vae_slicing()
        else:
            self.pipe.to(self.device)

        return self.pipe

    def generate_bg(self, prompt, output_path):
        pipe = self.load_pipeline()
        if not pipe: return False
        
        log_memory()
        print(f"   Generating BG: {prompt[:50]}...")
        
        style = "cinematic, photorealistic, highly detailed, 8k, masterpiece, raw photo, realistic lighting, unreal engine 5 render, sharp focus, ancient chinese architecture, wuxia, ancient Chinese"
        neg = "anime, cartoon, illustration, drawing, painting, people, humans, person, text, watermark, bad quality, blurry, crowd, lowres, distortedmodern, modern, futuristic, sci-fi, western architecture, neon signs, skyscraper, concrete, technology, street lights, electricity, power lines, container ship, cargo ship, dock crane"
        final_prompt = f"{style}, {prompt}"
        if len(final_prompt) > 1000:
            final_prompt = final_prompt[:1000]

        image = pipe(
            prompt=final_prompt,
            negative_prompt=neg,
            height=768, width=1280,
            num_inference_steps=30,
            guidance_scale=7.5
        ).images[0]
        
        image = image.resize((IMG_WIDTH, IMG_HEIGHT), Image.Resampling.LANCZOS)
        image.save(output_path)
        return True
    
class VNComposer:
    def process_character(self, img_path):
        """โหลดรูปตัวละคร (ที่ตัดพื้นหลังมาแล้ว)"""
        if not os.path.exists(img_path): return None
        return Image.open(img_path).convert("RGBA")

    def compose(self, bg_path, character_paths, output_path):
        """
        รวมร่าง: BG + ตัวละครตามจำนวน
        """
        if bg_path and os.path.exists(bg_path):
            bg = Image.open(bg_path).convert("RGBA")
        else:
            print("   ❌ BG not found, creating black canvas.")
            bg = Image.new("RGBA", (IMG_WIDTH, IMG_HEIGHT), "black")
        bg = bg.resize((IMG_WIDTH, IMG_HEIGHT), Image.Resampling.LANCZOS)
        valid_chars = []
        for p in character_paths:
            img = self.process_character(p)
            if img: valid_chars.append(img)
            
        count = len(valid_chars)
        char_target_h = int(IMG_HEIGHT * 0.85)
        
        positions = []
        if count == 1:
            positions = [0.5] # กลาง
        elif count == 2:
            positions = [0.25, 0.75] # ซ้าย, ขวา
        elif count >= 3:
            positions = [0.2, 0.5, 0.8] # ซ้าย, กลาง, ขวา (เอาแค่ 3 คนแรก)
            valid_chars = valid_chars[:3]

        for i, char_img in enumerate(valid_chars):
            aspect_ratio = char_img.width / char_img.height
            new_w = int(char_target_h * aspect_ratio)
            char_img = char_img.resize((new_w, char_target_h), Image.Resampling.LANCZOS)
            

            center_x = int(IMG_WIDTH * positions[i])
            paste_x = center_x - (new_w // 2)
            paste_y = IMG_HEIGHT - char_target_h + 30 
            
            # Paste with Alpha
            bg.alpha_composite(char_img, dest=(paste_x, paste_y))

        # 5. Save Final
        final_img = bg.convert("RGB")
        final_img.save(output_path)
        print(f"Saved: {os.path.basename(output_path)}")
        return True