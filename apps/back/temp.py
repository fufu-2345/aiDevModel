async def processChunk(chunk_text: str, client: httpx.AsyncClient, extractModel: str):
    prompt = f"""
    Role:
    คุณคือ AI Visual Director ผู้เชี่ยวชาญด้านการถอดรหัสภาพจากนิยายเพื่อนำไปสร้างภาพประกอบ

    Task:
    อ่านข้อความ Input Text แล้วสกัดข้อมูล Entity (Character, Location, Item) ออกมาเป็น JSON

    Refined Logic for 'Character':
    ต้องแยกคุณลักษณะออกเป็น 2 ส่วนให้ชัดเจน:
    1. "IdentityTags": ลักษณะทางกายภาพที่ติดตัว เปลี่ยนแปลงยาก (เช่น สีผม, สีตา, ทรงผมหลัก, สีผิว, เพศ, รูปร่าง, อายุ, เผ่าพันธุ์)
    2. "ModifierTags": สิ่งที่เปลี่ยนแปลงได้ตามสถานการณ์ (เช่น เสื้อผ้า, เครื่องประดับ, คราบเลือด, รอยเปื้อน, อารมณ์, ท่าทาง)
    **Important Rule:** หากในข้อความมีการเปลี่ยนชุดหรือสถานะ ให้ยึด "รูปลักษณ์แรก" (Initial State) ที่ปรากฏในข้อความนั้นเป็นหลัก

    Requirements:
    - Name: ชื่อหลักที่เป็นทางการ
    - AltNames: ชื่อเล่น หรือฉายา (ถ้ามี)
    - Tags Output: **ขอเป็นภาษาอังกฤษ (English) เท่านั้น** คั่นด้วย comma (,) เน้นคำนามและคำคุณศัพท์

    Output Format (JSON Only):
    {{
        "entities": [
            {{
                "type": "Character", 
                "name": "ชื่อตัวละคร",
                "altNames": ["ชื่อเรียกอื่น"],
                "IdentityTags": "silver hair, blue eyes, tall, muscular, scar on left cheek", 
                "ModifierTags": "wearing tattered white shirt, bleeding arm, angry expression"
            }},
            {{
                "type": "Location",
                "name": "ชื่อสถานที่",
                "altNames": [],
                "VisualTags": "dark cave, wet floor, torch light" 
            }},
            {{
                "type": "Item",
                "name": "ชื่อวัตถุ",
                "altNames": [],
                "VisualTags": "rusty iron sword, glowing rune"
            }}
        ]
    }}

    Input Text:
    {chunk_text}
    """

    payload = {
        "model": extractModel,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": 4096, 
            "temperature": 0.5
        },
        "format": "json"
    }

    try:
        response = await client.post(ollamaURL, json=payload)
        response.raise_for_status()
        result_text = response.json().get("response", "")
        
        cleaned_text = result_text.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_text)
    except Exception as e:
        return None

@app.get("/extractEntities/{chapter_id}")
async def extract_entities2(chapter_id: int, session: Session = Depends(get_session)):
    start = time.perf_counter()
    
    chapter_obj = session.get(chapterContent, chapter_id)
    if not chapter_obj or not chapter_obj.chapterDetail:
        return {"result": "No content found in this chapter."}  
    
    chapterDetail = chapter_obj.chapterDetail
    lines = chapterDetail.split('\n')
    total_lines = len(lines)
    
    if total_lines < 10:
        chunks = [chapterDetail]
    else:
        chunk_size = (total_lines + 9) // 10
        overlap = 2
        step = max(1, chunk_size - overlap)
        chunks = []
        for i in range(0, total_lines, step):
            chunk_lines = lines[i:i + chunk_size]
            chunk_text = "\n".join(chunk_lines)
            chunks.append(chunk_text)
            if i + chunk_size >= total_lines:
                break
            
    print(f"{len(chunks)} chunks")
    results = []
    
    async with httpx.AsyncClient(timeout=1800.0) as client:
        for idx, chunk in enumerate(chunks):
            print(idx+1, ": ", len(chunks))
            res = await processChunk(chunk, client, extractModel)
            print(res)
            results.append(res)

    merged_entities = {}
    for res in results:
        if not res or not res.get("entities"):
            continue
        
        for entity in res["entities"]:
            e_type = entity.get("type")
            name = entity.get("name")
            
            if not e_type or not name:
                continue
                
            e_type = e_type.strip().capitalize() 
            name = name.strip()
            key = (e_type, name)
            
            current_tags_input = entity.get("VisualTags")
            if current_tags_input is None:
                current_tags = set()
            elif isinstance(current_tags_input, list): 
                current_tags = set(t.strip() for t in current_tags_input if t.strip())
            else:
                current_tags = set(t.strip() for t in str(current_tags_input).split(",") if t.strip())

            current_alts_input = entity.get("altNames")
            if current_alts_input is None:
                current_alts = set()
            elif isinstance(current_alts_input, list):
                current_alts = set(current_alts_input)
            else:
                current_alts = set([str(current_alts_input)])

            if key not in merged_entities:
                merged_entities[key] = {
                    "type": e_type,
                    "name": name,
                    "altNames": current_alts, 
                    "VisualTags": current_tags
                }
            else:
                merged_entities[key]["VisualTags"].update(current_tags)
                merged_entities[key]["altNames"].update(current_alts)

    final_output = {
        "characters": [],
        "locations": [],
        "items": []
    }

    for key, data in merged_entities.items():
        data["VisualTags"] = ", ".join(sorted(list(data["VisualTags"])))
        data["altNames"] = sorted(list(data["altNames"]))
        
        e_type_lower = data["type"].lower()
        
        if "character" in e_type_lower:
            final_output["characters"].append(data)
        elif "location" in e_type_lower:
            final_output["locations"].append(data)
        elif "item" in e_type_lower:
            final_output["items"].append(data)
        else:
            final_output["items"].append(data)
    print(f"Time: {time.perf_counter() - start:.3f} seconds")
    return final_output












เวอชั่นแรกสุด ดี แต่ Visual Tags only
prompt = f"""
    Role
    คุณคือ AI Assistant ผู้เชี่ยวชาญด้านการสกัดข้อมูลภาพ (Visual Extraction) สำหรับงาน Generative AI
    Task
    อ่านข้อความที่ได้รับ แล้วสกัด Entity 3 ประเภท:
    1. Character (ตัวละคร)
    2. Location (สถานที่)
    3. Item (วัตถุสำคัญ)
    Requirements:
    - Name: ระบุชื่อหลัก (Main Name) ที่เป็นทางการที่สุด
    - Alt Names: ระบุชื่อเล่น ฉายา หรือชื่อเรียกอื่น (ถ้ามี) ใส่ใน List
    - Visual Tags: ขอเฉพาะคำนามหรือคำคุณศัพท์ที่ระบุรูปลักษณ์ (เช่น ผมแดง, ชุดเกราะ, เก่าแก่) ห้ามใส่คำกิริยาหรือการกระทำ (เช่น เดิน, กิน, พูด, ต่อสู้) คั่นด้วยคอมมา
    Output Format (JSON Only):
    {{
        "entities": [
            {{
                "type": "Character",
                "name": "ชื่อหลัก",
                "altNames": ["ชื่อรอง1", "ชื่อรอง2"],
                "VisualTags": "tag1, tag2, tag3"
            }},
            {{
                "type": "Location",
                "name": "ชื่อสถานที่",
                "altNames": [],
                "VisualTags": "tag1, tag2"
            }}
        ]
    }}
    Input Text:
    {chunk_text}
    """
    
    
    
    
    
    Tags Output: เป็น eng
    prompt = f"""
    Role:
    คุณคือ AI Visual Director ผู้เชี่ยวชาญด้านการถอดรหัสภาพจากนิยายเพื่อนำไปสร้างภาพประกอบ

    Task:
    อ่านข้อความ Input Text แล้วสกัดข้อมูล Entity (Character, Location, Item) ออกมาเป็น JSON

    ต้องแยกคุณลักษณะออกเป็น 2 ส่วนให้ชัดเจน:
    1. "IdentityTags": ลักษณะทางกายภาพที่ติดตัว เปลี่ยนแปลงยาก (เช่น สีผม, สีตา, ทรงผมหลัก, สีผิว, เพศ, รูปร่าง, อายุ, เผ่าพันธุ์)
    2. "ModifierTags": สิ่งที่เปลี่ยนแปลงได้ตามสถานการณ์ (เช่น เสื้อผ้า, เครื่องประดับ, คราบเลือด, รอยเปื้อน, อารมณ์, ท่าทาง)
    **Important Rule:** หากในข้อความมีการเปลี่ยนชุดหรือสถานะ ให้ยึด "รูปลักษณ์แรก" (Initial State) ที่ปรากฏในข้อความนั้นเป็นหลัก

    Requirements:
    - Name: ชื่อหลักที่เป็นทางการ ภาษาไทย
    - AltNames: ชื่อเล่น หรือฉายา ภาษาไทย (ถ้ามี)
    - Tags Output: **ขอเป็นภาษาอังกฤษ (English) เท่านั้น** คั่นด้วย comma (,) เน้นคำนามและคำคุณศัพท์

    Output Format (JSON Only):
    {{
        "entities": [
            {{
                "type": "Character", 
                "name": "ชื่อตัวละคร",
                "altNames": ["ชื่อเรียกอื่น"],
                "IdentityTags": "silver hair, tall, muscular, scar on left cheek", 
                "ModifierTags": "wearing tattered white shirt, bleeding arm, angry expression"
            }},
            {{
                "type": "Location",
                "name": "ชื่อสถานที่",
                "altNames": [],
                "VisualTags": "dark cave, wet floort" 
            }},
            {{
                "type": "Item",
                "name": "ชื่อวัตถุ",
                "altNames": [],
                "VisualTags": "rusty iron sword, glowing rune"
            }}
        ]
    }}

    Input Text:
    {chunk_text}
    """
    
    
    เหมือนอันก่อนแต่ tag เป็นไทย
    prompt = f"""
    Role:
    คุณคือ AI Visual Director ผู้เชี่ยวชาญด้านการถอดรหัสภาพจากนิยายเพื่อนำไปสร้างภาพประกอบ

    Task:
    อ่านข้อความ Input Text แล้วสกัดข้อมูล Entity (Character, Location, Item) ออกมาเป็น JSON

    ต้องแยกคุณลักษณะออกเป็น 2 ส่วนให้ชัดเจน:
    1. "IdentityTags": ลักษณะทางกายภาพที่ติดตัว เปลี่ยนแปลงยาก (เช่น สีผม, สีตา, ทรงผมหลัก, สีผิว, เพศ, รูปร่าง, อายุ, เผ่าพันธุ์)
    2. "ModifierTags": สิ่งที่เปลี่ยนแปลงได้ตามสถานการณ์ (เช่น เสื้อผ้า, เครื่องประดับ, คราบเลือด, รอยเปื้อน, อารมณ์, ท่าทาง)
    **Important Rule:** หากมีหลายรูปลักษณ์ ให้ยึด "รูปลักษณ์แรก" ที่ปรากฏ

    Requirements:
    - Name: ชื่อหลักที่เป็นทางการ ภาษาไทย
    - AltNames: ชื่อเล่น หรือฉายา ภาษาไทย (ถ้ามี)
    - Visual Tags: ขอเฉพาะคำนามหรือคำคุณศัพท์ที่ระบุรูปลักษณ์ (เช่น ผมแดง, ชุดเกราะ, เก่าแก่) ห้ามใส่คำกิริยาหรือการกระทำ (เช่น เดิน, กิน, พูด, ต่อสู้) คั่นด้วยคอมมา 
    
    Output Format (JSON Only):
    {{
        "entities": [
            {{
                "type": "Character", 
                "name": "ชื่อตัวละคร",
                "altNames": ["ชื่อเรียกอื่น"],
                "IdentityTags": "tag1, tag2", 
                "ModifierTags": "tag1, tag2"
            }},
            {{
                "type": "Location",
                "name": "ชื่อสถานที่",
                "altNames": [],
                "VisualTags": "tag1, tag2"
            }},
            {{
                "type": "Item",
                "name": "ชื่อวัตถุ",
                "altNames": [],
                "VisualTags": "tag1, tag2"
            }}
        ]
    }}
    
    Input Text:
    {chunk_text}
    """