#!/usr/bin/env bash

set -e

echo "🚀 Setting up Sprint 2..."

mkdir -p backend/app/core
mkdir -p backend/app/api

cat > backend/app/core/settings.py << 'EOF'
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Odin Core"
    VERSION: str = "0.0.1"
    ENVIRONMENT: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
EOF

touch backend/app/core/config.py
touch backend/app/core/logger.py
touch backend/app/api/health.py
touch backend/app/api/version.py

echo "✅ Sprint 2 scaffold created!"