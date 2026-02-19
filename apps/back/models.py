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
    characters: List["character"] = Relationship(back_populates="movie")
    entities: List["entity"] = Relationship(back_populates="movie")

class chapterContent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    episodeNumber: float 
    chapterTitle: str                     
    chapterDetail: str = Field(default="")   
    chapterDetailEng: str = Field(default="")   
    picPath: str = Field(default="")      
    vdoPath: str = Field(default="")               
    movieId: Optional[int] = Field(default=None, foreign_key="movietitle.id")
    isExtracted: bool = Field(default=False)
    
    movie: Optional[movieTitle] = Relationship(back_populates="chapters")
    chunks: List["chunkContent"] = Relationship(back_populates="chapter")

class chunkContent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    chunkNumber: int 
    chunkDetail: str = Field(default="")      # Chunk thai (ไม่มี overlap)
    chunkDetailEng: str = Field(default="")   # Chunk eng (มี overlap)
    analyzed: str = Field(default="") 
    picRef: str = Field(default="")
    chapterId: Optional[int] = Field(default=None, foreign_key="chaptercontent.id")
    
    chapter: Optional[chapterContent] = Relationship(back_populates="chunks")

class entity(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    type: str 
    name: str
    visual_tags: str = Field(default="")
    movieId: Optional[int] = Field(default=None, foreign_key="movietitle.id")
    refpath: str = Field(default="")
    
    movie: Optional[movieTitle] = Relationship(back_populates="entities")
    altNames: List["altEntity"] = Relationship(back_populates="entity")

class altEntity(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    altName: str = Field(sa_column=Column("altName", Text))
    entityId: Optional[int] = Field(default=None, foreign_key="entity.id")
    
    entity: Optional["entity"] = Relationship(back_populates="altNames")

class character(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    type: str = Field(default="Character")
    name: str
    IdentityTags: str = Field(default="")
    ModifierTags: str = Field(default="")
    movieId: Optional[int] = Field(default=None, foreign_key="movietitle.id")
    refpath: str = Field(default="")
    
    movie: Optional[movieTitle] = Relationship(back_populates="characters")
    altNames: List["altCharacter"] = Relationship(back_populates="character")

class altCharacter(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    altName: str = Field(sa_column=Column("altName", Text))
    entityId: Optional[int] = Field(default=None, foreign_key="character.id")
    
    character: Optional["character"] = Relationship(back_populates="altNames")
    
class user(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    role: str = Field(default="user")
    emailL: str
    password: str 
    
class matcher(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    character: str
    location: str
    duration: str
    chapterId: Optional[int] = Field(default=None, foreign_key="chaptercontent.id")