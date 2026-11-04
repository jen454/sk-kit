#!/usr/bin/env bash
# 사용법: bash ~/kit/install.sh [프로젝트 경로, 기본=현재 디렉터리] [--cli]
#   기본: 파일 복사 + MCP 서버 동작 확인 + IDE의 'MCP 탭'에 붙여넣을 JSON 출력
#   --cli: MCP 탭이 없을 때만, codex mcp add로 등록
set -e
CLI=0; ARGS=()
for a in "$@"; do [ "$a" = "--cli" ] && CLI=1 || ARGS+=("$a"); done
KIT="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "${ARGS[0]:-$(pwd)}" && pwd)"
PY="$(command -v python3 || command -v python || true)"

mkdir -p "$ROOT/docs"
for f in "$KIT"/templates/*.md; do
  [ -e "$ROOT/docs/$(basename "$f")" ] || cp "$f" "$ROOT/docs/"
done
[ -e "$ROOT/AGENTS.md" ] || cp "$KIT/AGENTS.md" "$ROOT/AGENTS.md"
echo "[O] $ROOT 에 AGENTS.md, docs/ 생성"

if [ -z "$PY" ]; then
  echo "[X] python3 없음 → MCP 없이 AGENTS.md 규칙만으로 진행"; exit 0
fi
OUT="$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | WORKFLOW_ROOT="$ROOT" "$PY" "$KIT/mcp/workflow_server.py")"
case "$OUT" in *exam-workflow*) echo "[O] MCP 서버 동작 확인 ($PY)";; *) echo "[X] MCP 서버 응답 이상: $OUT"; exit 1;; esac

if [ "$CLI" = 1 ]; then
  codex mcp remove exam-workflow >/dev/null 2>&1 || true
  codex mcp add exam-workflow --env WORKFLOW_ROOT="$ROOT" -- "$PY" "$KIT/mcp/workflow_server.py"
  echo "[O] codex mcp add 완료"
else
  echo
  echo "▼ IDE 왼쪽 'MCP 탭'의 설정 JSON에 아래 항목을 추가하고 저장하세요 (기존 형식이 다르면 키 이름만 맞추기)"
  cat <<JSON
{
  "mcpServers": {
    "exam-workflow": {
      "command": "$PY",
      "args": ["$KIT/mcp/workflow_server.py"],
      "env": { "WORKFLOW_ROOT": "$ROOT" }
    }
  }
}
JSON
fi
echo
echo "다음: 터미널에서 codex 실행 → '/mcp'로 exam-workflow 확인 → 'exam-workflow의 kit_init 실행해줘'"
echo "MCP가 안 붙어도: AGENTS.md와 docs/가 이미 복사되어 있으므로 규칙만으로 진행 가능 (MCP 탭이 없으면 --cli 옵션)"
