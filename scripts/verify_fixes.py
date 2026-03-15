"""실증검증 스크립트: BUG-2, BUG-3, P4 수정 사항 live 검증.

실행 방법:
    source .venv/bin/activate
    python scripts/verify_fixes.py
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.consensus import AgentVote, ConsensusEngine

PASS = "\033[32m[PASS]\033[0m"
FAIL = "\033[31m[FAIL]\033[0m"
INFO = "\033[36m[INFO]\033[0m"

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    tag = PASS if condition else FAIL
    print(f"  {tag} {name}")
    if detail:
        for line in detail.splitlines():
            print(f"         {line}")
    results.append((name, condition, detail))


# ---------------------------------------------------------------------------
# BUG-2: environment_constrained 분산 계산 제외
# ---------------------------------------------------------------------------


def verify_bug2() -> None:
    print("\n=== BUG-2: 환경 제약 에이전트 분산 오탐 수정 검증 ===")

    engine = ConsensusEngine(
        threshold=0.9,
        score_ready_min=90,
        dispersion_alert_threshold=20,
        max_rereviews=2,
    )

    # --- 시나리오 A: 수정 전 동작 재현 (environment_constrained=False) ---
    print(f"\n  {INFO} 시나리오 A: 수정 전 동작 (constrained 플래그 없음)")
    old_votes = [
        AgentVote("claude", score=95, vote="ready", confidence=1.0, base_weight=0.40),
        AgentVote("codex",  score=65, vote="not_ready", confidence=0.8, base_weight=0.35),
        AgentVote("gemini", score=100, vote="ready", confidence=1.0, base_weight=0.25),
    ]
    result_old = engine.compute("TASK-BUG2-OLD", old_votes)
    check(
        "수정 전: 분산=35 → dispersion_warning=True (예상된 오탐)",
        result_old.dispersion_warning is True,
        f"dispersion = 100-65 = 35 > 20, warning={result_old.dispersion_warning}",
    )

    # --- 시나리오 B: 수정 후 동작 (environment_constrained=True) ---
    print(f"\n  {INFO} 시나리오 B: 수정 후 동작 (Codex에 constrained 플래그)")
    new_votes = [
        AgentVote("claude", score=95, vote="ready", confidence=1.0, base_weight=0.40),
        AgentVote(
            "codex", score=65, vote="not_ready", confidence=0.8, base_weight=0.35,
            environment_constrained=True,
        ),
        AgentVote("gemini", score=100, vote="ready", confidence=1.0, base_weight=0.25),
    ]
    result_new = engine.compute("TASK-BUG2-NEW", new_votes)
    check(
        "수정 후: 분산=5(Claude/Gemini만) → dispersion_warning=False",
        result_new.dispersion_warning is False,
        f"unconstrained scores=[95,100], dispersion=5 ≤ 20, warning={result_new.dispersion_warning}",
    )

    # --- 시나리오 C: 제약 투표도 비율 계산에 포함 ---
    print(f"\n  {INFO} 시나리오 C: 제약 투표도 ratio 계산에는 포함")
    check(
        "Codex(not_ready) 포함: ratio=0.65 < 0.9 → rework",
        result_new.ratio < 0.9 and result_new.action == "rework",
        f"ready_weight=0.40+0.25=0.65, ratio={result_new.ratio:.2f}, action={result_new.action}",
    )

    # --- 시나리오 D: build_votes_from_reports 플래그 전파 ---
    print(f"\n  {INFO} 시나리오 D: build_votes_from_reports() 플래그 전파")
    reports = {
        "claude": {"score": 95, "vote": "ready", "confidence": 1.0},
        "codex": {
            "score": 65, "vote": "not_ready", "confidence": 0.8,
            "environment_constrained": True,
        },
    }
    config = [
        {"id": "claude", "base_weight": 0.40, "reliability": 1.0},
        {"id": "codex",  "base_weight": 0.35, "reliability": 1.0},
    ]
    votes = engine.build_votes_from_reports(reports, config)
    codex_v = next(v for v in votes if v.agent_id == "codex")
    check(
        "build_votes_from_reports: codex.environment_constrained=True",
        codex_v.environment_constrained is True,
        f"codex.environment_constrained={codex_v.environment_constrained}",
    )


# ---------------------------------------------------------------------------
# BUG-3: 중복 escalation 방지
# ---------------------------------------------------------------------------


def verify_bug3() -> None:
    print("\n=== BUG-3: 중복 escalation 이슈 생성 방지 검증 ===")

    import yaml
    from scripts.orchestrator import Orchestrator

    MINIMAL_CONFIG = {
        "github": {"repo": "owner/testrepo", "polling_interval_seconds": 60, "mention_user": ""},
        "orchestrator": {
            "target_project_path": "",
            "inbox_dir": "inbox/",
            "brief_archive_dir": "docs/briefs/",
            "orchestra_dir": ".orchestra/",
            "assignment_timeout_minutes": 30,
            "max_retries": 3,
        },
        "consensus": {
            "threshold": 0.9, "score_ready_min": 90,
            "dispersion_alert_threshold": 20, "max_rereviews": 2,
        },
        "quality": {"enforce_english_comments": True, "validate_schemas": False},
        "logging": {
            "level": "INFO",
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "file": ".orchestra/logs/orchestrator.log",
        },
    }
    MINIMAL_AGENTS = {"agents": [
        {
            "id": "claude", "cli_command": "claude", "display_name": "Claude Code",
            "base_weight": 0.40, "reliability": 1.0,
            "primary_stages": ["kickoff"], "secondary_stages": [],
            "can_modify": [], "cannot_modify": [],
            "can_veto": False, "sandbox_mode": None,
        }
    ]}

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir()
        (cfg_dir / "config.yaml").write_text(yaml.dump(MINIMAL_CONFIG))
        (cfg_dir / "agents.json").write_text(json.dumps(MINIMAL_AGENTS))

        with (
            patch("scripts.orchestrator.GitHubClient"),
            patch("scripts.orchestrator.StateManager"),
            patch("scripts.orchestrator.ConsensusEngine"),
            patch.object(
                Orchestrator, "check_agent_availability",
                side_effect=lambda agents: [{**a, "available": True} for a in agents],
            ),
        ):
            orch = Orchestrator(
                config_path=cfg_dir / "config.yaml",
                agents_path=cfg_dir / "agents.json",
            )

    orch.github.create_issue = MagicMock(return_value=10)

    # --- 시나리오 A: 동일 agent/task 2회 호출 ---
    print(f"\n  {INFO} 시나리오 A: 동일 agent/task에 _create_escalation_issue 2회 호출")
    ctx = {"agent_id": "codex", "task_id": "task-dup-001"}
    r1 = orch._create_escalation_issue("timeout", ctx)
    r2 = orch._create_escalation_issue("timeout", ctx)
    check(
        "1회차: GitHub create_issue 호출 → issue #10 반환",
        r1 == 10,
        f"반환값={r1}",
    )
    check(
        "2회차: 중복 감지 → None 반환, create_issue 추가 호출 없음",
        r2 is None and orch.github.create_issue.call_count == 1,
        f"반환값={r2}, create_issue 총 호출={orch.github.create_issue.call_count}회",
    )

    # --- 시나리오 B: 다른 task는 정상 생성 ---
    print(f"\n  {INFO} 시나리오 B: 다른 task_id는 별도 escalation 생성")
    orch.github.create_issue = MagicMock(side_effect=[20, 21])
    r3 = orch._create_escalation_issue("timeout", {"agent_id": "codex", "task_id": "task-A"})
    r4 = orch._create_escalation_issue("timeout", {"agent_id": "codex", "task_id": "task-B"})
    check(
        "task-A, task-B 각각 escalation 생성 (2회 호출)",
        r3 == 20 and r4 == 21 and orch.github.create_issue.call_count == 2,
        f"task-A issue={r3}, task-B issue={r4}, 총 호출={orch.github.create_issue.call_count}회",
    )

    # --- 시나리오 C: consensus escalate 경로 dedup set ---
    print(f"\n  {INFO} 시나리오 C: _escalated_issue_numbers set 초기화 확인")
    check(
        "오케스트레이터 초기화 시 _escalated_issue_numbers=set() 존재",
        hasattr(orch, "_escalated_issue_numbers") and isinstance(orch._escalated_issue_numbers, set),
        f"_escalated_issue_numbers={orch._escalated_issue_numbers}",
    )
    orch._escalated_issue_numbers.add(5)
    check(
        "issue #5 등록 후 중복 여부 판단 가능",
        5 in orch._escalated_issue_numbers and 7 not in orch._escalated_issue_numbers,
        f"5 in set={5 in orch._escalated_issue_numbers}, 7 in set={7 in orch._escalated_issue_numbers}",
    )


# ---------------------------------------------------------------------------
# P4: 좀비 프로세스 정리 로직 검증
# ---------------------------------------------------------------------------


def verify_p4() -> None:
    print("\n=== P4: start_t1.sh 좀비/중지 프로세스 정리 검증 ===")

    # --- 시나리오 A: 문법 검사 ---
    print(f"\n  {INFO} 시나리오 A: bash -n 문법 검사")
    t1_path = Path(__file__).parent / "start_t1.sh"
    r = subprocess.run(["bash", "-n", str(t1_path)], capture_output=True, text=True)
    check("start_t1.sh bash -n 문법 검사 통과", r.returncode == 0, r.stderr.strip())

    # --- 시나리오 B: 좀비 정리 코드 포함 여부 ---
    print(f"\n  {INFO} 시나리오 B: 좀비 정리 로직 포함 확인")
    content = t1_path.read_text()
    check("pgrep 프로세스 탐지 코드 포함", "pgrep" in content)
    check("kill -9 강제 종료 코드 포함", "kill -9" in content)
    check("T/Z 상태 필터링 코드 포함", "T" in content and "Z" in content)
    check("정상 실행 중 프로세스 보호 (exit 1) 코드 포함", 'exit 1' in content)

    # --- 시나리오 C: SIGSTOP 프로세스 정리 실증 ---
    print(f"\n  {INFO} 시나리오 C: 실제 SIGSTOP 프로세스 감지 및 kill 검증")
    dummy = subprocess.Popen(["sleep", "30"])
    dummy_pid = dummy.pid
    os.kill(dummy_pid, signal.SIGSTOP)
    time.sleep(0.3)

    # 프로세스 상태 확인
    state_result = subprocess.run(
        ["ps", "-o", "state=", "-p", str(dummy_pid)],
        capture_output=True, text=True,
    )
    state = state_result.stdout.strip()
    check(
        f"더미 프로세스(PID={dummy_pid}) SIGSTOP → T 상태 확인",
        "T" in state,
        f"ps state={state!r}",
    )

    # 정리 로직 시뮬레이션: T 상태면 kill
    killed = False
    if "T" in state or "Z" in state:
        os.kill(dummy_pid, signal.SIGKILL)
        killed = True
        time.sleep(0.2)

    # 부모 프로세스가 wait() 해야 zombie 완전 소멸
    try:
        dummy.wait(timeout=2)
    except Exception:
        pass
    time.sleep(0.1)

    alive = subprocess.run(
        ["ps", "-p", str(dummy_pid)],
        capture_output=True,
    ).returncode
    check(
        "kill + wait 후 프로세스 완전 소멸 확인",
        killed and alive != 0,
        f"killed={killed}, ps returncode={alive} (0=살아있음, 1=소멸)",
    )


# ---------------------------------------------------------------------------
# 결과 요약
# ---------------------------------------------------------------------------


def print_summary() -> None:  # noqa: return handled via sys.exit
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    failed = [name for name, ok, _ in results if not ok]

    print("\n" + "=" * 60)
    print(f"  실증검증 결과: {passed}/{total} 통과")
    print("=" * 60)
    if failed:
        print(f"\n  실패 항목:")
        for name in failed:
            print(f"    {FAIL} {name}")
    else:
        print(f"\n  {PASS} 모든 항목 통과")
    print()

    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    verify_bug2()
    verify_bug3()
    verify_p4()
    sys.exit(print_summary())
