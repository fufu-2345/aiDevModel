import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from models import chapterContent, movieTitle, ytVideo
from database import get_session

router = APIRouter(
    prefix="/yt",
    tags=["yt"]
)

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def get_youtube_client():
    creds = None
    
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                raise Exception("ไม่พบไฟล์ credentials.json กรุณาตรวจสอบตำแหน่งไฟล์")
                
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('youtube', 'v3', credentials=creds)

@router.get("/upload/{chapter_id}")
async def upload_chapter_to_youtube(
    chapter_id: int, 
    session: Session = Depends(get_session)
):
    chapter = session.get(chapterContent, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูล Chapter นี้")
        
    movie = session.get(movieTitle, chapter.movieId)
    if not movie:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูล Movie ของ Chapter นี้")

    yt_title = f"{movie.movieTitle} | EP {chapter.episodeNumber}: {chapter.chapterTitle}"
    video_path = chapter.vdoPath
    thumbnail_path = chapter.picPath

    if not video_path:
        raise HTTPException(status_code=400, detail="ไม่พบ vdoPath สำหรับอัปโหลด")

    try:
        youtube = get_youtube_client()
        
        body = {
            "snippet": {
                "title": yt_title,
                "description": f"รับชม {movie.movieTitle} ตอนที่ {chapter.episodeNumber}",
                "categoryId": "22"
            },
            "status": {
                "privacyStatus": "private"
            }
        }

        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        
        print(f"กำลังอัปโหลดวิดีโอ: {yt_title} ...")
        upload_request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )
        response = upload_request.execute()
        
        video_id = response['id']
        yt_url = f"https://www.youtube.com/watch?v={video_id}"
        print(f"อัปโหลดวิดีโอสำเร็จ! URL: {yt_url}")

        if thumbnail_path:
            print("กำลังอัปโหลด Thumbnail...")
            try:
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_path)
                ).execute()
                print("อัปโหลด Thumbnail สำเร็จ!")
            except Exception as thumb_e:
                print(f"คำเตือน: อัปโหลด Thumbnail ไม่สำเร็จ ({str(thumb_e)}) แต่วิดีโอหลักอัปโหลดไปแล้ว")

        new_yt_video = ytVideo(
            movieTitleId=movie.id,
            chaptercontentId=chapter.id,
            videoUrl=yt_url,
            viewCount=0,
            likeCount=0
        )
        session.add(new_yt_video)
        session.commit()
        session.refresh(new_yt_video)

        return {
            "message": "อัปโหลดวิดีโอลง YouTube และบันทึกข้อมูลสำเร็จ",
            "video_url": yt_url,
            "data": new_yt_video
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการอัปโหลด: {str(e)}")