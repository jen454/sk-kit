#!/usr/bin/env python3
"""Exam workflow MCP server (stdio, Python standard library only).

Enforces a 6-phase workflow for "requirements + data -> web service" tasks
and keeps a trail of decisions and AI usage that feeds the submission docs.

Project root: tool argument `root` > env WORKFLOW_ROOT > current directory.
"""
import datetime
import json
import os
import re
import shutil
import sys

KIT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(KIT_DIR, "templates")
DOCS = "docs"
STATE_FILE = os.path.join(".workflow", "state.json")
TODO_MARK = "<!-- TODO"

PHASES = [
    {"id": 1, "name": "요구사항 분석", "file": "REQUIREMENTS.md"},
    {"id": 2, "name": "데이터 탐색", "file": "DATA_NOTES.md"},
    {"id": 3, "name": "설계", "file": "ARCHITECTURE.md"},
    {"id": 4, "name": "구현", "file": None},
    {"id": 5, "name": "검증", "file": "TEST_REPORT.md"},
    {"id": 6, "name": "정리", "file": None},
]

EXPLAIN_BACK = {
    1: ["필수 요구사항 중 가장 구현이 어려운 것은 무엇이고 왜인가요?",
        "모호했던 점에서 세운 가정이 틀렸다면 무엇이 바뀌나요?"],
    2: ["데이터에서 발견한 가장 중요한 사실을 숫자로 말해보세요.",
        "이상값/결측치를 어떻게 처리했고, 그 처리가 결과에 어떤 영향을 주나요?"],
    3: ["사용자가 주요 버튼을 눌렀을 때 요청이 어떤 계층을 거쳐 DB까지 가나요?",
        "비즈니스 규칙 검사는 어느 계층에서 하나요? 왜 프론트엔드가 아닌가요?",
        "이 기술 스택을 고른 이유와 포기한 대안은 무엇인가요?"],
    4: ["방금 만든 코드 중 가장 핵심인 함수는 무엇이고 어떤 입력/출력을 가지나요?",
        "여기서 에러가 나면 어디서 잡히고 사용자는 무엇을 보나요?"],
    5: ["실패하거나 검증 못 한 요구사항이 있다면 이유와 계획은?",
        "가장 위험한 엣지 케이스는 무엇이었나요?"],
    6: ["2분 안에 서비스 구조와 핵심 판단을 설명해 보세요."],
}

INTERVIEW_BANK = {
    "아키텍처": ["전체 아키텍처를 설명해 주세요. 왜 이렇게 나눴나요?",
              "사용자가 1만 명으로 늘면 어디가 먼저 병목이 되나요?",
              "인증/권한은 어떻게 처리했나요? 안 했다면 어떻게 하겠어요?"],
    "데이터 흐름": ["제공된 데이터가 DB에 들어가서 화면에 보이기까지의 흐름을 설명해 주세요.",
               "운영자가 데이터를 수정하면 사용자 화면에는 언제 반영되나요?",
               "두 운영자가 동시에 같은 자원을 수정하면 어떻게 되나요?"],
    "에러 처리": ["잘못된 입력이 들어오면 어디서 막나요?",
              "외부/DB 오류가 나면 사용자에게 무엇이 보이나요?",
              "데이터 파일에 깨진 행이 있으면 어떻게 하나요?"],
    "검증": ["요구사항을 모두 만족한다는 걸 어떻게 확인했나요?",
           "AI가 만든 코드에서 직접 찾아 고친 문제가 있나요?"],
}


# ---------------------------------------------------------------- helpers
def _root(args):
    return os.path.abspath(args.get("root") or os.environ.get("WORKFLOW_ROOT") or os.getcwd())


def _doc(root, name):
    return os.path.join(root, DOCS, name)


def _read(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def _strip_comments(text):
    return re.sub(r"<!--.*?-->", "", text or "", flags=re.S)


def _now():
    return datetime.datetime.now().strftime("%H:%M")


def _load_state(root):
    text = _read(os.path.join(root, STATE_FILE))
    if text:
        return json.loads(text)
    return {"phase": 1, "history": [], "decision_count": 0, "ai_count": 0}


def _save_state(root, state):
    path = os.path.join(root, STATE_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _req_ids(root):
    text = _strip_comments(_read(_doc(root, "REQUIREMENTS.md")))
    ids = re.findall(r"\bR(\d+)\b", text)
    return ["R" + i for i in sorted(set(ids), key=int)]


def _has_todo(root, name):
    text = _read(_doc(root, name))
    return text is None or TODO_MARK in text


def _code_files(root):
    skip = {DOCS, ".workflow", ".git", "kit", "exam-kit", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
    exts = (".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".vue", ".java", ".go", ".sql")
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            if fn.endswith(exts):
                yield os.path.join(dirpath, fn)


def _gate(root, phase):
    """Return list of unmet conditions for finishing `phase`."""
    missing = []
    if phase == 1:
        if _has_todo(root, "REQUIREMENTS.md"):
            missing.append("docs/REQUIREMENTS.md를 채우고 TODO 줄을 지우세요.")
        if not _req_ids(root):
            missing.append("요구사항에 R1, R2... 형식의 ID가 하나도 없습니다.")
    elif phase == 2:
        if _has_todo(root, "DATA_NOTES.md"):
            missing.append("docs/DATA_NOTES.md를 채우고 TODO 줄을 지우세요.")
    elif phase == 3:
        if _has_todo(root, "ARCHITECTURE.md"):
            missing.append("docs/ARCHITECTURE.md를 채우고 TODO 줄을 지우세요.")
        if not re.search(r"^## D\d+", _read(_doc(root, "DECISIONS.md")) or "", re.M):
            missing.append("설계 판단을 log_decision으로 최소 1개 기록하세요.")
    elif phase == 4:
        if not any(True for _ in _code_files(root)):
            missing.append("구현된 코드 파일이 없습니다.")
    elif phase == 5:
        if _has_todo(root, "TEST_REPORT.md"):
            missing.append("docs/TEST_REPORT.md를 채우고 TODO 줄을 지우세요.")
        report = _strip_comments(_read(_doc(root, "TEST_REPORT.md")))
        for rid in _req_ids(root):
            if not re.search(r"\b%s\b.*(✅|❌)" % rid, report):
                missing.append("%s의 검증 결과(✅/❌)가 TEST_REPORT.md에 없습니다." % rid)
    elif phase == 6:
        if not os.path.exists(os.path.join(root, "README.md")):
            missing.append("프로젝트 루트에 README.md(실행 방법, 구현 범위, 미구현과 이유)를 작성하세요.")
    return missing


# ------------------------------------------------------------------ tools
def tool_kit_init(args):
    root = _root(args)
    os.makedirs(os.path.join(root, DOCS), exist_ok=True)
    created = []
    for fn in sorted(os.listdir(TEMPLATE_DIR)):
        dst = _doc(root, fn)
        if not os.path.exists(dst):
            shutil.copy(os.path.join(TEMPLATE_DIR, fn), dst)
            created.append(fn)
    agents_src = os.path.join(KIT_DIR, "AGENTS.md")
    agents_dst = os.path.join(root, "AGENTS.md")
    if os.path.exists(agents_src) and not os.path.exists(agents_dst):
        shutil.copy(agents_src, agents_dst)
        created.append("AGENTS.md")
    state = _load_state(root)
    state.setdefault("started", datetime.datetime.now().isoformat(timespec="minutes"))
    _save_state(root, state)
    return ("프로젝트 루트: %s\n생성한 파일: %s\n\n지금은 1단계(요구사항 분석)입니다. "
            "문제를 읽고 docs/REQUIREMENTS.md를 R번호로 채우세요."
            % (root, ", ".join(created) or "(이미 모두 있음)"))


def tool_phase_status(args):
    root = _root(args)
    state = _load_state(root)
    p = state["phase"]
    lines = ["현재 단계: %d/6 %s" % (p, PHASES[p - 1]["name"])]
    for ph in PHASES:
        mark = "✅" if ph["id"] < p else ("▶" if ph["id"] == p else "·")
        lines.append("%s %d. %s" % (mark, ph["id"], ph["name"]))
    missing = _gate(root, p)
    lines.append("")
    lines.append("이 단계를 마치려면:" if missing else "이 단계의 조건을 모두 충족했습니다. phase_advance를 호출하세요.")
    lines += ["- " + m for m in missing]
    ids = _req_ids(root)
    if ids:
        lines.append("\n요구사항 ID: " + ", ".join(ids))
    lines.append("기록된 판단: %d개, AI 활용 기록: %d개" % (state["decision_count"], state["ai_count"]))
    return "\n".join(lines)


def tool_phase_advance(args):
    root = _root(args)
    state = _load_state(root)
    p = state["phase"]
    missing = _gate(root, p)
    if missing and not args.get("force"):
        return ("%d단계(%s)를 아직 마칠 수 없습니다:\n" % (p, PHASES[p - 1]["name"])
                + "\n".join("- " + m for m in missing)
                + "\n\n(정말 넘어가야 하면 force=true와 reason을 주세요. 사유는 기록됩니다.)")
    state["history"].append({"phase": p, "done_at": _now(),
                             "forced": bool(missing), "reason": args.get("reason", "")})
    qs = EXPLAIN_BACK.get(p, [])
    if p < 6:
        state["phase"] = p + 1
    _save_state(root, state)
    nxt = PHASES[state["phase"] - 1]["name"] if p < 6 else "완료"
    return ("%d단계(%s) 완료 → 다음: %s\n\n"
            "다음으로 넘어가기 전에, 사용자가 아래 질문에 직접 답하게 하세요(AI가 대신 답하지 말 것):\n"
            % (p, PHASES[p - 1]["name"], nxt)
            + "\n".join("- " + q for q in qs))


def tool_log_decision(args):
    root = _root(args)
    state = _load_state(root)
    state["decision_count"] += 1
    n = state["decision_count"]
    fields = [("목표", "goal"), ("제약", "constraints"), ("근거 데이터", "evidence"),
              ("방법", "method"), ("대안과 안 고른 이유", "alternatives"), ("검증(지표)", "validation")]
    block = "\n## D%d. %s\n" % (n, args.get("title", "(제목 없음)"))
    block += "".join("- %s: %s\n" % (label, args.get(key) or "(미정)") for label, key in fields)
    path = _doc(root, "DECISIONS.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(block)
    _save_state(root, state)
    empty = [label for label, key in fields if not args.get(key)]
    note = ("\n비어 있는 항목: %s (나중에 채우세요. 특히 '검증'은 면접 단골 질문입니다)" % ", ".join(empty)) if empty else ""
    return "D%d 기록 완료.%s" % (n, note)


def tool_log_ai_usage(args):
    root = _root(args)
    state = _load_state(root)
    state["ai_count"] += 1
    n = state["ai_count"]
    phase = PHASES[state["phase"] - 1]["name"]

    def cell(k):
        return (args.get(k) or "").replace("|", "/").replace("\n", " ")

    row = "| %d | %s | %s | %s | %s | %s |\n" % (n, _now(), phase, cell("task"), cell("result"),
                                               cell("verification") or "(검증 필요)")
    with open(_doc(root, "AI_USAGE_LOG.md"), "a", encoding="utf-8") as f:
        f.write(row)
    _save_state(root, state)
    return "AI 활용 #%d 기록 완료." % n


def tool_coverage_report(args):
    root = _root(args)
    ids = _req_ids(root)
    if not ids:
        return "REQUIREMENTS.md에 R번호가 없습니다."
    corpus = ""
    for path in _code_files(root):
        try:
            corpus += _read(path) or ""
        except (UnicodeDecodeError, OSError):
            pass
    arch = _strip_comments(_read(_doc(root, "ARCHITECTURE.md")))
    report = _strip_comments(_read(_doc(root, "TEST_REPORT.md")))
    rows = ["| ID | 설계(API표) | 코드 언급 | 검증 결과 |", "|---|---|---|---|"]
    for rid in ids:
        pat = r"\b%s\b" % rid
        m = re.search(pat + r".*?(✅|❌)", report)
        rows.append("| %s | %s | %s | %s |" % (
            rid, "O" if re.search(pat, arch) else "-",
            "O" if re.search(pat, corpus) else "-", m.group(1) if m else "미검증"))
    return ("\n".join(rows) + "\n\n(코드 언급 = 주석/테스트 이름/라우트 등에 요구사항 ID가 있는지. "
            "'-'가 많으면 추적성이 약해 보입니다.)")


ROUTE_PY = re.compile(r"@(\w+)\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']", re.I)
ROUTE_JS = re.compile(r"\b(app|router)\.(get|post|put|patch|delete)\(\s*[\"'`]([^\"'`]+)", re.I)
DEF_PY = re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\(", re.M)


def _analyze(root):
    """Static scan of the project: routes, tables, errors, loaders, core functions."""
    a = {"routes": [], "tables": [], "raises": {}, "broad_except": [], "handlers": [],
         "loaders": [], "core_funcs": [], "fetches": set(), "tests": 0,
         "auth": False, "tx": False, "files": 0}
    for path in _code_files(root):
        try:
            text = _read(path) or ""
        except (UnicodeDecodeError, OSError):
            continue
        rel = os.path.relpath(path, root)
        a["files"] += 1
        lines = text.splitlines()
        for i, line in enumerate(lines):
            m = ROUTE_PY.search(line) or ROUTE_JS.search(line)
            if m:
                handler = ""
                for nxt in lines[i + 1:i + 4]:
                    d = re.search(r"def\s+(\w+)|function\s+(\w+)", nxt)
                    if d:
                        handler = d.group(1) or d.group(2)
                        break
                a["routes"].append((m.group(2).upper(), m.group(3), rel, handler))
        a["tables"] += [(t, rel) for t in re.findall(r"CREATE TABLE(?: IF NOT EXISTS)?\s+[\"`]?(\w+)", text, re.I)]
        a["tables"] += [(t, rel) for t in re.findall(r"^class\s+(\w+)\((?:[\w.]*Base|SQLModel|[\w.]*Model)\b", text, re.M)
                        if not rel.endswith("schemas.py")]
        for exc in re.findall(r"raise\s+(\w+)\(", text):
            a["raises"].setdefault(exc, set()).add(rel)
        if re.search(r"except\s*:|except\s+Exception\b", text):
            a["broad_except"].append(rel)
        if re.search(r"exception_handler|app\.use\(\s*\(err", text):
            a["handlers"].append(rel)
        if re.search(r"read_csv|csv\.(Dict)?[Rr]eader|\.csv[\"']|read_excel|json\.load", text):
            a["loaders"].append(rel)
        a["fetches"].update(re.findall(r"fetch\(\s*[\"'`]([^\"'`]+)", text))
        a["tests"] += len(re.findall(r"^\s*(?:async\s+)?def\s+test_\w+|\b(?:it|test)\(\s*[\"']", text, re.M))
        if re.search(r"auth|token|login|role|권한|Depends\(get_current", text, re.I):
            a["auth"] = True
        if re.search(r"commit\(\)|BEGIN|transaction|with_for_update|FOR UPDATE", text):
            a["tx"] = True
        if path.endswith(".py") and "test" not in rel:
            defs = [(m.start(), m.group(2), len(m.group(1))) for m in DEF_PY.finditer(text)]
            for k, (start, name, _) in enumerate(defs):
                end = defs[k + 1][0] if k + 1 < len(defs) else len(text)
                size = text.count("\n", start, end)
                if not name.startswith("_") or size > 15:
                    a["core_funcs"].append((size, name, rel))
    a["core_funcs"].sort(reverse=True)
    return a


def _project_questions(root):
    a = _analyze(root)
    qs = []  # (category, question, where to look)
    service_funcs = [f for f in a["core_funcs"] if "service" in f[2]] or a["core_funcs"]
    write_routes = [r for r in a["routes"] if r[0] != "GET"]

    qs.append(("아키텍처", "전체 구조를 30초 안에 설명해 주세요. 파일/폴더를 왜 이렇게 나눴나요?",
               "AGENTS.md 표준 구조, docs/ARCHITECTURE.md"))
    for method, path, rel, handler in write_routes[:3]:
        qs.append(("데이터 흐름", "`%s %s` 요청이 들어오면 DB에 저장될 때까지 어떤 함수들을 거치나요?" % (method, path),
                   "%s의 %s → 호출하는 service → repository" % (rel, handler or "핸들러")))
    for size, name, rel in service_funcs[:3]:
        qs.append(("핵심 로직", "`%s`(%s, %d줄)는 무슨 일을 하나요? 입력과 출력, 판단 기준은?" % (name, rel, size),
                   "%s 직접 읽기" % rel))
    if a["loaders"]:
        qs.append(("데이터 흐름", "제공된 데이터는 어디서 읽어서 어떻게 검증하고 넣나요? 깨진 행은요?",
                   ", ".join(sorted(set(a["loaders"])))))
    if a["tables"]:
        names = ", ".join(sorted(set(t for t, _ in a["tables"])))
        qs.append(("데이터 모델", "테이블(%s) 사이 관계를 설명하고, 왜 이렇게 나눴나요?" % names,
                   ", ".join(sorted(set(r for _, r in a["tables"])))))
    custom = {k: v for k, v in a["raises"].items() if k not in ("ValueError", "TypeError", "Exception")}
    if custom:
        k = sorted(custom)[0]
        qs.append(("에러 처리", "`%s`는 언제 발생하고, 사용자는 어떤 응답(상태 코드, 메시지)을 받나요?" % k,
                   ", ".join(sorted(custom[k]))))
    if a["handlers"]:
        qs.append(("에러 처리", "예상하지 못한 오류가 나면 어떻게 되나요? 내부 정보가 노출되지 않나요?",
                   ", ".join(sorted(set(a["handlers"])))))
    else:
        qs.append(("에러 처리", "전역 에러 핸들러가 보이지 않습니다. 처리 안 된 예외가 나면 사용자는 무엇을 보나요?",
                   "main.py (없다면 지금 추가 고려)"))
    for rel in a["broad_except"][:2]:
        qs.append(("에러 처리", "`%s`에서 예외를 넓게 잡은 이유는? 그러면 숨겨지는 오류는 없나요?" % rel, rel))
    if write_routes:
        qs.append(("동시성", "두 사람이 동시에 같은 자원에 쓰기 요청(%s %s)을 보내면 어떻게 되나요?"
                   % (write_routes[0][0], write_routes[0][1]),
                   "트랜잭션/정원 재확인 위치 (%s)" % ("트랜잭션 코드 있음" if a["tx"] else "트랜잭션 코드 없음")))
    qs.append(("보안/권한", "운영자 기능을 일반 사용자가 호출하지 못하게 어떻게 막나요?",
               "권한 관련 코드 %s" % ("있음" if a["auth"] else "없음 → '안 했다면 이렇게 하겠다'로 답 준비")))
    if a["fetches"]:
        qs.append(("화면 연동", "화면은 어떤 API를 부르나요(%s)? 실패하면 화면에 무엇이 보이나요?"
                   % ", ".join(sorted(a["fetches"])[:4]), "static/ 또는 web/의 JS"))
    for d in re.findall(r"^## (D\d+\. .+)$", _read(_doc(root, "DECISIONS.md")) or "", re.M):
        qs.append(("판단 기준", "'%s': 왜 이 기준인가요? 예외 상황은? 맞는지 어떤 지표로 확인했나요?" % d, "docs/DECISIONS.md"))
    report = _strip_comments(_read(_doc(root, "TEST_REPORT.md")))
    unverified = [r for r in _req_ids(root) if not re.search(r"\b%s\b.*✅" % r, report)]
    if unverified:
        qs.append(("검증", "%s는 검증이 안 됐거나 실패했습니다. 이유와 해결 계획은?" % ", ".join(unverified),
                   "docs/TEST_REPORT.md"))
    qs.append(("검증", "요구사항을 만족한다는 걸 어떻게 확인했나요? (테스트 %d개)" % a["tests"], "tests/, docs/TEST_REPORT.md"))
    qs.append(("AI 활용", "AI가 만든 결과에서 직접 찾아 고친 문제를 하나 말해 주세요.", "docs/AI_USAGE_LOG.md 검증 칸"))
    return a, qs


def tool_interview_questions(args):
    root = _root(args)
    a, qs = _project_questions(root)
    out = ["# 제출 직후 면접 예상 질문 (프로젝트 파일 %d개, API %d개 분석)" % (a["files"], len(a["routes"])), ""]
    for n, (cat, q, where) in enumerate(qs, 1):
        out.append("%d. [%s] %s\n   - 확인할 곳: %s" % (n, cat, q, where))
    out.append("\n실제 시험: 서술형 6문항, 문항당 5분, AI 사용 불가, 복사·붙여넣기 불가. 사용자가 직접 타이핑한다.")
    out.append("답변 형식(3~5문장): 결론 한 문장 → 근거(파일·함수 이름) → 예시나 지표 → 남은 한계. "
               "질문의 전제가 실제 구현과 다르면 차이를 먼저 밝힌다.")
    out.append("리허설 방법: AI는 질문을 하나씩만 내고, 사용자가 답하면 빈틈(근거·지표·예외 누락)만 지적한 뒤 다음 질문으로. "
               "AI가 모범답안을 먼저 말하지 말 것. 답을 못 한 질문은 해당 파일을 같이 읽고 다시 답하게 할 것.")
    return "\n".join(out)


def tool_answer_brief(args):
    """One-page brief of the actual project for the last review before submission."""
    root = _root(args)
    a = _analyze(root)
    out = ["# 제출 전 10분 복습 노트 (자동 생성)", "", "## API 목록", "| 메서드 | 경로 | 파일 | 핸들러 |", "|---|---|---|---|"]
    out += ["| %s | %s | %s | %s |" % r for r in a["routes"]] or ["| - | - | - | - |"]
    out += ["", "## 테이블", "- " + (", ".join("%s (%s)" % t for t in sorted(set(a["tables"]))) or "(못 찾음)")]
    out += ["", "## 핵심 함수 (긴 순서)"] + ["- %s (%s, %d줄)" % (n, r, s) for s, n, r in a["core_funcs"][:8]]
    out += ["", "## 에러", "- 직접 던지는 예외: " + (", ".join(sorted(a["raises"])) or "없음"),
            "- 전역 핸들러: " + (", ".join(sorted(set(a["handlers"]))) or "없음"),
            "- 넓게 잡는 except: " + (", ".join(a["broad_except"]) or "없음")]
    out += ["", "## 데이터 적재", "- " + (", ".join(sorted(set(a["loaders"]))) or "(못 찾음)")]
    decisions = _read(_doc(root, "DECISIONS.md")) or ""
    out += ["", "## 판단 기준"] + ["- " + d for d in re.findall(r"^## (D\d+\. .+)$", decisions, re.M)]
    out += ["", "## 약점 (질문 나오면 '알고 있고, 이렇게 하겠다'로 답하기)"]
    weak = []
    if not a["handlers"]:
        weak.append("전역 에러 핸들러 없음")
    if not a["auth"]:
        weak.append("권한 구분 코드 없음")
    if not a["tx"]:
        weak.append("트랜잭션/동시성 처리 흔적 없음")
    if a["tests"] == 0:
        weak.append("자동 테스트 없음")
    out += ["- " + w for w in weak] or ["- (자동 탐지된 약점 없음)"]
    path = os.path.join(root, ".workflow", "ANSWER_BRIEF.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    return "\n".join(out) + "\n\n(.workflow/ANSWER_BRIEF.md에 저장. 제출물에 넣을지는 사용자가 결정)"


KIT_DOCS = {"README.md", "AGENTS.md"}


def _find_forms(root):
    """Candidate organizer-provided form files: .md outside docs/ and the kit."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {DOCS, ".workflow", ".git", "kit", "exam-kit",
                                                        "node_modules", ".venv", "venv"}]
        for fn in filenames:
            if fn.lower().endswith((".md", ".txt")) and fn not in KIT_DOCS:
                found.append(os.path.relpath(os.path.join(dirpath, fn), root))
    return sorted(found)


def tool_fill_forms(args):
    """Collect work records and map them onto the organizer's form files (Codex writes them)."""
    root = _root(args)
    state = _load_state(root)
    forms = args.get("forms") or _find_forms(root)
    if not forms:
        return ("주최측 양식 파일을 찾지 못했습니다. forms 인자로 경로를 알려주세요. "
                "(프로젝트 안의 .md/.txt 중 README.md, AGENTS.md, docs/ 제외하고 찾습니다)")
    get = lambda n: _strip_comments(_read(_doc(root, n)) or "").strip() or "(기록 없음)"
    hist = "\n".join("- %d단계 %s 완료 %s%s" % (h["phase"], PHASES[h["phase"] - 1]["name"], h["done_at"],
                                            " (강제 진행: %s)" % h["reason"] if h["forced"] else "")
                     for h in state["history"]) or "(기록 없음)"
    out = ["# 주최측 양식 채우기", ""]
    for rel in forms:
        text = _read(os.path.join(root, rel))
        if text is None:
            out.append("## %s: 파일 없음" % rel)
            continue
        heads = re.findall(r"^#{1,4}\s+.+$", text, re.M) or ["(제목 없음: 문서 전체가 하나의 항목)"]
        out.append("## 양식: %s" % rel)
        out += ["  " + h for h in heads]
        out.append("")
    out += ["# 근거 자료 (이 기록에 있는 사실만 사용)",
            "## 진행 단계 이력\n" + hist,
            "## 요구사항 (docs/REQUIREMENTS.md)\n" + get("REQUIREMENTS.md"),
            "## 데이터 (docs/DATA_NOTES.md)\n" + get("DATA_NOTES.md"),
            "## 아키텍처 (docs/ARCHITECTURE.md)\n" + get("ARCHITECTURE.md"),
            "## 판단 (docs/DECISIONS.md)\n" + get("DECISIONS.md"),
            "## 검증 (docs/TEST_REPORT.md)\n" + get("TEST_REPORT.md"),
            "## AI 활용 (docs/AI_USAGE_LOG.md)\n" + get("AI_USAGE_LOG.md"),
            "## 작업 방식\n- AGENTS.md 규칙과 exam-workflow MCP(단계 관문, 판단·AI 활용 기록, 요구사항 추적, 면접 리허설)를 "
            "직접 만들어 사용함. 서비스 코드는 사전에 준비하지 않음.",
            "",
            "# 작성 지시",
            "1. 양식 파일의 제목, 순서, 안내 문구를 바꾸지 말고 각 항목 아래에만 채운다.",
            "2. 각 항목에 맞는 근거 자료를 골라 쓴다. 기록에 없는 내용은 지어내지 말고 '[확인 필요]'로 남긴다.",
            "3. 판단 기준은 목표 → 근거(숫자) → 대안 → 검증 지표 순서로 쓴다.",
            "4. AI 활용은 '맡긴 일 → 결과 → 내가 검증하거나 고친 점'이 드러나게 쓴다. 고친 사례를 최소 1개 넣는다.",
            "4-1. 응시 가이드 기준으로 '선택한 판단과 근거, 검증 결과, 남은 한계'가 반드시 들어가야 한다. 남은 한계를 숨기지 않는다.",
            "5. 다 쓰면 사용자에게 '[확인 필요]' 항목을 보여주고 확인을 받는다."]
    return "\n".join(out)


def _schema(props=None, required=None):
    props = dict(props or {})
    props["root"] = {"type": "string", "description": "프로젝트 루트 절대경로 (생략 시 WORKFLOW_ROOT 또는 현재 디렉터리)"}
    return {"type": "object", "properties": props, "required": required or []}


S = {"type": "string"}
TOOLS = {
    "kit_init": (tool_kit_init, "프로젝트에 docs/ 템플릿과 AGENTS.md를 만들고 워크플로를 시작한다. 시험 시작 직후 1회.", _schema()),
    "phase_status": (tool_phase_status, "현재 단계와 다음 단계로 가기 위해 부족한 것을 보여준다. 작업 시작 전 항상 호출.", _schema()),
    "phase_advance": (tool_phase_advance, "현재 단계 조건을 검사하고 통과하면 다음 단계로 넘긴다. 사용자에게 던질 설명 질문을 돌려준다.",
                      _schema({"force": {"type": "boolean"}, "reason": S})),
    "log_decision": (tool_log_decision, "중요한 설계/도메인 판단(예: 배정 기준)을 DECISIONS.md에 기록한다.",
                     _schema({"title": S, "goal": S, "constraints": S, "evidence": S, "method": S,
                              "alternatives": S, "validation": S}, ["title"])),
    "log_ai_usage": (tool_log_ai_usage, "AI에게 맡긴 일과 검증 내용을 AI_USAGE_LOG.md에 한 줄 기록한다. 의미 있는 작업마다 호출.",
                     _schema({"task": S, "result": S, "verification": S}, ["task"])),
    "coverage_report": (tool_coverage_report, "요구사항 ID별 설계/코드/검증 추적표를 만든다.", _schema()),
    "interview_questions": (tool_interview_questions, "프로젝트 코드와 문서를 분석해 제출 직후 나올 면접 질문(파일·함수 단위)을 만든다. 제출 전 리허설용.", _schema()),
    "answer_brief": (tool_answer_brief, "실제 코드에서 API·테이블·핵심 함수·에러·약점을 뽑아 제출 전 10분 복습 노트를 만든다.", _schema()),
    "fill_forms": (tool_fill_forms, "주최측이 제공한 제출 양식 파일의 목차를 읽고, 작업 기록을 근거 자료로 모아 그 파일을 채우도록 안내한다. forms를 생략하면 양식 파일을 자동으로 찾는다.",
                   _schema({"forms": {"type": "array", "items": {"type": "string"}, "description": "양식 파일 경로들 (프로젝트 기준 상대경로)"}})),
}


# --------------------------------------------------------------- JSON-RPC
def _send(msg):
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _handle(req):
    method, rid = req.get("method"), req.get("id")
    if rid is None:  # notification
        return None
    if method == "initialize":
        ver = (req.get("params") or {}).get("protocolVersion", "2025-06-18")
        return {"protocolVersion": ver, "capabilities": {"tools": {}},
                "serverInfo": {"name": "exam-workflow", "version": "1.0.0"}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [{"name": n, "description": d, "inputSchema": s} for n, (_, d, s) in TOOLS.items()]}
    if method == "tools/call":
        params = req.get("params") or {}
        entry = TOOLS.get(params.get("name"))
        if not entry:
            raise ValueError("unknown tool: %s" % params.get("name"))
        try:
            text, err = entry[0](params.get("arguments") or {}), False
        except Exception as e:  # report tool failures to the model, keep server alive
            text, err = "도구 실행 오류: %s: %s" % (type(e).__name__, e), True
        return {"content": [{"type": "text", "text": text}], "isError": err}
    raise LookupError(method)


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            _send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        try:
            result = _handle(req)
            if result is not None:
                _send({"jsonrpc": "2.0", "id": req["id"], "result": result})
        except LookupError as e:
            _send({"jsonrpc": "2.0", "id": req.get("id"), "error": {"code": -32601, "message": "method not found: %s" % e}})
        except Exception as e:
            _send({"jsonrpc": "2.0", "id": req.get("id"), "error": {"code": -32603, "message": str(e)}})


if __name__ == "__main__":
    main()
