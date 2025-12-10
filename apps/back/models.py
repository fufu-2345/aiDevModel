from typing import Optional
from sqlmodel import Field, SQLModel

class movieTitle(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    movieTitle: str                 
    episodeAmount: int                     
    picPath: str = Field(default="")
    
class chapterContent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    episodeNumber: float 
    chapterTitle: str                     
    chapterDetail: str    
    picPath: str = Field(default="")      
    vdoPath: str = Field(default="")               
    movieId: Optional[int] = Field(default=None, foreign_key="movietitle.id")