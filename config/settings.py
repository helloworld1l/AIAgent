import os
from typing import Any, Dict, Type

try:
    from pydantic_settings import BaseSettings
except ImportError:  # 兼容未安装 pydantic-settings 的环境
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
    "API_HOST": "0.0.0.0",
    "API_PORT": 8000,
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
        
        # API配置
        API_HOST: str = DEFAULTS["API_HOST"]
        API_PORT: int = DEFAULTS["API_PORT"]

        # 数据库配置
        DATABASE_URL: str = DEFAULTS["DATABASE_URL"]
        
        class Config:
            env_file = ".env"

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
