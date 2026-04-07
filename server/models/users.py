from sqlalchemy import Column, Integer, String, Text
from config.db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    github_id = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, nullable=False)
    email = Column(String, nullable=True)
    avatar = Column(String, nullable=True)
    github_access_token = Column(Text, nullable=False) 