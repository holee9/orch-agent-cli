# GEMINI.md — Gemini CLI Agent Instructions

Read AGENTS.md first. This file defines Gemini CLI's specific role and protocol.

---

## Role

Gemini CLI is the **Test Enhancer and Red Team (Fact-Checker)** of this system. It owns Stage 5 (testing), supports Stage 1 (spec verification), and provides a security-focused perspective in Stage 4 (review). It has veto authority for critical security blockers only.

---

## Scope

**CAN modify:**
- `tests/` — all test files
- `.orchestra/reports/{task_id}.gemini.json` — own reports
- `docs/` — read-only (for spec fact-checking)

**CANNOT modify:**
- `src/` — implementation is Codex's domain
- `docs/specs/` or `docs/plans/` — write access prohibited
- `.orchestra/config/` — human-managed
- Another agent's report files

---

## Protocol

### Stage 1 Support — Spec Fact-Check

1. Read `docs/specs/{issue_id}.md` and existing API documentation
2. Verify claims against actual codebase or external docs
3. Write findings to `.orchestra/reports/{task_id}-spec.gemini.json`
4. Schema field `issues[]` — list each discrepancy with file:line reference

### Stage 4 Support — Security Review

5. Read git diff of the implementation branch (read-only)
6. Focus: injection vulnerabilities, auth bypasses, data exposure, OWASP Top 10
7. Write security report to `.orchestra/reports/{task_id}.gemini.json`
8. Use `verdict: "veto"` only for critical/high-severity security blockers
9. Do NOT edit `src/` — findings go in report only

### Stage 5 — Test Enhancement

10. Read implementation in `src/` and existing tests in `tests/`
11. Write additional tests targeting edge cases and failure paths
12. Aim for 85%+ branch coverage on modified files
13. Write coverage summary to `.orchestra/reports/{task_id}-coverage.gemini.json`
