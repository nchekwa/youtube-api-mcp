#!/bin/bash

# Skrypt uruchamiający serwer API w trybie deweloperskim
# Domyślny port to 8000 (można zmienić przez _APP_PORT w .env)

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_ENV_FILE="$SCRIPT_DIR/.env"
LOG_CONFIG_FILE="$SCRIPT_DIR/app/uvicorn_log_config.json"

# Sprawdź czy venv jest aktywowane
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "❌ Virtual environment nie jest aktywowane!"
    echo "Uruchom: source venv/bin/activate"
    exit 1
fi

if [[ -f "$PROJECT_ENV_FILE" ]]; then
    echo "📄 Ładuję zmienne środowiskowe z: $PROJECT_ENV_FILE"
    set -a
    source "$PROJECT_ENV_FILE"
    set +a
fi

APP_PORT="${_APP_PORT:-8000}"
APP_TRANSCRIPTION_BACKEND="$(printf '%s' "${_APP_TRANSCRIPTION_BACKEND:-faster-whisper}" | cut -d'#' -f1 | xargs)"
APP_TRANSCRIPT_FROM_AUDIO="$(printf '%s' "${_APP_TRANSCRIPT_FROM_AUDIO:-false}" | cut -d'#' -f1 | xargs)"

# Zabij procesy słuchające na wybranym porcie
echo "🔍 Sprawdzam port $APP_PORT..."
PID=$(lsof -ti:$APP_PORT 2>/dev/null)

if [[ -n "$PID" ]]; then
    echo "⚠️  Znaleziono proces na porcie $APP_PORT (PID: $PID)"
    echo "🔪 Zabijam stary proces..."
    kill -9 $PID 2>/dev/null
    sleep 1
    echo "✅ Proces zakończony"
else
    echo "✅ Port $APP_PORT jest wolny"
fi

echo ""
echo "✅ Virtual environment: $VIRTUAL_ENV"
echo "🚀 Uruchamiam serwer w trybie deweloperskim (z hot-reload)..."
echo "📡 API będzie dostępne pod: http://0.0.0.0:$APP_PORT"
echo "🪵 Log level: ${_APP_LOG_LEVEL:-INFO}"
echo "🧠 Transcription backend: ${APP_TRANSCRIPTION_BACKEND:-faster-whisper}"
echo "↩️ Transcript from audio: ${APP_TRANSCRIPT_FROM_AUDIO:-false}"
echo "🕒 Timestamp log config: $LOG_CONFIG_FILE"
echo "📚 Dokumentacja Swagger: http://localhost:$APP_PORT/docs"
echo ""
echo "Naciśnij Ctrl+C aby zatrzymać"
echo "----------------------------------------"

# Uruchom serwer z reload (tryb dev)
# PYTHONDONTWRITEBYTECODE=1 prevents .pyc and __pycache__ generation
PYTHONDONTWRITEBYTECODE=1 uvicorn app.main:app --host 0.0.0.0 --port $APP_PORT --reload --log-config "$LOG_CONFIG_FILE"
