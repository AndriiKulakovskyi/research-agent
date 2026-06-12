#!/usr/bin/env bash
# Deep Harness API from the shell. Requires: deep-harness-server running, curl, jq.
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
USERNAME="demo_$RANDOM"

echo "# 1. Register (use /api/auth/login for an existing account)"
TOKEN=$(curl -sf "$BASE_URL/api/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"username\": \"$USERNAME\", \"password\": \"demo-password-1\"}" | jq -r .token)
AUTH="Authorization: Bearer $TOKEN"

echo "# 2. Create a thread"
THREAD_ID=$(curl -sf "$BASE_URL/api/threads" -X POST -H "$AUTH" \
  -H 'Content-Type: application/json' -d '{}' | jq -r .id)
echo "thread: $THREAD_ID"

echo "# 3. Send a task — the agent run streams back as SSE"
curl -sN "$BASE_URL/api/threads/$THREAD_ID/messages" -H "$AUTH" \
  -H 'Content-Type: application/json' \
  -d '{"content": "List the tables in the database and summarize what each holds."}'

echo "# 4. Persisted history, plan, and workspace artifacts"
curl -sf "$BASE_URL/api/threads/$THREAD_ID/messages" -H "$AUTH" | jq '.[].role'
curl -sf "$BASE_URL/api/threads/$THREAD_ID/todos" -H "$AUTH" | jq
curl -sf "$BASE_URL/api/files" -H "$AUTH" | jq

echo "# 5. Clean up"
curl -sf -X DELETE "$BASE_URL/api/threads/$THREAD_ID" -H "$AUTH"
curl -sf -X POST "$BASE_URL/api/auth/logout" -H "$AUTH"
echo "done."
