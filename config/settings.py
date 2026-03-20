import os
from typing import Any, Dict, MutableMapping, Type

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:  # 兼容未安装 pydantic-settings 的环境
    SettingsConfigDict = None  # type: ignore
    try:
        from pydantic import BaseSettings  # type: ignore
    except ImportError:
        BaseSettings = None  # type: ignore

DEFAULTS: Dict[str, Any] = {
    "QDRANT_HOST": "localhost",
    "QDRANT_PORT": 6333,
    "QDRANT_COLLECTION": "crm_filters",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "deepseek-r1:7b",
    "OLLAMA_TIMEOUT_SEC": 180,
    "OLLAMA_NUM_PREDICT": 128,
    "EMBEDDING_MODEL": "BAAI/bge-large-zh-v1.5",
    "EMBEDDING_DEVICE": "cpu",
    "RETRIEVAL_VECTOR_BACKEND": "auto",
    "RETRIEVAL_BM25_WEIGHT": 0.55,
    "RETRIEVAL_VECTOR_WEIGHT": 0.45,
    "RETRIEVAL_RERANK_BLEND": 0.35,
    "RETRIEVAL_CANDIDATE_MULTIPLIER": 4,
    "MODEL_SPEC_REPAIR_MAX_ROUNDS": 2,
    "SESSION_STORE_BACKEND": "memory",
    "SESSION_HISTORY_SIZE": 50,
    "CHAT_HISTORY_WINDOW": 12,
    "FALLBACK_HISTORY_WINDOW": 6,
    "PLANNER_HISTORY_WINDOW": 4,
    "SESSION_TTL_SEC": 604800,
    "REDIS_HOST": "localhost",
    "REDIS_PORT": 6379,
    "REDIS_DB": 0,
    "REDIS_PASSWORD": "",
    "REDIS_KEY_PREFIX": "rag_crm_agent:session",
    "API_HOST": "0.0.0.0",
    "API_PORT": 8000,
    "LOCAL_BUILD_MCP_DRY_RUN": False,
    "DATABASE_URL": "sqlite:///crm_database.db",
}


def _cast_env_value(raw: str, expected_type: Type[Any], default: Any) -> Any:
    try:
        if expected_type is int:
            return int(raw)
        if expected_type is float:
            return float(raw)
        if expected_type is bool:
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        return raw
    except Exception:
        return default


def _read_env_file(path: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not os.path.exists(path):
        return values
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    except Exception:
        return {}
    return values


if BaseSettings is not None:
    if SettingsConfigDict is not None:
        class Settings(BaseSettings):
            model_config = SettingsConfigDict(env_file=".env", extra="ignore")

            # Qdrant配置
            QDRANT_HOST: str = DEFAULTS["QDRANT_HOST"]
            QDRANT_PORT: int = DEFAULTS["QDRANT_PORT"]
            QDRANT_COLLECTION: str = DEFAULTS["QDRANT_COLLECTION"]
            
            # Ollama配置
            OLLAMA_BASE_URL: str = DEFAULTS["OLLAMA_BASE_URL"]
            OLLAMA_MODEL: str = DEFAULTS["OLLAMA_MODEL"]
            OLLAMA_TIMEOUT_SEC: int = DEFAULTS["OLLAMA_TIMEOUT_SEC"]
            OLLAMA_NUM_PREDICT: int = DEFAULTS["OLLAMA_NUM_PREDICT"]
            
            # 嵌入模型配置
            EMBEDDING_MODEL: str = DEFAULTS["EMBEDDING_MODEL"]
            EMBEDDING_DEVICE: str = DEFAULTS["EMBEDDING_DEVICE"]
            RETRIEVAL_VECTOR_BACKEND: str = DEFAULTS["RETRIEVAL_VECTOR_BACKEND"]
            RETRIEVAL_BM25_WEIGHT: float = DEFAULTS["RETRIEVAL_BM25_WEIGHT"]
            RETRIEVAL_VECTOR_WEIGHT: float = DEFAULTS["RETRIEVAL_VECTOR_WEIGHT"]
            RETRIEVAL_RERANK_BLEND: float = DEFAULTS["RETRIEVAL_RERANK_BLEND"]
            RETRIEVAL_CANDIDATE_MULTIPLIER: int = DEFAULTS["RETRIEVAL_CANDIDATE_MULTIPLIER"]
            MODEL_SPEC_REPAIR_MAX_ROUNDS: int = DEFAULTS["MODEL_SPEC_REPAIR_MAX_ROUNDS"]

            # 会话缓存配置
            SESSION_STORE_BACKEND: str = DEFAULTS["SESSION_STORE_BACKEND"]
            SESSION_HISTORY_SIZE: int = DEFAULTS["SESSION_HISTORY_SIZE"]
            CHAT_HISTORY_WINDOW: int = DEFAULTS["CHAT_HISTORY_WINDOW"]
            FALLBACK_HISTORY_WINDOW: int = DEFAULTS["FALLBACK_HISTORY_WINDOW"]
            PLANNER_HISTORY_WINDOW: int = DEFAULTS["PLANNER_HISTORY_WINDOW"]
            SESSION_TTL_SEC: int = DEFAULTS["SESSION_TTL_SEC"]

            # Redis配置
            REDIS_HOST: str = DEFAULTS["REDIS_HOST"]
            REDIS_PORT: int = DEFAULTS["REDIS_PORT"]
            REDIS_DB: int = DEFAULTS["REDIS_DB"]
            REDIS_PASSWORD: str = DEFAULTS["REDIS_PASSWORD"]
            REDIS_KEY_PREFIX: str = DEFAULTS["REDIS_KEY_PREFIX"]

            # API配置
            API_HOST: str = DEFAULTS["API_HOST"]
            API_PORT: int = DEFAULTS["API_PORT"]
            LOCAL_BUILD_MCP_DRY_RUN: bool = DEFAULTS["LOCAL_BUILD_MCP_DRY_RUN"]

            # 数据库配置
            DATABASE_URL: str = DEFAULTS["DATABASE_URL"]
    else:
        class Settings(BaseSettings):
            # Qdrant配置
            QDRANT_HOST: str = DEFAULTS["QDRANT_HOST"]
            QDRANT_PORT: int = DEFAULTS["QDRANT_PORT"]
            QDRANT_COLLECTION: str = DEFAULTS["QDRANT_COLLECTION"]
            
            # Ollama配置
            OLLAMA_BASE_URL: str = DEFAULTS["OLLAMA_BASE_URL"]
            OLLAMA_MODEL: str = DEFAULTS["OLLAMA_MODEL"]
            OLLAMA_TIMEOUT_SEC: int = DEFAULTS["OLLAMA_TIMEOUT_SEC"]
            OLLAMA_NUM_PREDICT: int = DEFAULTS["OLLAMA_NUM_PREDICT"]
            
            # 嵌入模型配置
            EMBEDDING_MODEL: str = DEFAULTS["EMBEDDING_MODEL"]
            EMBEDDING_DEVICE: str = DEFAULTS["EMBEDDING_DEVICE"]
            RETRIEVAL_VECTOR_BACKEND: str = DEFAULTS["RETRIEVAL_VECTOR_BACKEND"]
            RETRIEVAL_BM25_WEIGHT: float = DEFAULTS["RETRIEVAL_BM25_WEIGHT"]
            RETRIEVAL_VECTOR_WEIGHT: float = DEFAULTS["RETRIEVAL_VECTOR_WEIGHT"]
            RETRIEVAL_RERANK_BLEND: float = DEFAULTS["RETRIEVAL_RERANK_BLEND"]
            RETRIEVAL_CANDIDATE_MULTIPLIER: int = DEFAULTS["RETRIEVAL_CANDIDATE_MULTIPLIER"]
            MODEL_SPEC_REPAIR_MAX_ROUNDS: int = DEFAULTS["MODEL_SPEC_REPAIR_MAX_ROUNDS"]

            # 会话缓存配置
            SESSION_STORE_BACKEND: str = DEFAULTS["SESSION_STORE_BACKEND"]
            SESSION_HISTORY_SIZE: int = DEFAULTS["SESSION_HISTORY_SIZE"]
            CHAT_HISTORY_WINDOW: int = DEFAULTS["CHAT_HISTORY_WINDOW"]
            FALLBACK_HISTORY_WINDOW: int = DEFAULTS["FALLBACK_HISTORY_WINDOW"]
            PLANNER_HISTORY_WINDOW: int = DEFAULTS["PLANNER_HISTORY_WINDOW"]
            SESSION_TTL_SEC: int = DEFAULTS["SESSION_TTL_SEC"]

            # Redis配置
            REDIS_HOST: str = DEFAULTS["REDIS_HOST"]
            REDIS_PORT: int = DEFAULTS["REDIS_PORT"]
            REDIS_DB: int = DEFAULTS["REDIS_DB"]
            REDIS_PASSWORD: str = DEFAULTS["REDIS_PASSWORD"]
            REDIS_KEY_PREFIX: str = DEFAULTS["REDIS_KEY_PREFIX"]

            # API配置
            API_HOST: str = DEFAULTS["API_HOST"]
            API_PORT: int = DEFAULTS["API_PORT"]
            LOCAL_BUILD_MCP_DRY_RUN: bool = DEFAULTS["LOCAL_BUILD_MCP_DRY_RUN"]

            # 数据库配置
            DATABASE_URL: str = DEFAULTS["DATABASE_URL"]
            
            class Config:
                env_file = ".env"
                extra = "ignore"

    settings = Settings()
else:
    class FallbackSettings:
        """无 pydantic 时的轻量配置加载器。"""

        def __init__(self):
            file_env = _read_env_file(".env")
            for key, default in DEFAULTS.items():
                raw = os.getenv(key)
                if raw is None:
                    raw = file_env.get(key)
                if raw is None:
                    value = default
                else:
                    value = _cast_env_value(raw, type(default), default)
                setattr(self, key, value)

    settings = FallbackSettings()


def ensure_runtime_env_defaults(
    env: MutableMapping[str, str] | None = None,
    dry_run: bool | None = None,
) -> None:
    runtime_env = os.environ if env is None else env
    configured = runtime_env.get("LOCAL_BUILD_MCP_DRY_RUN")
    if configured is None or not str(configured).strip():
        resolved_dry_run = bool(getattr(settings, "LOCAL_BUILD_MCP_DRY_RUN", False)) if dry_run is None else bool(dry_run)
        runtime_env["LOCAL_BUILD_MCP_DRY_RUN"] = "1" if resolved_dry_run else "0"
