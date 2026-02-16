import os
import gc
import json
import re
import time
import asyncio
import traceback
from PIL import Image, ImageDraw, ImageFilter, ImageOps
import httpx
import torch
from diffusers import (
    AutoPipelineForInpainting, 
    StableDiffusionXLInpaintPipeline, 
    StableDiffusionInpaintPipeline
)
from transformers import CLIPVisionModelWithProjection
from dotenv import load_dotenv

# ✅ Import rembg สำหรับลบพื้นหลัง
try:
    from rembg import remove as remove_bg
    HAS_REMBG = True
except ImportError:
    print("⚠️ 'rembg' not installed. Background removal will be skipped.")
    HAS_REMBG = False

# พยายาม import psutil
try:
    import psutil
except ImportError:
    psutil = None

load_dotenv()

# ================= CONFIG =================
IMG_WIDTH = 768
IMG_HEIGHT = 512
NUM_STEPS = 20

# Model Paths
ollamaURL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
ollamaModel = os.getenv("OLLAMA_MODEL", "gemma3:12b")
stabilityModel = "C:\\stability matrix\\Data\\Models\\StableDiffusion\\juggernautXL_ragnarokBy.safetensors"
IP_ADAPTER_REPO = "h94/IP-Adapter" 
IP_ADAPTER_SUBFOLDER = "sdxl_models"
IP_ADAPTER_FILENAME = "ip-adapter-plus-face_sdxl_vit-h.bin"

# ================= UTILS =================
def log_memory_usage(label=""):
    if psutil:
        mem = psutil.virtual_memory()
        print(f"   📊 RAM [{label}]: Used {mem.percent}% | Free {mem.available / 1024**3:.2f} GB")
        return mem.percent
    return 0

def flush_memory():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

async def wait_for_memory(threshold=85):
    if not psutil: return
    if log_memory_usage("Pre-Check") > 90:
        print("   ⏳ High RAM, waiting 10s...")
        await asyncio.sleep(10)
        flush_memory()
    for _ in range(5): 
        if log_memory_usage("Check") < threshold: return
        flush_memory()
        await asyncio.sleep(2)

def clean_prompt(text):
    if isinstance(text, list): text = ", ".join(text)
    if not isinstance(text, str): return ""
    text = re.sub(r"[\[\]\{\}\"']", "", text)
    text = re.sub(r"\w+\s*:\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

# ================= OLLAMA LOGIC =================
async def unload_ollama(client: httpx.AsyncClient):
    try:
        await client.post(ollamaURL, json={"model": ollamaModel, "keep_alive": 0})
        print("   ✅ Ollama Unloaded.")
    except: pass

async def analyze_scene(chunk_text: str, client: httpx.AsyncClient):
    await wait_for_memory()
    
    prompt = f"""
    Role: Visual Director. Task: Extract keywords. Input: "{chunk_text}"
    Output JSON: {{ 
        "environment": "keywords...", 
        "characters": [ {{ "name": "...", "position": "LEFT/CENTER/RIGHT", "depth": "FOREGROUND/MID_GROUND/BACKGROUND", "visual_action": "action keywords" }} ] 
    }}
    """
    try:
        print(f"   [Ollama] Analyzing...")
        res = await client.post(ollamaURL, json={"model": ollamaModel, "prompt": prompt, "stream": False, "format": "json"}, timeout=300.0)
        clean_json = re.sub(r'```json\s*', '', res.json().get("response", "")).replace('```', '')
        match = re.search(r'\{.*\}', clean_json, re.DOTALL)
        return json.loads(match.group(0)) if match else None
    except Exception as e:
        print(f"❌ Analysis Failed: {e}")
        return None

# ================= SDXL LOGIC =================
class SDEngine:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.dtype = torch.float16 if self.device == "cuda" else torch.float32
        
    def load_pipeline(self):
        print(f"   🚀 Loading SDXL ({self.device})...")
        
        # 1. Image Encoder
        try:
            image_encoder = CLIPVisionModelWithProjection.from_pretrained(
                "h94/IP-Adapter", subfolder="models/image_encoder", torch_dtype=self.dtype, local_files_only=True
            )
        except:
            image_encoder = CLIPVisionModelWithProjection.from_pretrained(
                "h94/IP-Adapter", subfolder="models/image_encoder", torch_dtype=self.dtype
            )

        # 2. Pipeline
        PipelineClass = StableDiffusionXLInpaintPipeline if "xl" in stabilityModel.lower() else StableDiffusionInpaintPipeline
        
        try:
            if stabilityModel.endswith(".safetensors"):
                pipe = PipelineClass.from_single_file(stabilityModel, torch_dtype=self.dtype, image_encoder=image_encoder, use_safetensors=True)
            else:
                pipe = PipelineClass.from_pretrained(stabilityModel, torch_dtype=self.dtype, image_encoder=image_encoder)
        except:
            # Fallback
            pipe = PipelineClass.from_pretrained(stabilityModel, torch_dtype=self.dtype, image_encoder=image_encoder, use_safetensors=False)

        if hasattr(pipe, "safety_checker"): pipe.safety_checker = None
        
        # Optimization
        try: pipe.enable_vae_slicing()
        except: pass
        if self.device == "cuda": pipe.enable_model_cpu_offload()
        else: pipe.to(self.device)
        
        # IP-Adapter
        pipe.load_ip_adapter(IP_ADAPTER_REPO, subfolder=IP_ADAPTER_SUBFOLDER, weight_name=IP_ADAPTER_FILENAME)
        
        return pipe

    def get_smart_coords(self, pos, depth, w, h):
        p, d = pos.upper(), depth.upper()
        
        # ปรับสเกลตามระยะ
        if "FORE" in d: scale, y_rat = 0.85, 0.10
        elif "MID" in d: scale, y_rat = 0.60, 0.30
        else: scale, y_rat = 0.40, 0.40
        
        char_h = int(h * scale)
        # คำนวณความกว้างตามสัดส่วน 1:2.5 (คนปกติ) เพื่อไม่ให้อ้วน/ผอมเกิน
        char_w = int(char_h / 2.5) 
        
        top_y = int(h * y_rat)
        
        if "LEFT" in p: start_x = int(w * 0.1)
        elif "RIGHT" in p: start_x = int(w * 0.9) - char_w
        else: start_x = (w // 2) - (char_w // 2)
        
        return (start_x, top_y, start_x + char_w, top_y + char_h)

    def process_character_image(self, img_path):
        """
        โหลดรูป -> ลบพื้นหลัง -> คืนค่าเป็น RGBA
        """
        if not os.path.exists(img_path): return None
        
        img = Image.open(img_path).convert("RGBA")
        
        # ✅ ลบพื้นหลัง (ถ้ามี library)
        if HAS_REMBG:
            # print(f"      ✂️ Removing background for {os.path.basename(img_path)}...")
            try:
                img = remove_bg(img)
            except Exception as e:
                print(f"      ⚠️ Rembg failed: {e}")
        
        return img

    def run(self, scene_plan, output_path, character_refs):
        log_memory_usage("Start SD")
        pipe = None
        try:
            pipe = self.load_pipeline()
            
            env_desc = clean_prompt(scene_plan.get('environment', 'scene'))
            STYLE = "masterpiece, best quality, photorealistic, 8k, raw photo, ancient chinese wuxia style"
            NEG = "modern, western, low quality, ugly, blurry, watermark, text, bad anatomy"
            
            base_prompt = f"{STYLE}, {env_desc}, no humans, empty scenery, masterpiece"
            
            # 1. Gen Background
            print("   Generating Background...")
            # ✅ FIX: สร้าง Dummy Image เพื่อหลอก Model ให้ทำงาน
            dummy_ref = Image.new("RGB", (224, 224), "black")
            
            pipe.set_ip_adapter_scale(0.0)
            base_image = pipe(
                prompt=base_prompt, negative_prompt=NEG,
                image=Image.new("RGB", (IMG_WIDTH, IMG_HEIGHT), (128,128,128)),
                mask_image=Image.new("L", (IMG_WIDTH, IMG_HEIGHT), "white"),
                ip_adapter_image=dummy_ref,
                # ✅ FIX: บังคับขนาดภาพเพื่อไม่ให้สเกลเพี้ยน
                height=IMG_HEIGHT, width=IMG_WIDTH, 
                num_inference_steps=NUM_STEPS, strength=1.0
            ).images[0]

            # 📸 DEBUG: Save Background Step
            try:
                base_image.save(output_path.replace(".png", "_step0_bg.png"))
            except: pass

            # 2. Paste Characters & Blend
            # Sort Depth: Back -> Fore
            character_refs.sort(key=lambda x: 0 if "BACK" in x['depth'] else (1 if "MID" in x['depth'] else 2))

            for i, char in enumerate(character_refs):
                name = char['name']
                ref_path = char['ref_path']
                
                print(f"   👤 Processing: {name} ({char['depth']})")
                
                # โหลดและตัดพื้นหลัง
                char_img_rgba = self.process_character_image(ref_path)
                if not char_img_rgba: continue

                # คำนวณขนาด
                x1, y1, x2, y2 = self.get_smart_coords(char['position'], char['depth'], IMG_WIDTH, IMG_HEIGHT)
                target_w, target_h = x2 - x1, y2 - y1
                
                # Resize
                char_img_rgba.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
                
                # คำนวณจุดวาง (Center Bottom aligned)
                paste_x = x1 + (target_w - char_img_rgba.width) // 2
                paste_y = y2 - char_img_rgba.height # วางให้เท้าชิดขอบล่างของกรอบ
                
                # แปะรูปลงไป (Composite)
                base_image.paste(char_img_rgba, (paste_x, paste_y), char_img_rgba)
                
                # สร้าง Mask จาก Alpha Channel ของตัวละคร
                # เพื่อให้ AI วาดแก้เฉพาะตรงตัวคน + ขอบๆ นิดหน่อย
                char_mask = char_img_rgba.split()[-1] # เอา Alpha Channel
                full_mask = Image.new("L", (IMG_WIDTH, IMG_HEIGHT), 0)
                full_mask.paste(char_mask, (paste_x, paste_y))
                
                # ขยาย Mask ออกเล็กน้อยเพื่อให้ AI เกลี่ยขอบ (Dilate)
                full_mask = full_mask.filter(ImageFilter.GaussianBlur(radius=5)) # เบลอนิดเดียวพอ
                
                # Inpaint (Blending)
                # ใช้ Strength ต่ำๆ เพื่อรักษาหน้าตาเดิม
                # ใช้ IP-Adapter ช่วยคุมแสง
                pipe.set_ip_adapter_scale(0.6) 
                prompt = f"{STYLE}, {name}, {char['visual_action']}, masterpiece"
                
                base_image = pipe(
                    prompt=prompt, negative_prompt=NEG,
                    image=base_image,
                    mask_image=full_mask,
                    ip_adapter_image=char_img_rgba.convert("RGB"), # ส่งรูปไปให้ดูแสง
                    # ✅ FIX: บังคับขนาดภาพอีกครั้ง
                    height=IMG_HEIGHT, width=IMG_WIDTH,
                    num_inference_steps=NUM_STEPS,
                    strength=0.45, # ✅ Strength ต่ำๆ เน้นเกลี่ยแสง ไม่วาดหน้าใหม่
                    guidance_scale=6.0
                ).images[0]

                # 📸 DEBUG: Save Step Image
                try:
                    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', name)
                    base_image.save(output_path.replace(".png", f"_step{i+1}_{safe_name}.png"))
                except: pass

            base_image.save(output_path)
            print(f"✅ Saved: {output_path}")
            return True
            
        except Exception as e:
            print(f"❌ SD Run Error: {e}")
            traceback.print_exc()
            return False
        finally:
            if 'pipe' in locals() and pipe is not None: del pipe
            flush_memory()