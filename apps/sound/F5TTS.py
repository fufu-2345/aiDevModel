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

def cleanup_temp_file(filepath: str):
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        print(f"err: {e}", flush=True)

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
        
        if isinstance(infer_result, (tuple, list)) and len(infer_result) >= 2:
            res0 = infer_result[0]
            res1 = infer_result[1]
            
            if isinstance(res0, (int, float, np.integer, np.floating)) and res0 >= 8000:
                sr = int(res0)
                raw_wav = res1
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
        result_queue.put({"status": "error", "error": str(e)})

def process_tts_task(task_id: str, text: str, ref_audio_path: str, ref_text: str, speaker_type: str):
    try:
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

    clean_stype = str(speaker_type).replace('"', '').replace("'", "").strip().lower() if speaker_type else "narrator"
    stype = clean_stype if clean_stype in default_refs else "male"
    
    final_ref_audio = default_refs[stype]["audio"]
    final_ref_text = default_refs[stype]["text"]

    task_id = str(uuid.uuid4())[:8]
    results_dict[task_id] = {"status": "pending"}
    
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

def split_thai_to_segments(text: str, max_chars: int = 60) -> list[str]:
    """
    แบ่งข้อความภาษาไทยเป็น segment โดย:
    1. ตัดที่ space (' ') เป็นหลัก  → หยุดพูดตรง space เปะๆ
    2. ถ้า segment ยาวเกิน max_chars bytes → แบ่งต่อตรงเครื่องหมายวรรคตอน
    3. แต่ละ segment จะถูก gen แยก แล้วค่อย concat
    """
    # แยกด้วย space ก่อน
    parts = text.split(" ")
    
    segments = []
    buffer = ""
    
    for part in parts:
        part = part.strip()
        if not part:
            # เจอ space → flush buffer เป็น segment ใหม่ (หยุดพูด)
            if buffer:
                segments.append(buffer.strip())
                buffer = ""
            continue
        
        candidate = (buffer + " " + part).strip() if buffer else part
        
        if len(candidate.encode("utf-8")) <= max_chars:
            buffer = candidate
        else:
            # buffer เต็มแล้ว → flush แล้วเริ่ม buffer ใหม่
            if buffer:
                segments.append(buffer.strip())
            buffer = part
    
    if buffer:
        segments.append(buffer.strip())
    
    return [s for s in segments if s]


# ─────────────────────────────────────────────
# ฟังก์ชัน generate แยกทีละ segment แล้ว concat
# ─────────────────────────────────────────────
def generate_segmented(
    task_id_prefix: str,
    gen_text: str,
    ref_audio: str,
    ref_text: str,
    stype: str,
    silence_ms: int = 300,       # หยุดพัก (ms) ตรง space แต่ละช่อง
    max_chars: int = 60,
) -> str:
    """
    แบ่ง gen_text ตาม space → gen ทีละ segment → concat พร้อม silence → คืน path
    """
    segments = split_thai_to_segments(gen_text, max_chars=max_chars)
    print(f"[Segmented TTS] แบ่งได้ {len(segments)} segment:", flush=True)
    for i, s in enumerate(segments):
        print(f"  [{i}] {s}", flush=True)

    audio_parts = []
    sample_rate = None

    for i, seg in enumerate(segments):
        seg_task_id = f"{task_id_prefix}_seg{i}"
        results_dict[seg_task_id] = {"status": "pending"}
        
        task_queue.put((seg_task_id, seg, ref_audio, ref_text, stype))
        
        # รอผล
        timeout = 300
        start = time.time()
        while results_dict[seg_task_id]["status"] == "pending":
            if time.time() - start > timeout:
                results_dict.pop(seg_task_id, None)
                raise RuntimeError(f"Timeout on segment {i}")
            time.sleep(0.5)
        
        result = results_dict.pop(seg_task_id)
        if result["status"] == "error":
            raise RuntimeError(f"Segment {i} error: {result.get('error')}")
        
        # อ่าน audio
        audio_data, sr = sf.read(result["file"])
        cleanup_temp_file(result["file"])
        
        if sample_rate is None:
            sample_rate = sr
        
        audio_parts.append(audio_data)
        
        # เพิ่ม silence หลังแต่ละ segment (จำลองการหยุดตรง space)
        silence_samples = int(sr * silence_ms / 1000)
        silence = np.zeros((silence_samples,) if audio_data.ndim == 1 
                           else (silence_samples, audio_data.shape[1]))
        audio_parts.append(silence)

    # ลบ silence ก้อนสุดท้ายออก (ไม่ต้องหยุดตอนจบ)
    if audio_parts:
        audio_parts = audio_parts[:-1]

    # รวม audio ทั้งหมด
    final_audio = np.concatenate(audio_parts, axis=0)
    
    output_path = f"temp_output_{task_id_prefix}.wav"
    sf.write(output_path, final_audio, sample_rate)
    
    return output_path

@app.get("/test")
def debug_generate(background_tasks: BackgroundTasks):
    test_gen_text = (
        "หานลี่เดินทางด้วยความเร็วที่น่าตกใจจนเหล่าผู้บําเพ็ญเพียรต่างหวาดกลัว "
        "และมาถึงใกล้ๆ เมืองดาวจรัสฟ้าในที่สุด "
        "เมื่อเห็นว่าอีกไม่กี่วันก็จะถึงแล้ว "
        "หานลี่จึงถอดผ้าคลุมออกแล้วบินด้วยความเร็วปกติ "
        "ทะเลแถบนี้"
    )

    stype = "narrator"
    ref_audio = "F5sound/narrator.wav"
    ref_text = "เฮ้ยทุกคน เชื่อไหมว่าเดี๋ยวนี้ AI มันทำอะไรได้เยอะมากจริงๆ วันนี้ผมลองเล่นมาตัวนึง"

    task_id = "dbg_" + str(uuid.uuid4())[:4]

    print(f"\n[Debug API] 🛠️ gen_text:\n{test_gen_text}", flush=True)

    try:
        output_file = generate_segmented(
            task_id_prefix=task_id,
            gen_text=test_gen_text,
            ref_audio=ref_audio,
            ref_text=ref_text,
            stype=stype,
            silence_ms=300,   # ← ปรับตรงนี้ได้ = ระยะหยุดตรง space (ms)
            max_chars=60,     # ← ปรับตรงนี้ได้ = ขนาด segment สูงสุด (bytes)
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    background_tasks.add_task(cleanup_temp_file, output_file)
    return FileResponse(output_file, media_type="audio/wav")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    import uvicorn
    uvicorn.run("F5:app", host="0.0.0.0", port=8001, reload=False)