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

EXPLAIN_POINTS = {
    1: "필수 요구사항, 내가 정한 가정, 실무자 에이전트에게 확인한 내용",
    2: "데이터의 핵심 숫자, 정제 규칙과 그 이유",
    3: "요청이 router → service → repository를 거치는 경로, 규칙 검사 위치, 스택 선택 이유",
    4: "구현한 핵심 함수와 에러가 잡히는 위치",
    5: "검증 결과와 남은 한계",
    6: "서비스 구조와 핵심 판단",
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
    point = EXPLAIN_POINTS.get(p, "")
    if p < 6:
        state["phase"] = p + 1
    _save_state(root, state)
    nxt = PHASES[state["phase"] - 1]["name"] if p < 6 else "완료"
    return ("%d단계(%s) 완료 → 다음: %s\n\n사용자에게 이번 단계 결과를 3줄 이내로 설명하세요: %s"
            % (p, PHASES[p - 1]["name"], nxt, point))


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
    note = ("\n비어 있는 항목: %s (나중에 채우세요. 특히 '검증'은 판단이 맞았다는 근거입니다)" % ", ".join(empty)) if empty else ""
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


def tool_structure_summary(args):
    """Facts from the actual code, for writing the as-built summary in ARCHITECTURE.md."""
    root = _root(args)
    a = _analyze(root)
    out = ["# 실제 구현 사실 (코드 정적 분석, 파일 %d개)" % a["files"], "", "## API"]
    out += ["- %s %s → %s (%s)" % (m, path, h or "?", rel) for m, path, rel, h in a["routes"]] or ["- (못 찾음)"]
    out += ["", "## 테이블: " + (", ".join("%s (%s)" % t for t in sorted(set(a["tables"]))) or "(못 찾음)")]
    out += ["", "## 핵심 함수 (긴 순서)"] + ["- %s (%s, %d줄)" % (n, r, sz) for sz, n, r in a["core_funcs"][:8]]
    out += ["", "## 에러",
            "- 직접 던지는 예외: " + (", ".join("%s (%s)" % (k, ", ".join(sorted(v))) for k, v in sorted(a["raises"].items())) or "없음"),
            "- 전역 핸들러: " + (", ".join(sorted(set(a["handlers"]))) or "없음"),
            "- 넓게 잡는 except: " + (", ".join(a["broad_except"]) or "없음")]
    out += ["", "## 데이터 적재: " + (", ".join(sorted(set(a["loaders"]))) or "(못 찾음)"),
            "## 화면이 부르는 API: " + (", ".join(sorted(a["fetches"])) or "(못 찾음)"),
            "## 권한 처리 흔적: %s / 트랜잭션 흔적: %s / 테스트 함수: %d개"
            % ("있음" if a["auth"] else "없음", "있음" if a["tx"] else "없음", a["tests"])]
    out += ["", "# 작성 지시",
            "docs/ARCHITECTURE.md 맨 아래에 '## 실제 구현 요약' 절을 만들거나 갱신한다. 계획이 아니라 **지금 코드 기준**으로, 위 사실과 코드를 직접 읽어서 쓴다.",
            "1. 전체 구조: 폴더·파일별 역할 한 줄씩",
            "2. 요청 흐름: 핵심 기능 2~3개를 화면 → router 함수 → service 함수 → repository → DB 순서로, 실제 함수 이름으로",
            "3. 데이터 구조: 테이블과 관계, 제공 데이터를 적재하는 방법, 깨진 데이터 처리",
            "4. 에러 처리: 어떤 상황에 어떤 예외 → 어떤 상태 코드·메시지 → 화면에 어떻게 보이는지",
            "5. 판단 기준: DECISIONS.md의 각 판단을 한 줄로 (기준 → 이유 → 검증 지표)",
            "6. 남은 한계: 위 사실에서 '없음'으로 나온 항목(권한, 트랜잭션, 테스트 등) 중 해당하는 것과 개선 방향",
            "설계 계획과 실제 구현이 달라진 부분이 있으면 '계획과 달라진 점'으로 밝힌다. 짧고 평이한 문장으로 쓴다.",
            "다 쓰면 사용자에게 이 절을 읽어 보라고 안내한다."]
    return "\n".join(out)


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
            "## 작업 방식\n- AGENTS.md 규칙과 exam-workflow MCP(단계 관문, 판단·AI 활용 기록, 요구사항 추적, 구현 구조 요약)를 "
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
    "structure_summary": (tool_structure_summary, "실제 코드를 분석해 API·테이블·핵심 함수·에러 처리·한계를 뽑고, ARCHITECTURE.md에 '실제 구현 요약'을 쓰도록 안내한다. 마무리 단계에서 사용.", _schema()),
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
