# CLAUDE.md Coding Standards

**Source**: `CLAUDE.md`

This reference highlights key patterns. Read the full CLAUDE.md file for complete details.

## Most Important Rules

**Type hints:**
- Use modern syntax: `Foo | None` instead of `Optional[Foo]`
- Use lowercase: `list[str]` instead of `List[str]`

**Function design:**
- Functions >5 args must use keyword-only (add `*` separator)
- `org_id` always first in argument list if present
- Keep functions <100 lines, modules <400 lines

**Data structures:**
- Avoid `dict` for passing data (use dataclasses instead)
- Exception: dicts OK for serialization only

**Database queries:**
- Every query must filter by `org_id`

**Imports:**
- Absolute imports only (never relative)
- Keep at top of file

For complete details, read `CLAUDE.md`
