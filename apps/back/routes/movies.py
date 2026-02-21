from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, col, or_, cast, String, and_
from typing import List
from database import get_session 
from models import movieTitle, chapterContent, chunkContent
from pydantic import BaseModel

router = APIRouter(
    prefix="/movies",
    tags=["movies"]
)

class ChapterUpdate(BaseModel):
    chapterTitle: str
    chapterDetail: str
    
@router.get("/", response_model=List[movieTitle])
def get_movies(session: Session = Depends(get_session)):
    movies = session.exec(select(movieTitle)).all()
    return movies

# หน้า chapter
@router.get("/{movie_id}", response_model=movieTitle)
def get_movie(movie_id: int, session: Session = Depends(get_session)):
    movie = session.get(movieTitle, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie

# search ของ chapters
@router.get("/chapters/searchChapters/{search}/{movieId}", response_model=List[chapterContent])
def searchChapters(search: str, movieId: int, session: Session = Depends(get_session)):
    statement = select(chapterContent).where(
        and_(
            col(chapterContent.movieId) == movieId,
            or_(
                col(chapterContent.chapterTitle).contains(search),
                cast(chapterContent.episodeNumber, String).contains(search)
            )
        )
    ).order_by(chapterContent.episodeNumber)
    return session.exec(statement).all()

# search ของ archive
@router.get("/chapters/searchArchive/{search}", response_model=List[movieTitle])
def searchArchive(search: str, session: Session = Depends(get_session)):
    statement = select(movieTitle).where(
        col(movieTitle.movieTitle).contains(search),
    )
    return session.exec(statement).all()

# หน้า chapter
@router.get("/{movie_id}/chapters", response_model=List[chapterContent])
def get_movie_chapters(movie_id: int, session: Session = Depends(get_session)):
    return session.exec(select(chapterContent).where(chapterContent.movieId == movie_id).order_by(chapterContent.episodeNumber)).all()#แก้ให้เอาแค่เกือบครบ

# ลบ movie
@router.delete("/{movie_id}")
def delete_movie(movie_id: int, session: Session = Depends(get_session)):
    movie = session.get(movieTitle, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    
    chapters = session.exec(select(chapterContent).where(chapterContent.movieId == movie_id)).all()
    for chapter in chapters:
        session.delete(chapter)
    session.delete(movie)
    session.commit()
    return {"ok": True}

@router.put("/chapters/{chapter_id}")
def update_chapter(chapter_id: int, chapter_data: ChapterUpdate, session: Session = Depends(get_session)):
    chapter = session.get(chapterContent, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    chapter.chapterTitle = chapter_data.chapterTitle
    chapter.chapterDetail = chapter_data.chapterDetail
    session.add(chapter)
    session.commit()
    session.refresh(chapter)
    return chapter

# ข้อมูลทีละ chapter
@router.get("/chapters/{chapter_id}", response_model=chapterContent)
def get_chapter(chapter_id: int, session: Session = Depends(get_session)):
    chapter = session.get(chapterContent, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter

# get chunksContent.chunkDetail
@router.get("/chapters/{chapter_id}/chunks-summary")
def get_chunks_summary(chapter_id: int, session: Session = Depends(get_session)):
    chapter = session.get(chapterContent, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    statement = select(chunkContent).where(chunkContent.chapterId == chapter_id).order_by(chunkContent.chunkNumber)
    chunks = session.exec(statement).all()
    result = {str(chunk.chunkNumber): chunk.chunkDetail for chunk in chunks}
    return result

@router.get("/chunk/{chapter_id}")
def getChunk(chapter_id: int, session: Session = Depends(get_session)):
    chapter = session.get(chapterContent, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
        
    statement = select(chunkContent).where(chunkContent.chapterId == chapter_id).order_by(chunkContent.chunkNumber)
    chunks = session.exec(statement).all()
    result = {}
    for chunk in chunks:
        result[str(chunk.chunkNumber)] = {
            "text": chunk.chunkDetail,
            "picRef": chunk.picRef
        }
    return result

@router.get("/pic/allMovies")
def get_all_movies_pictures(session: Session = Depends(get_session)):
    statement = (
        select(chapterContent.movieId, chunkContent.picRef)
        .join(chapterContent, chapterContent.id == chunkContent.chapterId)
        .where(chunkContent.picRef != None)
        .where(chunkContent.picRef != "") 
        .order_by(chapterContent.movieId, chunkContent.chapterId, chunkContent.chunkNumber)
    )
    results = session.exec(statement).all()
    movies_pic = {}
    for movie_id, pic_ref in results:
        m_id_str = str(movie_id)
        if m_id_str not in movies_pic:
            movies_pic[m_id_str] = pic_ref
    return movies_pic

@router.get("/pic/{movieId}")
def get_movie_pictures(movieId: int, session: Session = Depends(get_session)):
    statement = (
        select(chunkContent.chapterId, chunkContent.picRef)
        .join(chapterContent, chapterContent.id == chunkContent.chapterId)
        .where(chapterContent.movieId == movieId)
        .where(chunkContent.picRef != None)
        .where(chunkContent.picRef != "") 
        .order_by(chunkContent.chapterId, chunkContent.chunkNumber)
    )
    results = session.exec(statement).all()
    chapters_pic = {}
    movie_pic = None
    for chapter_id, pic_ref in results:
        ch_id_str = str(chapter_id) 
        if ch_id_str not in chapters_pic:
            chapters_pic[ch_id_str] = pic_ref
            if movie_pic is None:
                movie_pic = pic_ref
                
    return {
        "moviePic": movie_pic,
        "chapters": chapters_pic
    }