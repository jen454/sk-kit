# SK hynix hackathon 2차 예선 준비 자료

특정 문제용이 아니라 **어떤 주제가 나와도 같은 순서로 일하게 만드는** 키트입니다. 서비스 코드는 들어 있지 않습니다.

## 구성
- `AGENTS.md`: Codex가 자동으로 읽는 작업 규칙 (단계 순서, 계층 구조, 에러 처리, 기록 규칙)
- `templates/`: 요구사항, 데이터, 아키텍처, 판단, 검증, AI 활용 문서 양식
- `mcp/workflow_server.py`: 단계 관문과 기록을 담당하는 MCP 서버 (Python 3 표준 라이브러리만 사용, 설치 불필요)

## 시험장 설치
응시 가이드 기준: **공개 GitHub 저장소의 git clone은 허용**, 개인 PC 파일 업로드는 불가, MCP는 IDE의 **MCP 탭 JSON**으로 설정.

1. 프로젝트 폴더의 터미널에서:
   ```bash
   git clone https://github.com/jen454/sk-kit ~/kit && bash ~/kit/install.sh
   ```
   - 키트는 프로젝트 **밖**(`~/kit`)에 받아서 제출물에 섞이지 않게 합니다.
   - `AGENTS.md`와 `docs/` 템플릿을 복사하고, MCP 서버가 동작하는지 확인합니다.
2. 출력된 JSON을 IDE 왼쪽 **MCP 탭**의 설정에 추가하고 저장합니다.
3. `codex` 실행 → `/mcp`로 연결 확인 → "exam-workflow의 kit_init 실행해줘"
- MCP 탭이 없을 때만: `bash ~/kit/install.sh --cli` (`codex mcp add`로 등록)
- MCP가 끝내 안 붙으면 `AGENTS.md` 규칙만으로 진행합니다.

## 도구
| 도구 | 언제 |
|---|---|
| `kit_init` | 시작 직후 1회 |
| `phase_status` | 매 요청 시작 시 (AGENTS.md가 시킴) |
| `phase_advance` | 단계를 마칠 때. 조건 미충족이면 막고, 통과하면 설명 질문을 냄 |
| `log_decision` | 배정 기준 등 중요한 판단을 했을 때 |
| `log_ai_usage` | AI에게 맡긴 작업 하나를 끝냈을 때 |
| `coverage_report` | 구현·검증 중간 점검 |
| `structure_summary` | 마무리. 실제 코드 기준으로 ARCHITECTURE.md에 '실제 구현 요약' 작성 → 사용자가 읽고 제출 |
| `fill_forms` | 주최측 제출 양식을 작업 기록으로 채움 |
