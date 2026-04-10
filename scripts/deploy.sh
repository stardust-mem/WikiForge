#!/bin/bash
# PKM Wiki 一键部署脚本
# 用法: ./scripts/deploy.sh "commit message"

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

MSG="${1:-auto: update}"

echo "=== 1. Build frontend ==="
cd frontend && npm run build 2>&1 | grep -E "error|✓ built"
cd "$PROJECT_ROOT"

echo "=== 2. Verify backend ==="
cd backend && source .venv/bin/activate
python -c "from app.main import app; print('Backend OK')"

echo "=== 3. Git commit & push ==="
cd "$PROJECT_ROOT"
git add -A
if git diff --cached --quiet; then
  echo "No changes to commit"
else
  git commit -m "$MSG"
  git push origin main
  echo "Pushed to origin/main"
fi

echo "=== 4. Restart server ==="
lsof -ti :8001 | xargs kill -9 2>/dev/null || true
sleep 1
cd backend
nohup uvicorn app.main:app --host 0.0.0.0 --port 8001 > /tmp/pkm-backend.log 2>&1 &
sleep 2
curl -s http://localhost:8001/api/health
echo ""
echo "=== Done ==="
