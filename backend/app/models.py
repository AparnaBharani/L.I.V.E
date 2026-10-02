from sqlalchemy import Column, Integer, String
from app.database import Base

class Experience(Base):
    __tablename__ = "experiences"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    category = Column(String, nullable=False)
    difficulty = Column(String, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    cost = Column(Integer, nullable=False, default=0)
