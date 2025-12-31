#!/bin/bash

# Skrypt uruchamiający serwer API w trybie deweloperskim
# Domyślny port to 8000 (można zmienić przez _APP_PORT w .env)

# Sprawdź czy venv jest aktywowane
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "❌ Virtual environment nie jest aktywowane!"
    echo "Uruchom: source venv/bin/activate"
    exit 1
fi

# Zabij procesy słuchające na porcie 8000
echo "🔍 Sprawdzam port 8000..."
PID=$(lsof -ti:8000 2>/dev/null)

if [[ -n "$PID" ]]; then
    echo "⚠️  Znaleziono proces na porcie 8000 (PID: $PID)"
    echo "🔪 Zabijam stary proces..."
    kill -9 $PID 2>/dev/null
    sleep 1
    echo "✅ Proces zakończony"
else
    echo "✅ Port 8000 jest wolny"
fi

echo ""
echo "✅ Virtual environment: $VIRTUAL_ENV"
echo "🚀 Uruchamiam serwer w trybie deweloperskim (z hot-reload)..."
echo "📡 API będzie dostępne pod: http://0.0.0.0:${_APP_PORT:-8000}"
echo "📚 Dokumentacja Swagger: http://localhost:${_APP_PORT:-8000}/docs"
echo ""
echo "Naciśnij Ctrl+C aby zatrzymać"
echo "----------------------------------------"

# Uruchom serwer z reload (tryb dev)
# PYTHONDONTWRITEBYTECODE=1 prevents .pyc and __pycache__ generation
PYTHONDONTWRITEBYTECODE=1 uvicorn app.main:app --host 0.0.0.0 --port ${_APP_PORT:-8000} --reload
