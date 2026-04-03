from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("DATABASE_URL")
eng = create_engine(
    url,
    pool_pre_ping= True,
    pool_size=5,
    max_overflow=10
)

SessionLocal = sessionmaker(
    autocommit = False,
    autoflush=False,
    bind=eng
)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally :
        db.close()
