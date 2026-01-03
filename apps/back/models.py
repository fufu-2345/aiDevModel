from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, Text

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
    
class ChunkContent(Base):
    __tablename__ = "chunks"
    id = Column(Integer, primary_key=True, index=True)
    chunk_text = Column(Text)      
    chunk_index = Column(Integer)  
    chapter_id = Column(Integer, ForeignKey("chapters.id"))
    movie_id = Column(Integer)

class EntityContent(Base):
    __tablename__ = "entities"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)      
    category = Column(String)               # (Person, Item, Location)
    description = Column(Text)            
    visual_tags = Column(Text, default="") 
    movie_id = Column(Integer)
    chapter_found_id = Column(Integer)    

Base.metadata.create_all(bind=engine)