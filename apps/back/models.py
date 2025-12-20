from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship

class movieTitle(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    movieTitle: str                 
    episodeAmount: int = Field(default=0)                    
    picPath: str = Field(default="")
    chapters: List["chapterContent"] = Relationship(back_populates="movie")

class chapterContent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    episodeNumber: float 
    chapterTitle: str                     
    chapterDetail: str = Field(default="")   
    chapterDetailEng: str = Field(default="")   
    picPath: str = Field(default="")      
    vdoPath: str = Field(default="")               
    movieId: Optional[int] = Field(default=None, foreign_key="movietitle.id")
    movie: Optional[movieTitle] = Relationship(back_populates="chapters")