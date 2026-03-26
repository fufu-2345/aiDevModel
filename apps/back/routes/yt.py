from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

router = APIRouter(
    prefix="/yt",
    tags=["yt"]
)

def get_session():
    pass

def get_youtube_client():
    pass

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
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path)
            ).execute()
            print("อัปโหลด Thumbnail สำเร็จ!")

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