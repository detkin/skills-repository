# Linting Configuration Details

**Source**: `ruff.toml`

This reference highlights key rules. Query ruff.toml directly for complete details.

## Critical Rules

**Ruff Configuration (ruff.toml):**
- `line-length = 118` - Maximum line length
- `target-version = "py312"` - Python 3.12 target

**Import Rules (ruff.toml [lint.isort]):**
- `TID252` - Ban parent relative imports (e.g., `from ..module import foo`)
- `force-single-line = true` - Each import MUST be on separate line
- `lines-after-imports = 2` - Two blank lines after imports
- `case-sensitive = false` - Case-insensitive import sorting
- `order-by-type = true` - Order imports by type

**Enabled Rule Sets (ruff.toml [lint]):**
- `I`: isort (import sorting)
- `B`: flake8-bugbear (likely bugs and design problems)
- `SIM`: flake8-simplify (simplification suggestions)
- `TID252`: ban parent relative imports
- `C90`: mccabe complexity checks
- `PL`: pylint rules
- `PIE`: flake8-pie (unnecessary code patterns)
- `A`: flake8-builtins (shadowing built-in names)

**Complexity Limits (ruff.toml [lint.pylint]):**
- `max-args = 20` - Maximum function arguments
- `max-branches = 20` - Maximum branches in function
- `max-returns = 20` - Maximum return statements
- `max-statements = 50` - Maximum statements in function

**McCabe Complexity (ruff.toml [lint.mccabe]):**
- `max-complexity = 20` - Maximum cyclomatic complexity

## Intentionally Ignored Rules

**Global Ignores (ruff.toml [lint.ignore]):**
- PLC0415, PLR1714, PLR2044, PLW2901: pylint rules
- PLW1641, PLW1508, PLR2004: TODO - should be fixed in code
- B008, B024, B026, B904: bugbear rules - TODO - should be fixed in code
- SIM105, SIM116: simplify rules
- SIM102, SIM108, SIM117, SIM103, SIM113: TODO - should be fixed in code

**Per-File Ignores (ruff.toml [lint.per-file-ignores]):**
- `sleuth/settings/*.py`: E402 (import violations in settings)
- `sleuth/conftest.py`: E402 (import violations)
- Test files (`*/tests/*`): PLR0915, PLR2004, F811, A002, B, S
- Vendor code: ALL rules ignored

## Key Insight

The project uses ruff exclusively for linting. Many rules are intentionally ignored (see ruff.toml lines 19-32). Before suggesting style changes, verify the rule is enabled in ruff.toml.

Common ignored patterns:
- Specific pylint complexity rules (PLW, PLR)
- Some bugbear rules (B008, B024, B026, B904)
- Specific simplify rules (SIM102, SIM103, etc.)
- Security rules in tests (S)

For the complete list, read ruff.toml [lint.ignore] and [lint.per-file-ignores] sections.
