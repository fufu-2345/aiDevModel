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

SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.readonly'
]

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
    # public or private
    isPublic: bool = True,
    session: Session = Depends(get_session)
):
    chapter = session.get(chapterContent, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูล Chapter นี้")
        
    movie = session.get(movieTitle, chapter.movieId)
    if not movie:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูล Movie ของ Chapter นี้")

    ep_display = int(chapter.episodeNumber) if chapter.episodeNumber % 1 == 0 else chapter.episodeNumber

    yt_title = f"{movie.movieTitle} | EP {ep_display}: {chapter.chapterTitle}"
    video_path = chapter.vdoPath
    thumbnail_path = chapter.picPath

    if not video_path:
        raise HTTPException(status_code=400, detail="ไม่พบ vdoPath สำหรับอัปโหลด")

    privacy_status = "public" if isPublic else "private"

    try:
        youtube = get_youtube_client()
        
        body = {
            "snippet": {
                "title": yt_title,
                "description": "Thank for watching",
                "categoryId": "22"
            },
            "status": {
                "privacyStatus": privacy_status
            }
        }

        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        
        upload_request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )
        response = upload_request.execute()
        
        video_id = response['id']
        yt_url = f"https://www.youtube.com/watch?v={video_id}"

        if thumbnail_path:
            try:
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_path)
                ).execute()
            except Exception as thumb_e:
                print(f"Thumbnail error: {str(thumb_e)}")

        statement = select(ytVideo).where(ytVideo.chaptercontentId == chapter.id)
        existing_yt_videos = session.exec(statement).all()

        if existing_yt_videos:
            saved_video = existing_yt_videos[0]
            saved_video.videoUrl = yt_url
            saved_video.viewCount = 0
            saved_video.likeCount = 0
            session.add(saved_video)
            
            if len(existing_yt_videos) > 1:
                for duplicate in existing_yt_videos[1:]:
                    session.delete(duplicate)
                    
            session.commit()
            session.refresh(saved_video)
        else:
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
            saved_video = new_yt_video

        return {
            "message": "อัปโหลดวิดีโอลง YouTube และบันทึกข้อมูลสำเร็จ",
            "video_url": yt_url,
            "data": saved_video
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการอัปโหลด: {str(e)}")

@router.get("/stats/{chapter_id}")
def get_and_update_yt_stats(
    chapter_id: int, 
    refresh: bool = False,
    session: Session = Depends(get_session)
):
    statement = select(chapterContent).where(chapterContent.id == chapter_id)
    chapter = session.exec(statement).first()
    
    if not chapter:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลวิดีโอ (Chapter not found)")
        
    yt_statement = select(ytVideo).where(ytVideo.chaptercontentId == chapter_id)
    yt_stat = session.exec(yt_statement).first()

    raw_url = ""
    if yt_stat and yt_stat.videoUrl:
        raw_url = yt_stat.videoUrl
    elif chapter.vdoPath:
        raw_url = chapter.vdoPath

    if refresh and yt_stat and raw_url:
        video_id = ""
        if "watch?v=" in raw_url:
            video_id = raw_url.split("watch?v=")[1].split("&")[0]
        elif "youtu.be/" in raw_url:
            video_id = raw_url.split("youtu.be/")[1].split("?")[0]
            
        if video_id:
            try:
                youtube = get_youtube_client()
                response = youtube.videos().list(
                    part="statistics",
                    id=video_id
                ).execute()
                
                if response["items"]:
                    stats = response["items"][0]["statistics"]
                    yt_stat.viewCount = int(stats.get("viewCount", 0))
                    yt_stat.likeCount = int(stats.get("likeCount", 0))
                    session.add(yt_stat)
                    session.commit()
                    session.refresh(yt_stat)
            except Exception as e:
                print(f"Error fetching YouTube stats: {e}")
    
    view_count = yt_stat.viewCount if yt_stat else 0
    like_count = yt_stat.likeCount if yt_stat else 0
        
    embed_url = raw_url
    if raw_url:
        if "watch?v=" in raw_url:
            video_id = raw_url.split("watch?v=")[1].split("&")[0]
            embed_url = f"https://www.youtube.com/embed/{video_id}"
        elif "youtu.be/" in raw_url:
            video_id = raw_url.split("youtu.be/")[1].split("?")[0]
            embed_url = f"https://www.youtube.com/embed/{video_id}"
            
    return {
        "chapterTitle": chapter.chapterTitle,
        "episodeNumber": chapter.episodeNumber,
        "embed_url": embed_url,
        "view_count": view_count,
        "like_count": like_count
    }
    
@router.get("/{chapter_id}")
def get_yt_video_by_chapter_id(
    chapter_id: int, 
    session: Session = Depends(get_session)
):
    statement = select(ytVideo).where(ytVideo.chaptercontentId == chapter_id)
    yt_data = session.exec(statement).first()

    if not yt_data:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูล ytVideo สำหรับ Chapter นี้")

    return yt_data