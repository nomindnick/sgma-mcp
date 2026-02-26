"""Configuration settings loaded from environment variables and .env file."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Database
    database_path: Path = Path("data/sgma.db")

    # Embeddings
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Chunking
    chunk_token_threshold: int = 500
    chunk_overlap_tokens: int = 50

    # Search weights (must sum to 1.0)
    search_weight_keyword: float = 0.4
    search_weight_semantic: float = 0.6

    # Server
    mcp_transport: str = "stdio"
    host: str = "0.0.0.0"
    port: int = 8000

    # API keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""


settings = Settings()
