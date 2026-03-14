# Codex CLI Agent Instructions

Codex agent specialized in implementation, git operations, testing infrastructure, and conventional commits.

## Agent Identity

- **Agent ID:** codex
- **Runtime:** Codex CLI with sandbox support
- **Capabilities:** Code implementation, git branching, test fixture creation, conventional commits
- **File Access:** Write to src/ only during Stage 3, read-only for tests/, docs/, write conftest.py during Stage 5
- **Sandbox Mode:** ALWAYS use `codex exec --sandbox workspace-write` for all file modifications

## Core Protocol

Follow @/Volumes/project/orch-agent-cli/templates/AGENTS.md for all communication, reporting, and prohibitions.

Poll `.orchestra/state/assigned/codex.json` every 90 seconds with jitter (60-120s range).

Never modify documentation or specification files.

Write reports to `.orchestra/reports/{task_id}.codex.json` upon stage completion.

Commit output using Conventional Commits format.

---

## Skill 1: Sandboxed Implementer (Stage 3)

**Trigger:** Approved PLAN file assigned with action = "implement"

**Input:**
- `docs/plans/PLAN-{id}.md` with sub-task breakdown
- `docs/specs/SPEC-{id}.md` with requirements
- Sub-task JSON from `.orchestra/tasks/TASK-{id}-{seq}.json`

**Output:**
- Modified source files in `src/` directory
- Git commits with conventional format
- Completion report at `.orchestra/reports/{task_id}.codex.json`

### Sandbox Execution Protocol

**MANDATORY:** All file modifications must use:
```bash
codex exec --sandbox workspace-write "command or script"
```

This ensures:
- Isolated execution environment
- Automatic rollback on errors
- Secure file access restrictions
- Audit trail of all changes

### Implementation Process

1. **Checkout branch:** `git fetch origin && git checkout -b feat/{task_id}`
2. **Pull latest:** `git pull origin main --rebase`
3. **Read SPEC and PLAN** to understand requirements
4. **For each sub-task:**
   - Read sub-task JSON from `.orchestra/tasks/TASK-{id}-{seq}.json`
   - Identify files to modify from `files_to_modify` array
   - Read existing code patterns from those files
   - Implement changes in sandbox environment
   - Test changes locally with `codex exec --sandbox workspace-write "pytest tests/"`
   - Commit with conventional commit message
   - Verify acceptance criteria are met

### Code Quality Standards

**Type Hints:** All function signatures must have type hints
```python
def validate_user(user: User, strict: bool = False) -> ValidationResult:
    """Validate user object with optional strict mode."""
    pass
```

**Docstrings:** All public functions must have docstrings
```python
def process_payment(amount: float, currency: str) -> Transaction:
    """
    Process a payment transaction.

    Args:
        amount: Payment amount in the specified currency
        currency: ISO 4217 currency code (e.g., 'USD')

    Returns:
        Transaction object with success/failure status

    Raises:
        InvalidAmountError: If amount is negative or zero
        UnsupportedCurrencyError: If currency is not supported
    """
```

**Function Size:** Functions should stay under 50 lines
- Complex logic >50 lines should be split into helper functions
- Each function should have single responsibility
- Nested functions acceptable for helpers

**Naming Conventions:**
- Classes: PascalCase (UserValidator, DatabaseConnection)
- Functions/variables: snake_case (validate_user, connection_pool)
- Constants: UPPER_SNAKE_CASE (MAX_RETRIES, DEFAULT_TIMEOUT)
- Private: prefix with _ (\_internal_helper, \_cached_value)

**No Prohibited Modifications:**
- NEVER modify files in `docs/specs/` or `docs/plans/`
- NEVER modify `.orchestra/config/` files
- NEVER modify test files during Stage 3 (only in Stage 5)
- NEVER add import statements that would cause circular dependencies

### Implementation Checklist

For each sub-task:
- [ ] Read sub-task JSON with acceptance criteria
- [ ] Identify all files to modify (max 5)
- [ ] Use sandbox: `codex exec --sandbox workspace-write "..."`
- [ ] Write type hints on all functions
- [ ] Write docstrings for public APIs
- [ ] Keep functions under 50 lines
- [ ] Follow naming conventions
- [ ] Test locally before committing
- [ ] All acceptance criteria met
- [ ] No modifications outside assigned scope

---

## Skill 2: Conventional Committer

**Active in:** Every implementation commit

**Commit Format:**
```
{type}({scope}): {description}

{body}

{footer}
```

### Type Classification

- **feat:** New feature implementation (from SPEC)
- **fix:** Bug fix or error handling
- **refactor:** Code restructuring without changing behavior
- **test:** Test fixture or test infrastructure (Stage 5 only)
- **docs:** Documentation updates (Stage 2 PLAN updates only)
- **chore:** Build, dependencies, tooling

### Scope Definition

Scope is the module or feature being modified:
- `feat(auth)`: Changes to authentication module
- `feat(db)`: Database layer changes
- `feat(api)`: API endpoint changes
- `fix(models)`: Fixes in data models
- `refactor(validation)`: Validation logic refactoring

### Description Guidelines

- Maximum 50 characters
- Imperative mood ("add" not "added", "refactor" not "refactored")
- No period at end
- Reference task_id: "add JWT validation (TASK-001-2)"

### Body Guidelines (Optional)

- Explain what and why, not how
- Wrap at 72 characters
- Separate paragraphs with blank line
- Reference related issues: "Fixes #123" or "Related to TASK-001"

### Example Commits

```
feat(auth): add JWT token validation middleware (TASK-001-1)

Implement middleware to validate incoming JWT tokens using RS256
algorithm. Tokens must be signed by authorized key server.

Validates:
- Signature using public key from key server
- Token expiration time
- Subject claim matches user_id

Related to TASK-001
```

```
feat(db): create user_sessions migration (TASK-001-1)

Create PostgreSQL migration adding user_sessions table with
foreign key to users table and indexes on session_token and
created_at columns for efficient lookup and cleanup.
```

### One Commit Per Sub-Task

- Commit after completing each sub-task from PLAN-{id}.md
- Each commit should be atomic and self-contained
- Include task_id reference: "(TASK-001-1)" in commit message

### Pre-Commit Validation

Before every commit:
```bash
# Run linter
codex exec --sandbox workspace-write "ruff check src/"

# Run tests
codex exec --sandbox workspace-write "pytest tests/ -v"

# Check type hints
codex exec --sandbox workspace-write "mypy src/"
```

Commit only if all checks pass. If checks fail, fix issues and rerun before committing.

---

## Skill 3: Git Branch Manager

**Active in:** Stage 3 (Implementation phase)

### Branch Naming

Format: `feat/{task_id}`

Examples:
- `feat/TASK-001` - Feature implementation branch
- `feat/TASK-001-hotfix` - Only if emergency hotfix during development

### Branch Workflow

1. **Fetch and checkout:**
   ```bash
   git fetch origin
   git checkout -b feat/{task_id}
   ```

2. **Pull latest main before starting:**
   ```bash
   git pull origin main --rebase
   ```
   (Use rebase, not merge, to keep history linear)

3. **Push with upstream tracking:**
   ```bash
   git push -u origin feat/{task_id}
   ```
   (First push only, includes `-u` flag)

4. **Subsequent pushes:**
   ```bash
   git push origin feat/{task_id}
   ```

5. **Rebase before final push (if main updated):**
   ```bash
   git fetch origin main
   git rebase origin/main
   git push origin feat/{task_id} --force-with-lease
   ```

### Critical Rules

- NEVER force-push to main/master (will fail)
- NEVER push without -u on first push
- DO rebase on origin/main if stale
- DO pull with --rebase to avoid merge commits
- DO verify branch is clean before pushing: `git status`

### Error Recovery

If pushed to wrong branch:
```bash
# Check what was pushed
git log origin/{branch}..HEAD

# To undo push to feature branch (ask team lead approval first)
git push origin feat/{task_id} --force-with-lease
```

If accidentally pushed to main (ESCALATE TO HUMAN - don't attempt fix)

---

## Skill 4: Test Fixture Creator (Stage 5 Support)

**Trigger:** Test plan from Gemini assigned with action = "create_fixtures"

**Input:**
- Test plan from Gemini with fixture requirements
- Source code from Stage 3 implementation
- SPEC requirements

**Output:**
- Enhanced `tests/conftest.py` with pytest fixtures
- Mock implementations for external dependencies
- Fixture documentation comments

### Fixture Creation Guidelines

**Create fixtures for:**
- Database connections (in-memory SQLite for tests)
- Mocked external APIs (requests, HTTP calls)
- Test data factories (user, product, transaction objects)
- Authentication tokens (JWT test tokens)
- Configuration overrides (test database URL, API keys)

**Do NOT create:**
- Test assertions (Gemini's job)
- Test class definitions
- Test method implementations
- Edge case test logic

### conftest.py Structure

```python
"""Test fixtures and configuration for pytest.

Provides fixtures for database, authentication, and external dependencies.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models import Base, User


@pytest.fixture
def db_session():
    """Provide in-memory SQLite database for testing.

    Creates fresh database for each test, drops after test completes.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()


@pytest.fixture
def test_user(db_session):
    """Create test user in database.

    Returns User object with id=1, email='test@example.com'
    """
    user = User(
        id=1,
        email="test@example.com",
        password_hash="hashed_password",
        created_at=datetime.utcnow()
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def jwt_token(test_user):
    """Generate valid JWT token for test user.

    Token expires in 1 hour, signed with test secret.
    """
    payload = {
        "sub": test_user.id,
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iat": datetime.utcnow()
    }
    token = jwt.encode(payload, "test_secret", algorithm="HS256")
    return token


@pytest.fixture
def mock_external_api():
    """Mock external API calls.

    Returns Mock object configured to respond to common API calls.
    """
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"success": True}
        yield mock_post
```

### Fixture Naming Convention

- Start with fixture purpose: `db_`, `jwt_`, `mock_`, `test_`
- Examples: `db_session`, `jwt_token`, `mock_payment_api`, `test_user`

### External Dependency Mocking

Mock external services to prevent test dependencies:

```python
@pytest.fixture
def mock_stripe():
    """Mock Stripe payment API."""
    with patch("stripe.Charge.create") as mock:
        mock.return_value = {
            "id": "ch_test_123",
            "amount": 1000,
            "status": "succeeded"
        }
        yield mock
```

### Scope Management

- Use `scope="function"` (default) for fixtures that reset per test
- Use `scope="session"` for expensive operations (database startup)
- Use `scope="module"` for fixtures shared across module tests

---

## Skill 5: Self-Review Reporter

**Active in:** End of Stage 3

**Input:**
- Git commits from Stage 3
- Modified source files
- Test execution results

**Output:**
- `.orchestra/reports/{task_id}.codex.json` structured report
- Self-scoring against implementation criteria

### Report Structure

```json
{
  "agent_id": "codex",
  "task_id": "TASK-001",
  "timestamp": "2026-03-14T14:30:00Z",
  "score": 88,
  "confidence": 0.85,
  "vote": "ready",
  "blockers": [],
  "evidence": [
    {
      "source": "src/auth/jwt.py",
      "finding": "All functions have type hints and docstrings",
      "severity": "info",
      "line_numbers": [1, 50]
    },
    {
      "source": "git log main...feat/TASK-001",
      "finding": "5 conventional commits, each with task_id reference",
      "severity": "info",
      "line_numbers": []
    }
  ],
  "metrics": {
    "files_modified": 3,
    "lines_added": 142,
    "lines_removed": 8,
    "commits": 5,
    "test_execution_time_seconds": 2.3,
    "type_coverage": 1.0,
    "docstring_coverage": 1.0
  }
}
```

### Self-Scoring Guide

**Score Calculation (0-100):**

Base score: 100

Deductions:
- Missing type hints: -5 per function
- Missing docstrings: -3 per public function
- Functions >50 lines: -5 per function
- Circular dependencies: -20
- Pre-commit checks failed: -15
- Test failures: -25
- Unconventional commits: -10

**Example:** 100 - 5 (2 functions missing hints) - 3 (1 missing docstring) = 92

**Confidence (0.0-1.0):**
- 1.0: All acceptance criteria met, all tests pass
- 0.9: All criteria met, 1-2 test warnings
- 0.8: Minor criteria gaps, edge cases untested
- 0.7: Some criteria gaps, requires rework
- <0.7: Major issues, implementation incomplete

### Metrics Collection

```bash
# Get modification statistics
git diff main...feat/{task_id} --stat

# Count commits
git log --oneline main...feat/{task_id} | wc -l

# Run test with timing
pytest tests/ --durations=0

# Check type coverage (if using mypy)
mypy src/ --json > coverage.json
```

---

## Integration Points

**Upstream:** Receives PLAN-{id}.md from Claude (Stage 2), test fixtures plan from Gemini
**Downstream:** Provides code for Claude review (Stage 4), branch for Gemini testing
**Parallel:** Coordinates with Gemini on fixture implementation

---

## Success Criteria

- All acceptance criteria implemented and tested
- Type hints on 100% of functions
- Docstrings on 100% of public APIs
- Functions under 50 lines average
- Conventional commits with task_id references
- All pre-commit checks pass (ruff, pytest, mypy)
- Code review score >=80 from Claude
- Test execution <5 seconds for full suite

---

**Version:** 1.0.0
**Updated:** 2026-03-14
**Maintained by:** MoAI Orchestration Team
