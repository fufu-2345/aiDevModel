from fastapi import Depends, HTTPException, APIRouter, UploadFile, File, Form
from sqlmodel import Session
from database import get_session
from models import movieTitle, chapterContent
import fitz 
import re
import time

router = APIRouter(
    prefix="/uploadPDF",
    tags=["uploadPDF"]
)

def clearASCII(text: str) -> str:
    if not text:
        return ""
    replace_dict = {
        '\uf700': 'ฐ', '\uf701': 'ญ', '\uf702': 'ฐ', '\uf703': 'ญ',
        '\uf704': 'ญ', '\uf705': 'ฐ', '\uf706': 'ญ', '\uf707': 'ฐ',
        '\uf708': 'ญ', '\uf709': 'ญ', '\uf70a': '่', '\uf70b': '้',
        '\uf70c': '๊', '\uf70d': '๋', '\uf70e': '์', '\uf70f': 'ํ',
        '\uf710': 'ั', '\uf711': '็', '\uf712': 'ิ', '\uf713': 'ี',
        '\uf714': 'ึ', '\uf715': 'ื', '\uf716': 'ุ', '\uf717': 'ู',
        '\uf718': 'ุ', '\uf719': 'ู', '\uf71a': '็',
    }
    clearedText = text
    for pua_char, std_char in replace_dict.items():
        clearedText = clearedText.replace(pua_char, std_char)
    return clearedText

def clearThaiTypeing(text: str) -> str:
    if not text:
        return ""
    corrections = {
        "เปิน": "เป็น",
        "เปญด": "เปิด",
        "ปฐ": "ปี",
        "ปญอม": "ป้อม",
        "ฝฐา": "ฝ่า",
        "ฝญก": "ฝึก",
        "ฝฐาย": "ฝ่าย",
        "ฝฐ": "ฝี",
        "ฟญน": "ฟืน",    
        "ฟญา": "ฟ้า",
        "เฟญง": "เฟิง",
    }
    fixed_text = text
    for wrong_word, correct_word in corrections.items():
        fixed_text = fixed_text.replace(wrong_word, correct_word)    
    return fixed_text

def clearNewline(text: str) -> str:
    def replacer(match):
        found = match.group()
        if found.count('\n') > 1:
            return '\n'
        if ' \n' in found:
            return '\n'
        return ' '
    pattern = r"[ ]*\n[ \n]*"
    return re.sub(pattern, replacer, text).strip()

# อัพโหลดไฟล์ pdf
@router.post("/")
async def uploadPDF(
    title: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="This is not a PDF file")
    start_time = time.perf_counter()
    file_content = await file.read()
    
    new_movie = movieTitle(movieTitle=title, episodeAmount=0, picPath="")
    session.add(new_movie)
    session.commit()
    session.refresh(new_movie) 
    
    try:
        found_chapters_data = []
        chapter_map = [] 

        with fitz.open(stream=file_content, filetype="pdf") as doc:
            total_pages = len(doc)
            for i, page in enumerate(doc):
                raw_text = page.get_text()
                if not raw_text or not raw_text.strip():
                    continue
                
                lines = raw_text.split('\n')
                
                for line in lines[:1]:
                    match = re.search(r'ตอนที่\s*(\d+)', line)
                    if match:
                        found_chap_num = int(match.group(1))
                        if not chapter_map or chapter_map[-1]['num'] != found_chap_num:
                            chapter_map.append({
                                'num': found_chap_num,
                                'start_page': i
                            })
                        break 
            for idx, chap in enumerate(chapter_map):
                start_p = chap['start_page']
                end_p = chapter_map[idx+1]['start_page'] - 1 if (idx + 1 < len(chapter_map)) else total_pages - 1
                chapter_full_content = []
                chapter_title_text = ""
                for p_idx in range(start_p, end_p + 1):
                    page = doc[p_idx]
                    page_text = clearASCII(page.get_text() or "")
                    page_text = clearThaiTypeing(page_text)
                    page_text = clearNewline(page_text)
                    if p_idx == start_p:
                        lines = page_text.split('\n')
                        header_found = False
                        
                        for line in lines:
                            if not header_found and re.search(r'ตอนที่\s*' + str(chap['num']), line):
                                title_match = re.search(r'ตอนที่\s*\d+\s*(.*)', line)
                                if title_match:
                                    chapter_title_text = title_match.group(1).strip()
                                header_found = True
                            else:
                                chapter_full_content.append(line)
                    else:
                        chapter_full_content.append(page_text)
                
                final_title = chapter_title_text if chapter_title_text else f"ตอนที่ {chap['num']}"
                
                new_chapter = chapterContent(
                    episodeNumber=float(chap['num']),
                    chapterTitle=final_title,
                    chapterDetail="\n".join(chapter_full_content).strip(),
                    movieId=new_movie.id
                )
                session.add(new_chapter)
                found_chapters_data.append(new_chapter)
            new_movie.episodeAmount = len(found_chapters_data)
            session.add(new_movie)
            session.commit()
            print(f"Upload time use: {time.perf_counter()-start_time:.3f} seconds", flush=True)
            return {
                "status": "success",
                "movie_id": new_movie.id,
                "total_chapters_found": len(found_chapters_data),
                "chapters": [c.chapterTitle for c in found_chapters_data],
            }

    except Exception as e:
        print(f"Error processing PDF: {e}")
        session.delete(new_movie)
        session.commit()
        raise HTTPException(status_code=500, detail=f"PDF Processing Error: {e}")
