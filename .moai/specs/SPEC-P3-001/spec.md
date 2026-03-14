# SPEC-P3-001: Phase 3 안정성 및 관측성 개선

## Metadata

| Field | Value |
|-------|-------|
| SPEC-ID | SPEC-P3-001 |
| Created | 2026-03-15 |
| Status | approved |
| Priority | P1 (Critical) |
| issue_number | 0 |

## Summary

1차 E2E 검증(f129e43) 완료 후 발견된 구조적 버그 및 운영 개선 사항을 구현한다.
P1(안정성) 및 P2(관측성) 우선 구현, P3/P4는 후속 진행.

## Requirements (EARS Format)

### P1 — 안정성 (Stability)

**REQ-001**: WHEN orchestrator starts, the system SHALL check for an existing PID lock file at `/tmp/orchestrator.pid` and abort with error message if another instance is already running.

**REQ-002**: WHEN orchestrator starts successfully, the system SHALL write its PID to `/tmp/orchestrator.pid` and remove the file on clean exit or SIGTERM/SIGINT.

**REQ-003**: WHEN a poll cycle begins, the orchestrator SHALL reload `config/agents.json` from disk so that configuration changes take effect without restart.

**REQ-004**: WHEN `config/agents.json` cannot be read during reload, the system SHALL log a warning and continue using the last successfully loaded configuration.

### P2 — 관측성 (Observability)

**REQ-005**: WHEN the orchestrator logs any message, timestamps SHALL be formatted as UTC ISO8601 (`YYYY-MM-DDTHH:MM:SS.mmmZ`) so T1 logs are consistent with T2-T4 bash logs.

**REQ-006**: WHEN the orchestrator initializes, it SHALL configure Python's logging module with UTC timestamps using `logging.Formatter(datefmt)` and `converter = time.gmtime`.

## Acceptance Criteria

### AC-001: PID Lock — Duplicate Prevention
- Given: orchestrator is running with PID file at `/tmp/orchestrator.pid`
- When: a second instance of `python scripts/orchestrator.py` is launched
- Then: the second instance prints an error message and exits with non-zero code
- And: the first instance continues running uninterrupted

### AC-002: PID Lock — Clean Startup
- Given: no PID file exists
- When: orchestrator starts
- Then: `/tmp/orchestrator.pid` is created containing the process PID
- And: on SIGTERM/SIGINT, the PID file is deleted before exit

### AC-003: PID Lock — Stale PID Cleanup
- Given: a stale PID file exists for a non-running process
- When: orchestrator starts
- Then: stale PID file is detected (process not running), removed, and startup proceeds normally

### AC-004: Hot-Reload — Config Change Detected
- Given: orchestrator is running
- When: `config/agents.json` is modified on disk
- Then: within the next poll cycle, the new config is loaded and takes effect
- And: a log entry indicates "agents config reloaded"

### AC-005: Hot-Reload — SIGHUP Support
- Given: orchestrator is running
- When: SIGHUP signal is received
- Then: `config/agents.json` is reloaded immediately (not waiting for next poll)
- And: a log entry indicates "agents config reloaded via SIGHUP"

### AC-006: UTC Timestamp — Log Format
- Given: orchestrator produces log output
- When: any log message is emitted
- Then: the timestamp format is `YYYY-MM-DDTHH:MM:SS.mmmZ` (UTC)
- And: the format matches the `date -u +"%Y-%m-%dT%H:%M:%SZ"` output from T2-T4 bash scripts

## Technical Approach

### Files to Modify

- `scripts/orchestrator.py` — PID lock, hot-reload, UTC logging
  - Add `acquire_pid_lock()` / `release_pid_lock()` functions
  - Add `_load_agents_config()` helper (extracted from `__init__`)
  - Add SIGHUP handler calling `_load_agents_config()`
  - Modify poll loop to call `_load_agents_config()` at cycle start
  - Modify logging setup to use UTC formatter

### Files to Create

- `tests/test_orchestrator_stability.py` — TDD tests for all ACs above

### Key Implementation Notes

- Python `signal.signal(signal.SIGHUP, handler)` for SIGHUP support
- PID lock: `os.path.exists` + `psutil.pid_exists` or `/proc/{pid}` check for stale detection
- UTC logging: `logging.Formatter(datefmt='%Y-%m-%dT%H:%M:%S')` + `logging.Formatter.converter = time.gmtime`
- Stale PID detection: read PID from file, check `os.kill(pid, 0)` (raises OSError if not running)

## Out of Scope (Phase 4)

- P3: CLI availability check (D-004) — separate SPEC
- P4: Branch auto-creation (D-005), security fix (D-006), Issue cleanup — separate SPEC
