from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    port: int


settings = Settings()
