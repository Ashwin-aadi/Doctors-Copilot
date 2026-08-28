from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    # Resolved absolutely, not as the bare relative ".env" this used to be.
    # `make api` runs `cd backend && uvicorn ...`, so a cwd-relative path looked
    # for `backend/.env`, which does not exist -- the repo-root `.env` next to
    # `.env.example` was never loaded, and every setting silently fell back to
    # its default. GROQ_API_KEY read as empty even when set, which sent every
    # LLM call down the extractive-fallback path.
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", _REPO_ROOT / "backend" / ".env"),
        extra="ignore",
    )

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

    # Deployment locale. The product targets Indian primary and secondary care:
    # fees are rupees, times are IST, and emergency copy must cite 112/108.
    country_code: str = "IN"
    default_timezone: str = "Asia/Kolkata"
    currency: str = "INR"
    emergency_number: str = "112"
    ambulance_number: str = "108"

    # India-first clinical sources, consulted ahead of international ones.
    who_base: str = "https://www.who.int"
    mohfw_base: str = "https://www.mohfw.gov.in"
    icmr_base: str = "https://www.icmr.gov.in"
    ncdc_base: str = "https://ncdc.mohfw.gov.in"
    ncvbdc_base: str = "https://ncvbdc.mohfw.gov.in"
    ntep_base: str = "https://tbcindia.mohfw.gov.in"
    cdsco_base: str = "https://cdsco.gov.in"
    janaushadhi_base: str = "https://janaushadhi.gov.in"
    abdm_base: str = "https://abdm.gov.in"
    nlem_version: str = "2022"

    # International pharmacology backbone. Interaction chemistry is universal;
    # treatment protocol and drug availability are not, so these support an
    # Indian recommendation rather than replacing it.
    openfda_base: str = "https://api.fda.gov"
    rxnav_base: str = "https://rxnav.nlm.nih.gov/REST"
    pubmed_base: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    medlineplus_base: str = "https://medlineplus.gov"

    cors_origins: str = "http://localhost:5173"
    frontend_url: str = "http://localhost:5173"
    vite_api_base: str = "http://localhost:8000"

    # P3.2 notifications: dev SMTP defaults to a local MailHog instance
    # (infra/docker-compose.yml, see docs/DECISIONS.md); undelivered mail
    # falls back to infra/mail/*.eml so nothing is silently dropped.
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from: str = "no-reply@doctorcopilot.dev"
    mail_fallback_dir: str = "./infra/mail"

    # TRAI DLT (Distributed Ledger Technology) SMS registration -- required
    # by Indian telecom regulation for any transactional/promotional SMS.
    # Placeholder ids until a real DLT registration exists; per-type ids let
    # a real gateway be a drop-in config change. With no gateway configured,
    # send_sms() writes infra/sms/*.txt instead.
    dlt_entity_id: str = "1701000000000000000"
    dlt_sender_header: str = "DRCPLT"
    sms_fallback_dir: str = "./infra/sms"

    # P3.3 PDF export
    pdf_output_dir: str = "./infra/exports"


@lru_cache
def get_settings() -> Settings:
    return Settings()
