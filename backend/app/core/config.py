from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    api_port: int = 8000
    secret_key: str = "change-me-32-bytes-minimum-please"
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    postgres_user: str = "copilot"
    postgres_password: str = "copilot"
    postgres_db: str = "copilot"
    database_url: str = "postgresql+psycopg://copilot:copilot@localhost:5432/copilot"

    redis_url: str = "redis://localhost:6379/0"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "copilot123"

    chroma_path: str = "./infra/chroma"

    llm_provider: str = "groq"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    embed_model_general: str = "sentence-transformers/all-MiniLM-L6-v2"
    embed_model_clinical: str = "NeuML/pubmedbert-base-embeddings"
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    hf_home: str = "./ml/.cache"

    storage_root: str = "./infra/storage"

    captcha_ttl_seconds: int = 120
    captcha_difficulty: int = 50000

    openfda_base: str = "https://api.fda.gov"
    rxnav_base: str = "https://rxnav.nlm.nih.gov/REST"
    pubmed_base: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    medlineplus_base: str = "https://medlineplus.gov"

    cors_origins: str = "http://localhost:5173"
    frontend_url: str = "http://localhost:5173"
    vite_api_base: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
