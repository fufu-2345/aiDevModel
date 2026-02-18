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

# ✅ Import rembg
try:
    from rembg import remove as remove_bg
    HAS_REMBG = True
except ImportError:
    print("⚠️ 'rembg' not installed. Background removal will be skipped.")
    HAS_REMBG = False

try:
    import psutil
except ImportError:
    psutil = None

load_dotenv()

# ================= CONFIG =================
IMG_WIDTH = 1024
IMG_HEIGHT = 768
NUM_STEPS = 25 
CHAR_STEPS = 30 

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
        
        try:
            image_encoder = CLIPVisionModelWithProjection.from_pretrained(
                "h94/IP-Adapter", subfolder="models/image_encoder", torch_dtype=self.dtype, local_files_only=True
            )
        except:
            image_encoder = CLIPVisionModelWithProjection.from_pretrained(
                "h94/IP-Adapter", subfolder="models/image_encoder", torch_dtype=self.dtype
            )

        PipelineClass = StableDiffusionXLInpaintPipeline if "xl" in stabilityModel.lower() else StableDiffusionInpaintPipeline
        
        try:
            if stabilityModel.endswith(".safetensors"):
                pipe = PipelineClass.from_single_file(stabilityModel, torch_dtype=self.dtype, image_encoder=image_encoder, use_safetensors=True)
            else:
                pipe = PipelineClass.from_pretrained(stabilityModel, torch_dtype=self.dtype, image_encoder=image_encoder)
        except:
            pipe = PipelineClass.from_pretrained(stabilityModel, torch_dtype=self.dtype, image_encoder=image_encoder, use_safetensors=False)

        if hasattr(pipe, "safety_checker"): pipe.safety_checker = None
        
        try: pipe.enable_vae_slicing()
        except: pass
        if self.device == "cuda": pipe.enable_model_cpu_offload()
        else: pipe.to(self.device)
        
        pipe.load_ip_adapter(IP_ADAPTER_REPO, subfolder=IP_ADAPTER_SUBFOLDER, weight_name=IP_ADAPTER_FILENAME)
        
        return pipe

    # ✅ FIXED: ระบบ Slot แบ่งช่องชัดเจน กันคนซ้อนกัน
    def get_smart_coords(self, pos, depth, w, h, occupied_slots=[]):
        p = pos.upper()
        d = depth.upper()
        
        # 1. กำหนดขนาดตามระยะ (Scale) - ปรับให้กว้างขึ้นและสูงขึ้นแก้แขนหาย/หัวหาย
        if "FORE" in d: 
            scale_h = 0.90 # เกือบเต็มจอแนวตั้ง
            scale_w = 0.40 # กว้างหน่อย
            y_start = int(h * 0.05) # เริ่มเกือบติดขอบบน (แก้หัวขาด)
        elif "MID" in d: 
            scale_h = 0.70 
            scale_w = 0.30 
            y_start = int(h * 0.25)
        else: # BACK
            scale_h = 0.50 
            scale_w = 0.20 
            y_start = int(h * 0.45)

        char_h = int(h * scale_h)
        char_w = int(w * scale_w)
        bottom_y = y_start + char_h

        # 2. กำหนดตำแหน่ง X แบบ Slot (กันทับกัน)
        # แบ่งหน้าจอเป็น 3 ส่วน: 0-33%, 34-66%, 67-100%
        # แต่ละส่วนมี "จุดกึ่งกลาง" (Center Point) ของตัวเอง
        
        # ซ้าย
        if "LEFT" in p:
            slot_center = int(w * 0.20) 
        # ขวา
        elif "RIGHT" in p:
            slot_center = int(w * 0.80)
        # กลาง (Default)
        else: 
            slot_center = int(w * 0.50)

        # 🛑 Collision Check (แบบง่าย): ถ้าเลนนี้เต็มแล้ว ให้ขยับนิดหน่อย
        # (Logic นี้อาจต้องพัฒนาต่อถ้ามีคนเยอะมาก แต่เบื้องต้นใช้ Random jitter หรือ Offset)
        if p in occupied_slots:
            if "LEFT" in p: slot_center += int(w * 0.1) # ขยับเข้ากลางนิดนึง
            elif "RIGHT" in p: slot_center -= int(w * 0.1)
            elif "CENTER" in p: slot_center += int(w * 0.15) # หลบไปขวาหน่อย

        start_x = slot_center - (char_w // 2)
        end_x = start_x + char_w
        
        # Boundary Check (กันตกขอบจอ)
        if start_x < 0: 
            start_x = 0
            end_x = char_w
        if end_x > w:
            end_x = w
            start_x = w - char_w
        if bottom_y > h: 
            bottom_y = h

        return (start_x, y_start, end_x, bottom_y)

    def process_character_image(self, img_path):
        if not os.path.exists(img_path): return None
        return Image.open(img_path).convert("RGB")

    def run(self, scene_plan, output_path, character_refs):
        log_memory_usage("Start SD")
        pipe = None
        try:
            pipe = self.load_pipeline()
            
            env_desc = clean_prompt(scene_plan.get('environment', 'scene'))
            STYLE = "masterpiece, best quality, photorealistic, 8k, raw photo, ancient chinese wuxia style"
            
            # ✅ เพิ่ม Negative Prompt ดักเรื่องร่างกาย
            NEG = "people, humans, person, crowd, modern, western, ugly, blurry, watermark, text, bad anatomy, deformed body, missing head, cropped head, missing arms, extra limbs, floating limbs, mutated"
            
            base_prompt = f"{STYLE}, {env_desc}, (no humans:1.5), empty scenery, masterpiece"
            
            dummy_ref = Image.new("RGB", (224, 224), "black")

            # 1. Gen Background
            print("   Generating Background...")
            pipe.set_ip_adapter_scale(0.0)
            base_image = pipe(
                prompt=base_prompt, negative_prompt=NEG,
                image=Image.new("RGB", (IMG_WIDTH, IMG_HEIGHT), (128,128,128)),
                mask_image=Image.new("L", (IMG_WIDTH, IMG_HEIGHT), "white"),
                ip_adapter_image=dummy_ref, 
                height=IMG_HEIGHT, width=IMG_WIDTH, num_inference_steps=NUM_STEPS, strength=1.0
            ).images[0]

            try:
                base_image.save(output_path.replace(".png", "_00_background.png"))
            except: pass

            # 2. Add Characters
            # Sort Depth: Back -> Fore
            character_refs.sort(key=lambda x: 0 if "BACK" in x['depth'] else (1 if "MID" in x['depth'] else 2))
            
            occupied_slots = [] # เก็บประวัติว่าเลนไหนมีคนยืนแล้ว

            for i, char in enumerate(character_refs):
                name = char['name']
                ref_path = char['ref_path']
                position_key = char['position']
                
                print(f"   👤 Processing: {name} ({char['depth']}) | Ref: {os.path.basename(ref_path)}")
                
                ref_image = self.process_character_image(ref_path)
                if not ref_image: continue

                # ✅ ส่ง occupied_slots ไปเช็คชน
                x1, y1, x2, y2 = self.get_smart_coords(position_key, char['depth'], IMG_WIDTH, IMG_HEIGHT, occupied_slots)
                occupied_slots.append(position_key) # จดไว้ว่าเลนนี้ใช้แล้ว

                # สร้าง Mask
                mask = Image.new("L", (IMG_WIDTH, IMG_HEIGHT), 0)
                draw = ImageDraw.Draw(mask)
                draw.rectangle((x1, y1, x2, y2), fill=255)
                mask = mask.filter(ImageFilter.GaussianBlur(radius=10)) 
                
                pipe.set_ip_adapter_scale(0.85) 
                
                action = char['visual_action']
                # ✅ เพิ่ม "centered in frame, wide shot" เพื่อให้กล้องถอยออกมาหน่อย ไม่ซูมจนหัวขาด
                prompt = f"{STYLE}, full body shot of {name}, standing, {action}, highly detailed face, sharp eyes, masterpiece, centered in frame, wide shot, fitting in frame"
                print(f"      Prompt: {prompt}")

                base_image = pipe(
                    prompt=prompt, negative_prompt=NEG,
                    image=base_image,
                    mask_image=mask,
                    ip_adapter_image=ref_image, 
                    height=IMG_HEIGHT, width=IMG_WIDTH,
                    num_inference_steps=CHAR_STEPS, 
                    strength=1.0, 
                    guidance_scale=7.5
                ).images[0]

                try:
                    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', name)
                    base_image.save(output_path.replace(".png", f"_{i+1:02d}_{safe_name}.png"))
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