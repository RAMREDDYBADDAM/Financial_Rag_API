# app/config.py
"""
Enterprise Configuration Management with Validation
==================================================
Type-safe configuration with nested settings classes and comprehensive validation.

Features:
- Pydantic validators for all critical settings
- Nested configuration classes for logical grouping
- API key sanitization for logging
- Hot-reload support
- Environment variable override
"""
import os
import re
from typing import Optional, List
from dotenv import load_dotenv
from pydantic import Field, field_validator, computed_field
from pydantic_settings import BaseSettings

load_dotenv()


class SecuritySettings(BaseSettings):
    """Security and CORS configuration."""
    
    cors_enabled: bool = Field(
        default=True,
        description="Enable CORS middleware"
    )
    
    allowed_origins: List[str] = Field(
        default=["*"],
        description="Allowed CORS origins"
    )
    
    max_request_size_mb: int = Field(
        default=10,
        description="Maximum request body size in MB",
        ge=1,
        le=100
    )
    
    rate_limit_enabled: bool = Field(
        default=False,
        description="Enable rate limiting"
    )
    
    rate_limit_requests: int = Field(
        default=100,
        description="Max requests per window",
        ge=1
    )
    
    rate_limit_window_seconds: int = Field(
        default=60,
        description="Rate limit window in seconds",
        ge=1
    )
    
    @field_validator("allowed_origins")
    @classmethod
    def validate_origins(cls, v):
        """Ensure at least one origin is configured."""
        if not v or len(v) == 0:
            raise ValueError("At least one allowed origin must be configured")
        return v
    
    model_config = {"extra": "allow", "env_prefix": "SECURITY_"}


class LLMSettings(BaseSettings):
    """LLM provider configuration."""
    
    provider: str = Field(
        default="openai",
        description="LLM provider (openai, ollama, mock)"
    )
    
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key"
    )
    
    openai_model: str = Field(
        default="gpt-4o-mini",
        description="OpenAI model name"
    )
    
    ollama_enabled: bool = Field(
        default=True,
        description="Enable Ollama as fallback"
    )
    
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama server URL"
    )
    
    ollama_model: str = Field(
        default="mistral",
        description="Ollama model name"
    )
    
    temperature: float = Field(
        default=0.1,
        description="LLM sampling temperature",
        ge=0.0,
        le=2.0
    )
    
    timeout_seconds: int = Field(
        default=60,
        description="LLM request timeout",
        ge=1,
        le=300
    )
    
    max_tokens: Optional[int] = Field(
        default=None,
        description="Maximum tokens in response",
        ge=1
    )
    
    @field_validator("ollama_base_url")
    @classmethod
    def validate_ollama_url(cls, v):
        """Validate Ollama URL format."""
        if v and not re.match(r'^https?://', v):
            raise ValueError("Ollama base URL must start with http:// or https://")
        return v
    
    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v):
        """Validate temperature range."""
        if not 0.0 <= v <= 2.0:
            raise ValueError("Temperature must be between 0.0 and 2.0")
        return v
    
    model_config = {"extra": "allow", "env_prefix": "LLM_"}


class CacheSettings(BaseSettings):
    """Cache configuration."""
    
    enabled: bool = Field(
        default=True,
        description="Enable caching"
    )
    
    ttl_seconds: int = Field(
        default=3600,
        description="Cache TTL in seconds",
        ge=1
    )
    
    max_size_mb: int = Field(
        default=100,
        description="Maximum cache size in MB",
        ge=1
    )
    
    yahoo_cache_enabled: bool = Field(
        default=True,
        description="Enable Yahoo Finance data caching"
    )
    
    model_config = {"extra": "allow", "env_prefix": "CACHE_"}


class DatabaseSettings(BaseSettings):
    """Database configuration."""
    
    url: str = Field(
        default="",
        description="Database connection URL"
    )
    
    pool_size: int = Field(
        default=5,
        description="Connection pool size",
        ge=1,
        le=50
    )
    
    echo: bool = Field(
        default=False,
        description="Echo SQL statements"
    )
    
    @field_validator("url")
    @classmethod
    def validate_database_url(cls, v):
        """Validate database URL format if provided."""
        if v and not re.match(r'^(postgresql|sqlite|mysql)://', v):
            raise ValueError(
                "Database URL must start with postgresql://, sqlite://, or mysql://"
            )
        return v
    
    model_config = {"extra": "allow", "env_prefix": "DATABASE_"}


class Settings(BaseSettings):
    """
    Main application configuration.
    
    Aggregates all nested configuration classes and provides
    utility methods for config management.
    """
    
    # Application metadata
    app_name: str = Field(
        default="Financial RAG API",
        description="Application name"
    )
    
    app_version: str = Field(
        default="2.0.0",
        description="Application version"
    )
    
    debug: bool = Field(
        default=False,
        description="Enable debug mode"
    )
    
    # Allow extra fields from .env for backwards compatibility
    model_config = {"extra": "allow"}
    
    # Nested configuration
    security: SecuritySettings = Field(
        default_factory=SecuritySettings,
        description="Security settings"
    )
    
    llm: LLMSettings = Field(
        default_factory=LLMSettings,
        description="LLM settings"
    )
    
    cache: CacheSettings = Field(
        default_factory=CacheSettings,
        description="Cache settings"
    )
    
    database: DatabaseSettings = Field(
        default_factory=DatabaseSettings,
        description="Database settings"
    )
    
    # Legacy flat config for backwards compatibility
    openai_api_key: str = Field(default="")
    ollama_enabled: bool = Field(default=True)
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="mistral")
    database_url: str = Field(default="")
    vector_db_dir: str = Field(default="./data/vectorstore")
    llm_model: str = Field(default="gpt-4o-mini")
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    top_k_docs: int = Field(default=5, ge=1)
    
    def model_post_init(self, __context):
        """Sync legacy and nested configs after initialization."""
        # Sync nested to legacy for backwards compatibility
        self.openai_api_key = self.openai_api_key or self.llm.openai_api_key
        self.ollama_enabled = self.ollama_enabled or self.llm.ollama_enabled
        self.ollama_base_url = self.ollama_base_url or self.llm.ollama_base_url
        self.ollama_model = self.ollama_model or self.llm.ollama_model
        self.database_url = self.database_url or self.database.url
        self.temperature = self.temperature or self.llm.temperature
        self.llm_model = self.llm_model or self.llm.openai_model
        
        # Sync legacy to nested
        self.llm.openai_api_key = self.llm.openai_api_key or self.openai_api_key
        self.llm.ollama_enabled = self.llm.ollama_enabled or self.ollama_enabled
        self.llm.ollama_base_url = self.llm.ollama_base_url or self.ollama_base_url
        self.llm.ollama_model = self.llm.ollama_model or self.ollama_model
        self.database.url = self.database.url or self.database_url
        self.llm.temperature = self.llm.temperature or self.temperature
        self.llm.openai_model = self.llm.openai_model or self.llm_model
    
    @computed_field
    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return not self.debug and os.getenv("ENVIRONMENT", "development") == "production"
    
    @computed_field
    @property
    def has_database(self) -> bool:
        """Check if database is configured."""
        return bool(self.database_url or self.database.url)
    
    @computed_field
    @property
    def has_openai(self) -> bool:
        """Check if OpenAI is configured."""
        return bool(self.openai_api_key or self.llm.openai_api_key)
    
    def get_sanitized_config(self) -> dict:
        """
        Get configuration dict with sensitive values masked.
        
        Returns:
            Dict with API keys and passwords masked
        """
        config = self.model_dump()
        
        # Mask sensitive fields
        if config.get("openai_api_key"):
            config["openai_api_key"] = f"{config['openai_api_key'][:8]}...MASKED"
        
        if config.get("llm", {}).get("openai_api_key"):
            config["llm"]["openai_api_key"] = f"{config['llm']['openai_api_key'][:8]}...MASKED"
        
        if config.get("database_url") and "://" in config["database_url"]:
            # Mask password in database URL
            parts = config["database_url"].split("://")
            if len(parts) == 2 and "@" in parts[1]:
                user_pass, rest = parts[1].split("@", 1)
                if ":" in user_pass:
                    user, _ = user_pass.split(":", 1)
                    config["database_url"] = f"{parts[0]}://{user}:***@{rest}"
        
        if config.get("database", {}).get("url") and "://" in config["database"]["url"]:
            parts = config["database"]["url"].split("://")
            if len(parts) == 2 and "@" in parts[1]:
                user_pass, rest = parts[1].split("@", 1)
                if ":" in user_pass:
                    user, _ = user_pass.split(":", 1)
                    config["database"]["url"] = f"{parts[0]}://{user}:***@{rest}"
        
        return config
    
    def reload(self):
        """
        Reload configuration from environment.
        
        Useful for hot-reloading config without restarting server.
        """
        load_dotenv(override=True)
        self.__init__()
    
    model_config = {
        "extra": "allow",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False
    }


# Global singleton instance
settings = Settings()
