---
name: coding-standards
description: Use when writing Python code, reviewing code, refactoring, or doing PR reviews to ensure code follows project linting rules and CLAUDE.md standards. Prevents suggesting style changes that violate configured rules.
---

# Coding Standards
``
## Overview

This skill codifies the project's linting configuration and coding standards from CLAUDE.md. Use it to ensure code adheres to project-specific rules and avoid suggesting style changes that violate configured linting rules.

## When to Use This Skill

**Always use when:**
- Writing new Python code
- Reviewing code or PRs
- Refactoring existing code
- Suggesting code improvements

**Key principle:** Do NOT suggest style changes that are already handled by automated formatters or violate configured linting rules. Focus on logic, security, performance, and architecture issues.

## Critical Linting Rules

### Absolute Imports Only (ruff TID252)
**All imports must be absolute, never relative**

```python
# ✅ Correct - absolute import
from sleuth.apps.issues.models import Issue

# ❌ Wrong - parent relative import (banned by TID252)
from ..models import Issue

# ⚠️ Note: Same-directory relative imports (from .models) are not banned by TID252
# but violate CLAUDE.md standards and should be avoided
```

### Single-Line Imports (ruff)
**Most important rule:** Each import MUST be on its own line (`force-single-line = true`)

```python
# ✅ Correct
from foo import bar
from foo import baz

# ❌ Wrong - violates ruff configuration
from foo import bar, baz
```

### Line Length
**All tools configured to 118 characters**

### Import Organization (ruff)
After imports, add 2 blank lines before code:
```python
from sleuth.apps.organization import Organization
from sleuth.apps.remote import Remote


def my_function():  # 2 blank lines after imports
    pass
```

### Enabled Ruff Rule Sets

**Ruff extends select** (see ruff.toml):
- `I`: isort (import sorting)
- `B`: flake8-bugbear (likely bugs and design problems)
- `SIM`: flake8-simplify (simplification suggestions)
- `TID252`: ban parent relative imports
- `C90`: mccabe complexity checks
- `PL`: pylint rules
- `PIE`: flake8-pie (unnecessary code patterns)
- `A`: flake8-builtins (shadowing built-in names)

**Complexity limits** (ruff.toml):
- `max-args = 20`
- `max-branches = 20`
- `max-returns = 20`
- `max-statements = 50`
- `max-complexity = 20`

### Intentionally Ignored Rules

**Ruff ignores these** (see ruff.toml lines 19-32):
- PLC0415, PLR1714, PLR2044, PLW2901: pylint rules
- PLW1641, PLW1508, PLR2004: TODO - should be fixed in code
- B008, B024, B026, B904: bugbear rules - TODO - should be fixed in code
- SIM105, SIM116: simplify rules
- SIM102, SIM108, SIM117, SIM103, SIM113: TODO - should be fixed in code

**Per-file ignores** (ruff.toml):
- Settings files ignore E402 (import violations)
- Test files ignore: PLR0915, PLR2004, F811, A002, B, S
- Vendor code ignores ALL rules

## CLAUDE.md Standards Summary

See `references/claude_md_standards.md` for complete details.

**Quick reference:**
- Absolute imports only (never relative)
- Type hints required (use `Foo | None` not `Optional[Foo]`)
- Functions >5 args → keyword-only
- Functions <100 lines, modules <400 lines
- `org_id` always first in argument lists
- Avoid `dict` for data passing (use dataclasses)
- Every DB query must filter by org

## Linting Commands

**After making code changes:**
```bash
make format              # Run frequently - auto-fixes formatting and imports (fast)
```

**Before finalizing work:**
```bash
make check-types         # Validates type hints (expensive)
make lint-py             # Checks code quality (expensive)
```

## Code Review Focus

1. **Check architecture** - SOLID principles, function/module size
2. **Check security** - SQL injection, XSS, command injection
3. **Check logic** - correctness, error handling, edge cases
4. **Check performance** - N+1 queries, inefficient algorithms
5. **Skip style suggestions** - formatters handle this automatically

## Resources

### references/
- `claude_md_standards.md` - Complete CLAUDE.md coding standards
- `linting_config_details.md` - Detailed explanation of all linting rules
