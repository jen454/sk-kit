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
if [ -e "$ROOT/AGENTS.md" ] && ! grep -q "exam-workflow" "$ROOT/AGENTS.md"; then
  # 과제에 이미 AGENTS.md가 있으면 건드리지 않고, 키트 규칙은 별도 파일로 둔다
  cp "$KIT/AGENTS.md" "$ROOT/docs/KIT_RULES.md"
  echo "[!] 과제에 원래 있던 AGENTS.md는 그대로 둠. 키트 규칙은 docs/KIT_RULES.md에 복사"
  echo "    → Codex 첫 요청: 'AGENTS.md와 docs/KIT_RULES.md를 읽고 둘 다 따라줘. 충돌하면 AGENTS.md(과제 쪽)가 우선이야.'"
else
  [ -e "$ROOT/AGENTS.md" ] || cp "$KIT/AGENTS.md" "$ROOT/AGENTS.md"
  echo "[O] AGENTS.md 생성 (Codex는 이 폴더에서 실행해야 자동으로 읽음. 이미 켜져 있었다면 다시 실행)"
fi
echo "[O] $ROOT/docs/ 양식 생성"

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
echo "다음: 이 폴더에서 codex 실행 → 바로 작업 시작 (예: '요구사항 분석해줘. 아직 코드는 쓰지 마.')"
echo "MCP가 안 붙어도: AGENTS.md와 docs/가 이미 복사되어 있으므로 규칙만으로 진행 가능 (MCP 탭이 없으면 --cli 옵션)"
