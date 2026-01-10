# copy patse ใช้ได้เลย

@app.get("/tempReadPDF")
def readddpdf(file_path: str = "คัมภีร์วิถีเซียน0001-0500.pdf"):
    path = file_path.strip('"').strip("'")
    
    try:
        chapter_map = []
        
        with fitz.open(path) as doc:
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
            if not chapter_map:
                return {"status": "empty", "message": "ไม่พบ Pattern 'ตอนที่' ในไฟล์"}
            first_chap = chapter_map[0]
            start_p = first_chap['start_page']
            if len(chapter_map) > 1:
                end_p = chapter_map[1]['start_page'] - 1 
            else:
                end_p = total_pages - 1
            
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
                        if not header_found and re.search(r'ตอนที่\s*' + str(first_chap['num']), line):
                            title_match = re.search(r'ตอนที่\s*\d+\s*(.*)', line)
                            if title_match:
                                chapter_title_text = title_match.group(1).strip()
                            header_found = True
                        else:
                            chapter_full_content.append(line)
                else:
                    chapter_full_content.append(page_text)
            
            final_title = chapter_title_text if chapter_title_text else f"ตอนที่ {first_chap['num']}"
            
            # Return เฉพาะ Object ของตอนแรก
            return {
                "episodeNumber": float(first_chap['num']),
                "chapterTitle": final_title,
                "chapterDetail": "\n".join(chapter_full_content).strip()
            }

    except Exception as e:
        print(f"Error processing PDF: {e}")
        raise HTTPException(status_code=500, detail=f"error: {str(e)}")
    
@app.get("/tempReadPDFnoClear")
def readddpdf(file_path: str = "คัมภีร์วิถีเซียน0001-0500.pdf"):
    path = file_path.strip('"').strip("'")
    
    try:
        chapter_map = []
        
        with fitz.open(path) as doc:
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
            if not chapter_map:
                return {"status": "empty", "message": "ไม่พบ Pattern 'ตอนที่' ในไฟล์"}
            first_chap = chapter_map[0]
            start_p = first_chap['start_page']
            if len(chapter_map) > 1:
                end_p = chapter_map[1]['start_page'] - 1 
            else:
                end_p = total_pages - 1
            
            chapter_full_content = []
            chapter_title_text = ""
            
            for p_idx in range(start_p, end_p + 1):
                page = doc[p_idx]
                page_text = clearASCII(page.get_text() or "")
                page_text = clearThaiTypeing(page_text)
                # page_text = clearNewline(page_text)
                if p_idx == start_p:
                    lines = page_text.split('\n')
                    header_found = False
                    
                    for line in lines:
                        if not header_found and re.search(r'ตอนที่\s*' + str(first_chap['num']), line):
                            title_match = re.search(r'ตอนที่\s*\d+\s*(.*)', line)
                            if title_match:
                                chapter_title_text = title_match.group(1).strip()
                            header_found = True
                        else:
                            chapter_full_content.append(line)
                else:
                    chapter_full_content.append(page_text)
            
            final_title = chapter_title_text if chapter_title_text else f"ตอนที่ {first_chap['num']}"
            
            # Return เฉพาะ Object ของตอนแรก
            return {
                "episodeNumber": float(first_chap['num']),
                "chapterTitle": final_title,
                "chapterDetail": "\n".join(chapter_full_content).strip()
            }

    except Exception as e:
        print(f"Error processing PDF: {e}")
        raise HTTPException(status_code=500, detail=f"error: {str(e)}")