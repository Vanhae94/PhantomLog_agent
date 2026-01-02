from sqlalchemy import Column, Integer, String, Text
from backend.database import Base

class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    job = Column(String)
    personality = Column(String)
    prompt = Column(Text)
