import os
import sys
import torch 
import torch.nn as nn
import numpy as np
import uuid
import traceback
from fastapi import FastAPI, HTTPException, Form
from fastapi.responses import FileResponse, HTMLResponse
from torch.nn.attention import SDPBackend, sdpa_kernel

# 1. 🔍 ตรวจจับการ์ดจอ (CUDA)
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"[Worker] 🖥️ อุปกรณ์ที่ใช้ประมวลผล: {device.upper()}")

# 🚨 บังคับให้การคำนวณเป็น Float32 เท่านั้น
torch.set_default_dtype(torch.float32)

# ปิดระบบเร่งความเร็วที่มักจะมีปัญหากับการ์ดจอรุ่นเก่า (Pascal Architecture)
torch.backends.cudnn.allow_tf32 = False 
torch.backends.cudnn.benchmark = False

# จัดการ Path แคชของโมเดล
os.environ["CACHED_PATH_CACHE_ROOT"] = os.path.abspath(os.path.join(os.getcwd(), ".cache", "cached_path"))
if sys.platform == "win32" and "USERPROFILE" not in os.environ:
    os.environ["USERPROFILE"] = os.path.abspath(os.getcwd())

try:
    from f5_tts_th.tts import TTS
    import soundfile as sf
    import librosa
    has_f5 = True
except ImportError as e:
    has_f5 = False
    print(f"[Worker] ERROR: ไม่สามารถ import F5-TTS ได้: {e}")

app = FastAPI(title="F5-TTS Worker (GPU/CUDA - Strict FP32)")

tts_model = None
if has_f5:
    print(f"[Worker] ⏳ กำลังโหลดโมเดล F5-TTS ลงบน {device.upper()}...")
    try:
        tts_model = TTS(model="v1") 
        print("[Worker] 🔧 กำลังปรับโครงสร้างโมเดลให้เข้ากับ GTX 1050 (บังคับ Float32)...")
        for name, obj in tts_model.__dict__.items():
            if isinstance(obj, nn.Module):
                obj.to(torch.float32)
                
        print(f"[Worker] ✅ โหลดโมเดลสำเร็จ พร้อมรับงานบน {device.upper()} แล้ว!")
    except Exception as e:
        print(f"[Worker] ❌ โหลดโมเดลไม่สำเร็จ: {e}")

REF_AUDIO_PATH = "narrator.wav"
REF_TEXT = "เฮ้ยทุกคน เชื่อไหมว่าเดี๋ยวนี้ AI มันทำอะไรได้เยอะมากจริงๆ วันนี้ผมลองเล่นมาตัวนึง"

# --- ✂️ ฟังก์ชันทำความสะอาดเสียง (ปรับใหม่ให้ไม่กินหัวท้ายคำ) ---
def clean_and_pad_audio(wav, sr=24000):
    """ตัดเสียงสูดลมหายใจ/ความเงียบส่วนเกินทิ้ง แล้วเติมช่องว่าง 0.6 วินาทีให้ตำแหน่งเริ่มเป๊ะทุกครั้ง"""
    wav_1d = wav.flatten()
    try:
        # 1. ลดความดุลงจาก 45 เป็น 50 เพื่อรักษาหางเสียงที่แผ่วเบา
        intervals = librosa.effects.split(wav_1d, top_db=50, frame_length=1024, hop_length=256)
        
        if len(intervals) > 0:
            start_idx = intervals[0][0]
            end_idx = intervals[-1][1]
            
            # 2. เผื่อหัว 0.15s และเผื่อท้ายให้ยาวขึ้นเป็น 0.5s ป้องกันหางเสียงกุด
            margin_start = int(0.15 * sr)
            margin_end = int(0.50 * sr)
            start_idx = max(0, start_idx - margin_start)
            end_idx = min(len(wav_1d), end_idx + margin_end)
            
            trimmed_wav = wav_1d[start_idx:end_idx]
            
            # 3. เพิ่ม "ความเงียบจำลอง" 0.6 วินาที
            silence_pad = np.zeros(int(0.6 * sr), dtype=trimmed_wav.dtype)
            
            final_wav = np.concatenate((silence_pad, trimmed_wav, silence_pad))
            print(f"[Audio Cleaner] 🎯 ตัดทิ้งจนเจอเสียงจริงที่: {start_idx/sr:.2f}s | ความยาวใหม่: {len(final_wav)/sr:.2f}s")
            return final_wav
            
    except Exception as e:
        print(f"[Audio Cleaner] ❌ Algorithm Error: {e}")
        
    return wav_1d

# ==========================================================
# 1. 🌐 ROUTE สำหรับเทสผ่าน Browser (เวอร์ชัน UI แยกหน้าเว็บ)
# ==========================================================
@app.get("/test_clone")
def test_clone_browser():
    # เอาส่วนที่แปลงจุดไข่ปลา (...) ออกตามรีเควสต์ครับ ส่งเข้าตรงๆ เลย
    text_to_gen = "หานลี่เดินทางด้วยความเร็วที่น่าตกใจจนเหล่าผู้บําเพ็ญเพียรต่างหวาดกลัว และ มาถึงใกล้ๆ เมืองดาวจรัสฟ้าในที่สุด เมื่อเห็นว่าอีกไม่กี่วันก็จะถึงแล้ว หานลี่จึงถอดผ้าคลุมออกแล้วบินด้วยความเร็วปกติ ทะเลแถบนี้ในตอนนี้จะต้องมีผู้บําเพ็ญเพียรน้อยใหญ่อยู่มากมาย อาจจะมีผู้บําเพ็ญเพียรระดับก่อกําเนิดอยู่ด้วยเช่นกัน"
    
    print(f"[Worker] 📥 ได้รับคำสั่ง TEST จากเบราว์เซอร์\n[ข้อความที่จะให้อ่าน]: {text_to_gen}")
    
    if not has_f5 or tts_model is None:
        raise HTTPException(status_code=500, detail="ระบบโมเดล F5-TTS ยังไม่พร้อมทำงาน")
        
    if not os.path.exists(REF_AUDIO_PATH):
        raise HTTPException(status_code=500, detail=f"ไม่พบไฟล์เสียงต้นแบบที่: {REF_AUDIO_PATH}")

    output_filename = "demo_output.wav" 
    padded_ref_path = f"temp_narrator_{uuid.uuid4().hex[:8]}.wav"
    
    try:
        print(f"[Worker] ⚙️ กำลังเริ่มรัน AI ด้วย {device.upper()}...")
        
        audio_data, sr = sf.read(REF_AUDIO_PATH)
        silence_duration = 0.6  
        silence_frames = int(sr * silence_duration)
        
        if len(audio_data.shape) == 1:
            silence = np.zeros(silence_frames, dtype=audio_data.dtype)
        else:
            silence = np.zeros((silence_frames, audio_data.shape[1]), dtype=audio_data.dtype)
            
        padded_audio = np.concatenate((audio_data, silence))
        sf.write(padded_ref_path, padded_audio, sr)

        if device == "cuda":
            torch.cuda.empty_cache()
            
        with torch.no_grad():
            with sdpa_kernel(SDPBackend.MATH):
                wav = tts_model.infer(
                    ref_audio=padded_ref_path, 
                    ref_text=REF_TEXT,
                    gen_text=text_to_gen,
                    step=32,        
                    cfg=1.8,  
                    speed=0.9     
                )
        
        wav_np = np.array(wav)
        if not (np.isnan(wav_np).any() or np.isinf(wav_np).any() or np.all(wav_np == 0)):
            print(f"[Worker] ✅ เจนคลื่นเสียงสำเร็จ! เข้าสู่กระบวนการ Trim...")
            wav_np = clean_and_pad_audio(wav_np, 24000)

        sf.write(output_filename, wav_np, 24000)
        
        if os.path.exists(padded_ref_path):
            os.remove(padded_ref_path)
            
        print(f"[Worker] 🎉 เจนเสียงเสร็จแล้ว! กำลังส่งหน้า UI กลับไป")
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>F5-TTS Worker UI</title>
            <meta charset="utf-8">
            <style>
                body {{ background: #121212; color: #ffffff; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
                .card {{ background: #1e1e1e; padding: 2.5rem; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); text-align: center; border: 1px solid #333; max-width: 600px; }}
                h2 {{ margin-top: 0; color: #4CAF50; }}
                .text-box {{ background: #2a2a2a; padding: 15px; border-radius: 8px; margin: 20px 0; font-style: italic; color: #ccc; text-align: left; }}
                audio {{ margin-top: 10px; width: 100%; outline: none; }}
                .hint {{ color: #888; font-size: 0.85em; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h2>✅ สร้างเสียงเสร็จสมบูรณ์!</h2>
                <div class="text-box">
                    <b>ข้อความที่ AI อ่าน:</b><br>{text_to_gen}
                </div>
                <audio controls autoplay src="/listen_demo?t={uuid.uuid4().hex}"></audio>
                <div class="hint">💡 นำระบบแปลงจุดไข่ปลาออกแล้วครับ</div>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        if os.path.exists(padded_ref_path): os.remove(padded_ref_path)
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================================
# 1.5 🎵 ROUTE สำหรับให้เบราว์เซอร์สตรีมเสียง
# ==========================================================
@app.get("/listen_demo")
def listen_demo():
    if os.path.exists("demo_output.wav"):
        return FileResponse("demo_output.wav", media_type="audio/wav")
    raise HTTPException(status_code=404, detail="ยังไม่มีไฟล์เสียงถูกสร้าง")

# ==========================================================
# 🚀 ROUTE หลัก: สำหรับให้ App A (Main API) เรียกใช้งานจริง
# ==========================================================
@app.post("/internal/generate")
def generate_audio_for_main_api(text: str = Form(...)):
    print(f"[Worker] 📥 ได้รับงานจาก MAIN API\n[ประโยคที่จะให้ AI อ่าน]: {text}")
    
    if not has_f5 or tts_model is None:
        raise HTTPException(status_code=500, detail="ระบบโมเดล F5-TTS ยังไม่พร้อมทำงาน")
        
    output_filename = f"worker_out_{uuid.uuid4().hex[:8]}.wav"
    padded_ref_path = f"temp_narrator_{uuid.uuid4().hex[:8]}.wav"
    
    try:
        print(f"[Worker] ⚙️ กำลังเริ่มรัน AI ด้วย {device.upper()}...")
        audio_data, sr = sf.read(REF_AUDIO_PATH)
        silence_duration = 0.6  
        
        silence = np.zeros(int(sr * silence_duration), dtype=audio_data.dtype) if len(audio_data.shape) == 1 else np.zeros((int(sr * silence_duration), audio_data.shape[1]), dtype=audio_data.dtype)
        sf.write(padded_ref_path, np.concatenate((audio_data, silence)), sr)

        if device == "cuda": torch.cuda.empty_cache()
            
        # 🚨 เอา autocast ออก และเปลี่ยน step เป็น 32
        with torch.no_grad(), sdpa_kernel(SDPBackend.MATH):
            wav = tts_model.infer(
                ref_audio=padded_ref_path, 
                ref_text=REF_TEXT,
                gen_text=text,
                step=32, cfg=1.8, speed=0.9     
            )
        
        wav_np = np.array(wav)
        if not (np.isnan(wav_np).any() or np.isinf(wav_np).any() or np.all(wav_np == 0)):
            wav_np = clean_and_pad_audio(wav_np, 24000)

        sf.write(output_filename, wav_np, 24000)
        
        if os.path.exists(padded_ref_path): os.remove(padded_ref_path)
            
        print(f"[Worker] 🎉 เจนเสียงเสร็จแล้ว ส่งให้ Main API!")
        return FileResponse(output_filename, media_type="audio/wav")
        
    except Exception as e:
        if os.path.exists(padded_ref_path): os.remove(padded_ref_path)
        raise HTTPException(status_code=500, detail=str(e))