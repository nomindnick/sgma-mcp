"""Configuration settings loaded from environment variables and .env file."""

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # Database
    database_path: Path = Path("data/sgma.db")

    # Embeddings
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Chunking
    chunk_token_threshold: int = 500
    chunk_overlap_tokens: int = 50

    # Search weights
    search_weight_keyword: float = 0.4
    search_weight_semantic: float = 0.6

    @model_validator(mode="after")
    def _check_search_weights(self):
        total = self.search_weight_keyword + self.search_weight_semantic
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Search weights must sum to 1.0, got {total}")
        return self

    # Server
    mcp_transport: str = "sse"
    host: str = "0.0.0.0"
    port: int = 8000

    # API keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""


settings = Settings()
