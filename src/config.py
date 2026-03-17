"""
Configuration management for the Knowledge Graph API
"""
from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path
import os

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # API Settings
    app_name: str = "Knowledge Graph API"
    app_version: str = "2.0.0"
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False  # Override via DEBUG=true in .env for development

    # External Data Source
    external_api_url: str = "https://api.example.com/standards"
    external_api_key: Optional[str] = None

    # LLM Configuration
    llm_provider: str = "gemini"  # "openai" or "gemini"
    openai_api_key: Optional[str] = ""  # Local model doesn't need key
    openai_api_base: str = ""  # Any LLM server
    openai_model: Optional[str] = ""  # Any Local or API model
    openai_temperature: float = 0.2
    openai_max_tokens: int = 4096

    # Google Gemini Configuration
    gemini_api_key: Optional[str] = None  # Set via GEMINI_API_KEY in .env
    gemini_model: str = "gemini-2.5-flash"

    # Database
    database_url: str = "sqlite+aiosqlite:///./knowledge_graph.db"
    graph_storage_path: str = "./graph_data"
    vector_db_path: str = "./chroma_db"

    # Storage Paths
    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    upload_dir: str = "./uploads"
    output_dir: str = "./output"
    temp_dir: str = "./temp"
    data_dir: str = "./data"
    input_json_dir: str = "./data/output_json_chunk"
    input_images_dir: str = "./data/output_images"

    def get_abs_path(self, relative_path: str) -> str:
        """Get absolute path relative to project root"""
        path = Path(relative_path)
        if path.is_absolute():
            return str(path)
        return str(self.project_root / path)

    @property
    def abs_data_dir(self) -> Path:
        return self.project_root / self.data_dir.lstrip("./")

    @property
    def abs_output_dir(self) -> Path:
        return self.project_root / self.output_dir.lstrip("./")

    # Logging
    log_level: str = "INFO"
    log_file: str = "./logs/app.log"

    # Embedding Model
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dimension: int = 384

    # Processing
    batch_size: int = 32
    max_workers: int = 4

    # API Rate Limiting
    rate_limit_per_minute: int = 100

    # Reranking Configuration
    enable_reranking: bool = True
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    initial_retrieval_k: int = 50
    enable_semantic_search: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"

# Global settings instance
settings = Settings()

# Create necessary directories
def create_directories():
    """Create required directories if they don't exist"""
    dirs = [
        settings.upload_dir,
        settings.output_dir,
        settings.temp_dir,
        settings.data_dir,
        settings.graph_storage_path,
        settings.vector_db_path,
        os.path.dirname(settings.log_file)
    ]

    for dir_path in dirs:
        os.makedirs(dir_path, exist_ok=True)

# Initialize on import
create_directories()
