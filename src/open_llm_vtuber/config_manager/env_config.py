"""
Environment configuration module.

Centralizes all environment variable access with sensible defaults.
Load values from .env file or system environment variables.
"""

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()


def get_env(key: str, default: str = "") -> str:
    """Get environment variable with default fallback."""
    return os.getenv(key, default)


def get_env_int(key: str, default: int = 0) -> int:
    """Get environment variable as integer with default fallback."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def get_env_bool(key: str, default: bool = False) -> bool:
    """Get environment variable as boolean with default fallback."""
    value = os.getenv(key)
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on")


@dataclass
class ServerConfig:
    """Server configuration."""

    host: str = field(default_factory=lambda: get_env("VTUBER_HOST", "localhost"))
    port: int = field(default_factory=lambda: get_env_int("VTUBER_PORT", 12393))

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


@dataclass
class ProxyConfig:
    """Proxy WebSocket configuration."""

    enabled: bool = field(default_factory=lambda: get_env_bool("PROXY_ENABLED", False))
    host: str = field(default_factory=lambda: get_env("PROXY_HOST", "localhost"))
    port: int = field(default_factory=lambda: get_env_int("PROXY_PORT", 12393))

    @property
    def ws_url(self) -> str:
        return get_env("PROXY_WS_URL", f"ws://{self.host}:{self.port}/client-ws")

    @property
    def proxy_ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}/proxy-ws"


@dataclass
class LLMConfig:
    """LLM service URLs configuration."""

    ollama_base_url: str = field(
        default_factory=lambda: get_env(
            "LLM_OLLAMA_BASE_URL", "http://localhost:11434/v1"
        )
    )
    lmstudio_base_url: str = field(
        default_factory=lambda: get_env(
            "LLM_LMSTUDIO_BASE_URL", "http://localhost:1234/v1"
        )
    )
    openai_base_url: str = field(
        default_factory=lambda: get_env(
            "LLM_OPENAI_BASE_URL", "https://api.openai.com/v1"
        )
    )
    gemini_base_url: str = field(
        default_factory=lambda: get_env(
            "LLM_GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        )
    )
    mistral_base_url: str = field(
        default_factory=lambda: get_env(
            "LLM_MISTRAL_BASE_URL", "https://api.mistral.ai/v1"
        )
    )
    deepseek_base_url: str = field(
        default_factory=lambda: get_env(
            "LLM_DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
        )
    )
    groq_base_url: str = field(
        default_factory=lambda: get_env(
            "LLM_GROQ_BASE_URL", "https://api.groq.com/openai/v1"
        )
    )
    anthropic_base_url: str = field(
        default_factory=lambda: get_env(
            "LLM_ANTHROPIC_BASE_URL", "https://api.anthropic.com"
        )
    )
    zhipu_base_url: str = field(
        default_factory=lambda: get_env(
            "LLM_ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/"
        )
    )


@dataclass
class TTSConfig:
    """TTS service URLs configuration."""

    cosyvoice_url: str = field(
        default_factory=lambda: get_env("TTS_COSYVOICE_URL", "http://127.0.0.1:50000/")
    )
    gpt_sovits_url: str = field(
        default_factory=lambda: get_env(
            "TTS_GPT_SOVITS_URL", "http://127.0.0.1:9880/tts"
        )
    )
    x_tts_url: str = field(
        default_factory=lambda: get_env(
            "TTS_X_TTS_URL", "http://127.0.0.1:8020/tts_to_audio"
        )
    )
    openai_compatible_url: str = field(
        default_factory=lambda: get_env(
            "TTS_OPENAI_COMPATIBLE_URL", "http://localhost:8880/v1"
        )
    )
    spark_url: str = field(
        default_factory=lambda: get_env("TTS_SPARK_URL", "http://127.0.0.1:7860/")
    )
    melo_url: str = field(
        default_factory=lambda: get_env("TTS_MELO_URL", "http://localhost:8051")
    )
    fish_audio_url: str = field(
        default_factory=lambda: get_env("TTS_FISH_AUDIO_URL", "https://api.fish.audio")
    )
    minimax_url: str = field(
        default_factory=lambda: get_env(
            "TTS_MINIMAX_URL", "https://api.minimax.chat/v1/t2a_v2"
        )
    )
    siliconflow_url: str = field(
        default_factory=lambda: get_env(
            "TTS_SILICONFLOW_URL", "https://api.siliconflow.cn/v1/audio/speech"
        )
    )


@dataclass
class ASRConfig:
    """ASR service URLs configuration."""

    whisper_url: str = field(
        default_factory=lambda: get_env("ASR_WHISPER_URL", "http://localhost:8000")
    )
    groq_url: str = field(
        default_factory=lambda: get_env(
            "ASR_GROQ_URL", "https://api.groq.com/openai/v1"
        )
    )


@dataclass
class TranslateConfig:
    """Translation service configuration."""

    deeplx_url: str = field(
        default_factory=lambda: get_env(
            "TRANSLATE_DEEPLX_URL", "http://127.0.0.1:1188/v2/translate"
        )
    )


@dataclass
class AgentConfig:
    """Agent service configuration."""

    letta_host: str = field(
        default_factory=lambda: get_env("AGENT_LETTA_HOST", "localhost")
    )
    letta_port: int = field(
        default_factory=lambda: get_env_int("AGENT_LETTA_PORT", 8283)
    )

    @property
    def letta_base_url(self) -> str:
        return f"http://{self.letta_host}:{self.letta_port}"


@dataclass
class VADConfig:
    """VAD service configuration."""

    host: str = field(
        default_factory=lambda: get_env("VAD_WEBSOCKET_HOST", "localhost")
    )
    port: int = field(default_factory=lambda: get_env_int("VAD_WEBSOCKET_PORT", 8765))


@dataclass
class OAuthConfig:
    """OAuth configuration."""

    chzzk_redirect_url: str = field(
        default_factory=lambda: get_env(
            "CHZZK_OAUTH_REDIRECT_URL", "http://localhost:12393/chzzk/callback"
        )
    )


@dataclass
class PathConfig:
    """Directory paths configuration."""

    models_dir: str = field(default_factory=lambda: get_env("MODELS_DIR", "./models"))
    cache_dir: str = field(default_factory=lambda: get_env("CACHE_DIR", "./cache"))
    logs_dir: str = field(default_factory=lambda: get_env("LOGS_DIR", "./logs"))
    live2d_models_dir: str = field(
        default_factory=lambda: get_env("LIVE2D_MODELS_DIR", "./live2d-models")
    )
    backgrounds_dir: str = field(
        default_factory=lambda: get_env("BACKGROUNDS_DIR", "./backgrounds")
    )


@dataclass
class EnvConfig:
    """Main environment configuration container."""

    server: ServerConfig = field(default_factory=ServerConfig)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    asr: ASRConfig = field(default_factory=ASRConfig)
    translate: TranslateConfig = field(default_factory=TranslateConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    oauth: OAuthConfig = field(default_factory=OAuthConfig)
    paths: PathConfig = field(default_factory=PathConfig)


# Global configuration instance
_config: Optional[EnvConfig] = None


def get_config() -> EnvConfig:
    """Get the global configuration instance (singleton)."""
    global _config
    if _config is None:
        _config = EnvConfig()
    return _config


def reload_config() -> EnvConfig:
    """Reload configuration from environment variables."""
    global _config
    load_dotenv(override=True)
    _config = EnvConfig()
    return _config
