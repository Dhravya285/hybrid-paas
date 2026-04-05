from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    github_client_id: str
    github_client_secret: str
    jwt_secret: str

    class Config:
        env_file = ".env"

settings = Settings()