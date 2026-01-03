from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, Text

class movieTitle(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    movieTitle: str                 
    episodeAmount: int = Field(default=0)                    
    picPath: str = Field(default="")
    status: str = Field(default="ready")
    chapters: List["chapterContent"] = Relationship(back_populates="movie")
    chunks: List["ChunkContent"] = Relationship(back_populates="movie")
    entities: List["EntityContent"] = Relationship(back_populates="movie")

class chapterContent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    episodeNumber: float 
    chapterTitle: str                     
    chapterDetail: str = Field(default="")   
    chapterDetailEng: str = Field(default="")   
    picPath: str = Field(default="")      
    vdoPath: str = Field(default="")               
    movieId: Optional[int] = Field(default=None, foreign_key="movietitle.id")
    is_processed: bool = Field(default=False)
    movie: Optional[movieTitle] = Relationship(back_populates="chapters")
    chunks: List["ChunkContent"] = Relationship(back_populates="chapter")


class ChunkContent(SQLModel, table=True):
    __tablename__ = "chunks"
    id: Optional[int] = Field(default=None, primary_key=True)
    chunk_text: str = Field(sa_column=Column(Text))
    chunk_index: int
    chapter_id: Optional[int] = Field(default=None, foreign_key="chaptercontent.id")
    movie_id: Optional[int] = Field(default=None, foreign_key="movietitle.id")
    chapter: Optional[chapterContent] = Relationship(back_populates="chunks")
    movie: Optional[movieTitle] = Relationship(back_populates="chunks")

class EntityContent(SQLModel, table=True):
    __tablename__ = "entities" 
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    category: str
    description: str = Field(default="", sa_column=Column(Text))
    visual_tags: str = Field(default="", sa_column=Column(Text)) 
    movie_id: Optional[int] = Field(default=None, foreign_key="movietitle.id")
    chapter_found_id: Optional[int] = Field(default=None)
    movie: Optional[movieTitle] = Relationship(back_populates="entities")