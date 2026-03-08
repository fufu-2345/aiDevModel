import os
import time
import threading
import queue
import uuid
import multiprocessing
import numpy as np
import soundfile as sf
import shutil
from fastapi import FastAPI, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse

app = FastAPI(title="F5-TTS Queue API")

task_queue = queue.Queue()
cuda_lock = threading.Lock()
results_dict = {}

# ฟังก์ชันสำหรับลบไฟล์หลังจากส่งให้ Main API เสร็จแล้ว
def cleanup_temp_file(filepath: str):
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"🧹 [Cleanup] ลบไฟล์ชั่วคราวเรียบร้อย: {filepath}", flush=True)
    except Exception as e:
        print(f"⚠️ [Cleanup] ลบไฟล์ไม่สำเร็จ: {e}", flush=True)

def run_f5_tts_th(text, ref_audio_path, ref_text, out_wav_path, result_queue, user_home):
    try:
        import os
        if user_home:
            os.environ["USERPROFILE"] = user_home
            os.environ["HOME"] = user_home
            os.environ["HF_HOME"] = os.path.join(user_home, ".cache", "huggingface")
            drive, path = os.path.splitdrive(user_home)
            os.environ["HOMEDRIVE"] = drive
            os.environ["HOMEPATH"] = path
            
        from f5_tts_th.tts import TTS
        import torch
        
        tts = TTS()
        infer_result = tts.infer(ref_audio=ref_audio_path, ref_text=ref_text, gen_text=text)
        
        # [FIX] ระบบตรวจจับข้อมูลเสียงและ Sample Rate แบบยืดหยุ่น ป้องกันโมเดลส่งค่ากลับมาสลับตำแหน่ง
        if isinstance(infer_result, (tuple, list)) and len(infer_result) >= 2:
            res0 = infer_result[0]
            res1 = infer_result[1]
            
            # เช็คว่าถ้า index 0 เป็นตัวเลขหลักหมื่น (Sample Rate) ให้เอาข้อมูลเสียงจาก index 1
            if isinstance(res0, (int, float, np.integer, np.floating)) and res0 >= 8000:
                sr = int(res0)
                raw_wav = res1
            # ถ้าเป็นรูปแบบปกติ index 1 คือ Sample Rate
            elif isinstance(res1, (int, float, np.integer, np.floating)) and res1 >= 8000:
                raw_wav = res0
                sr = int(res1)
            else:
                raw_wav = res0
                try: sr = int(res1)
                except: sr = 24000
        else:
            raw_wav = infer_result
            sr = 24000
        
        processed_wavs = []
        if isinstance(raw_wav, (list, tuple)):
            for w in raw_wav:
                if hasattr(w, "cpu"): w = w.detach().cpu().numpy()
                elif not isinstance(w, np.ndarray):
                    try: w = np.array(w, dtype=np.float32)
                    except Exception: continue
                processed_wavs.append(np.array(w, dtype=np.float32).flatten())
            wav = np.concatenate(processed_wavs) if processed_wavs else np.array([], dtype=np.float32)
        else:
            if hasattr(raw_wav, "cpu"): raw_wav = raw_wav.detach().cpu().numpy()
            wav = np.array(raw_wav, dtype=np.float32).flatten()
            
        wav = np.nan_to_num(wav).astype(np.float32)
        
        if wav.size == 0:
            wav = np.zeros(sr, dtype=np.float32) 
            
        sf.write(out_wav_path, wav, sr)
        
        del tts
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
        result_queue.put({"status": "success"})
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"   [Debug-Worker] ❌ พบข้อผิดพลาดร้ายแรง:\n{error_trace}", flush=True)
        result_queue.put({"status": "error", "error": str(e)})

def process_tts_task(task_id: str, text: str, ref_audio_path: str, ref_text: str, speaker_type: str):
    try:
        print(f"\n==================================================", flush=True)
        print(f"[Worker] 📥 กำลังประมวลผลคิว Task: {task_id}", flush=True)
        print(f"         🗣️  Speaker Type : {speaker_type}", flush=True)
        print(f"         📝 Text         : {text}", flush=True)
        print(f"         🎧 Ref Audio    : {ref_audio_path}", flush=True)
        print(f"==================================================", flush=True)
        
        out_wav_path = f"worker_out_{task_id}.wav"
        final_out_path = f"final_{task_id}.wav"

        with cuda_lock:
            current_home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or os.path.expanduser("~")
            
            result_queue = multiprocessing.Queue()
            p = multiprocessing.Process(
                target=run_f5_tts_th, 
                args=(text, ref_audio_path, ref_text, out_wav_path, result_queue, current_home)
            )
            p.start()
            p.join() 
            
            if not result_queue.empty():
                res = result_queue.get()
                if res["status"] == "error":
                    results_dict[task_id] = {"status": "error", "error": res['error']}
                    return
            else:
                results_dict[task_id] = {"status": "error", "error": "Worker process terminated unexpectedly."}
                return

        if not os.path.exists(out_wav_path):
            results_dict[task_id] = {"status": "error", "error": "Output file not generated"}
            return

        shutil.move(out_wav_path, final_out_path)

        print(f"[Worker] 🎉 Task: {task_id} เจนเสียงเสร็จแล้ว!", flush=True)
        results_dict[task_id] = {"status": "done", "file": final_out_path}

    except Exception as e:
        results_dict[task_id] = {"status": "error", "error": str(e)}

def worker_loop():
    while True:
        task = task_queue.get()
        if task is None: break
        task_id, text, ref_audio_path, ref_text, speaker_type = task
        process_tts_task(task_id, text, ref_audio_path, ref_text, speaker_type)
        task_queue.task_done()

threading.Thread(target=worker_loop, daemon=True).start()

@app.post("/internal/generate")
def generate_audio(
    background_tasks: BackgroundTasks, 
    text: str = Form(...),
    speaker_type: str = Form("narrator"),  
    ref_audio_path: str = Form(None),      
    ref_text: str = Form(None)             
):
    default_refs = {
        "male": {
            "audio": "F5sound/male.wav",
            "text": "เฮ้ยทุกคน เชื่อไหมว่าเดี๋ยวนี้ AI มันทำอะไรได้เยอะมากจริงๆ วันนี้ผมลองเล่นมาตัวนึง"
        },
        "female": {
            "audio": "F5sound/female.wav",
            "text": "เฮ้ยทุกคน เชื่อไหมว่าเดี๋ยวนี้ AI มันทำอะไรได้เยอะมากจริงๆ วันนี้ผมลองเล่นมาตัวนึง" 
        },
        "narrator": {
            "audio": "F5sound/narrator.wav", 
            "text": "เฮ้ยทุกคน เชื่อไหมว่าเดี๋ยวนี้ AI มันทำอะไรได้เยอะมากจริงๆ วันนี้ผมลองเล่นมาตัวนึง" 
        }
    }

    # [FIX] ล้างค่า String ให้สะอาดหมดจด ป้องกันการส่งค่ามามีช่องว่างหรือเคสแปลกๆ
    clean_stype = str(speaker_type).replace('"', '').replace("'", "").strip().lower() if speaker_type else "narrator"
    stype = clean_stype if clean_stype in default_refs else "male"

    # [FIX] ตรวจสอบกรณีที่ FastAPI ได้รับข้อความคำว่า "None" (เป็น String) มาจาก Client
    final_ref_audio = ref_audio_path if ref_audio_path and str(ref_audio_path).strip().lower() != "none" else default_refs[stype]["audio"]
    final_ref_text = ref_text if ref_text and str(ref_text).strip().lower() != "none" else default_refs[stype]["text"]

    task_id = str(uuid.uuid4())[:8]
    results_dict[task_id] = {"status": "pending"}
    
    # [UPDATE] ส่ง stype ที่ผ่านการจับคู่และคัดกรองอย่างถูกต้องแล้วไปแสดงใน Log
    task_queue.put((task_id, text, final_ref_audio, final_ref_text, stype))
    
    timeout = 600
    start_time = time.time()
    
    while results_dict[task_id]["status"] == "pending":
        if time.time() - start_time > timeout:
            results_dict.pop(task_id, None)
            raise HTTPException(status_code=504, detail="Timeout")
        time.sleep(1)
        
    result = results_dict.pop(task_id)
    
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        
    background_tasks.add_task(cleanup_temp_file, result["file"])
    
    return FileResponse(result["file"], media_type="audio/wav")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    import uvicorn
    uvicorn.run("F5:app", host="0.0.0.0", port=8001, reload=False)