# Linting Configuration Details

**Sources**: `.pylintrc`, `.flake8`, `pyproject.toml`, `ruff.toml`

This reference highlights key rules. Query the source files directly for complete details.

## Critical Rules

**Ruff (ruff.toml):**
- `TID252` - Ban parent relative imports (e.g., `from ..module import foo`)
- `force-single-line = true` - Each import MUST be on separate line
- `lines-after-imports = 2` - Two blank lines after imports
- `line-length = 118`

**Pylint (.pylintrc):**
- `max-line-length = 118`
- `max-args = 20`, `max-positional-arguments = 8`
- **Extensive disabled checks** (lines 48-126) - Do NOT suggest changes for disabled rules

**Flake8 (.flake8):**
- Ignores: E203, E231, E402, F541, E731, E741, F811, E201, E202
- Most are whitespace rules that conflict with black

## Key Insight

Many style rules are intentionally disabled. Before suggesting style changes, check if the rule is disabled in `.pylintrc` lines 48-126.

Common disabled rules:
- Import ordering (wrong-import-order, ungrouped-imports)
- Else branches (no-else-return, no-else-raise)
- Complexity metrics (too-many-locals, too-many-instance-attributes)
- Documentation (missing-docstring)

For complete disabled list, read `.pylintrc` lines 48-126.
