# Validation Workflow Details

## Overview

This reference provides detailed guidance for Phase 2 validation. See SKILL.md for the overall process.

## Formatting Findings for User

After validation subagents complete, organize findings using this template:

```markdown
## Validation Results for <skill-name>

Analyzed: <target-directory-1>, <target-directory-2>

### Currently Documented
- Pattern A
- Pattern B
- Pattern C

### Priority 1: CRITICAL (Must Add)
1. **Pattern X** - Found in 15 files
   Rationale: Core to workflow, used everywhere
   Example: path/to/file.ext:123-135

2. **Pattern Y** - Found in 10 files
   Rationale: Essential for core operations
   Example: path/to/file.ext:45-60

### Priority 2: HIGH VALUE (Should Add)
3. **Pattern Z** - Found in 5 files
   Rationale: Common utility, saves significant time
   Example: path/to/file.ext:78-90

### Priority 3: NICE TO HAVE (Consider Adding)
4. **Pattern W** - Found in 2 files
   Rationale: Edge case, adds completeness
   Example: path/to/file.ext:200-210

**Which priorities should I add to the skill?**
```

**Key elements:**
- List all directories analyzed
- Group by priority with clear rationale
- Include file counts (shows importance)
- Provide specific file paths for examples
- End with clear question for user approval

## Implementing Approved Patterns

For each pattern the user approves, follow this structure:

### Update SKILL.md (High-Level Only)

Add brief mention with pointer to reference:

```markdown
### Pattern Name

[One sentence description]

[Brief code example - 3-5 lines max]

See `references/<topic>.md` for details.
```

**Keep it minimal** - Just enough to know the pattern exists and where to find details.

### Create/Update Reference File (Detailed)

Structure each pattern with:

1. **Pattern name** (## heading)
2. **Brief explanation** (1-2 sentences)
3. **Real code example** with file path:
   ```markdown
   From path/to/file.ext:45-60:

   ```language
   [actual code from codebase]
   ```
   ```
4. **When to use**
5. **Related patterns** (if applicable)

**Example:**

```markdown
# Async Testing Patterns

## Pattern: Async Factory Methods

Use async factory methods in async test contexts.

From tests/integration/test_service.py:24-26:

```python
entity = await EntityFactory.acreate()
related = await RelatedFactory.acreate(entity=entity)
```

**When to use:** Any async test function marked with @pytest.mark.asyncio

**Related patterns:** See "Async Fixtures" below

## Pattern: Async Fixtures

[Similar structure]
```

## Common Validation Findings by Priority

### High-Priority Patterns (Usually P1)

These typically warrant P1 (Critical) priority:
- Core workflows (how to start, basic operations)
- Essential utilities (commonly used helpers in 10+ files)
- Organization patterns (file structure, naming conventions)
- Common mistakes to avoid

### Medium-Priority Patterns (Usually P2)

These typically warrant P2 (High Value) priority:
- Advanced patterns (performance optimizations)
- Convenience utilities (used in 3-9 files)
- Alternative approaches
- Domain-specific patterns

### Low-Priority Patterns (Usually P3)

These typically warrant P3 (Nice to Have) priority:
- Edge cases (1-2 files)
- Rarely-used features
- Deprecated patterns still in code
- Legacy approaches being phased out

## Consolidating Findings from Multiple Directories

When validating against multiple directories:

1. **Review each subagent report separately**
2. **Identify overlapping patterns** - If same pattern found in multiple areas, increase priority
3. **Note unique patterns** - Patterns specific to one area may be lower priority
4. **Merge recommendations** - Combine similar patterns, deduplicate

**Example consolidation:**

From directory A:
- Pattern X (found in 8 files)

From directory B:
- Pattern X (found in 7 files)

Consolidated:
- Pattern X - Found in 15 files across both areas → Likely P1

## Troubleshooting Validation

### Subagent Returns Too Many Findings

**Problem:** 30+ patterns identified, overwhelming to review

**Solutions:**
- Filter to patterns used in 3+ files before presenting
- Group similar patterns together
- Focus on consistently used patterns, exclude one-offs
- Ask user to prioritize categories, not individual patterns

### Subagent Misses Known Patterns

**Problem:** You know pattern X exists but subagent didn't find it

**Solutions:**
- Check if pattern actually exists in target directories
- Try different target directory where pattern is more prevalent
- Manually add the pattern with examples from your knowledge
- Adjust subagent prompt to be more specific about what to look for

### Patterns Don't Match Skill Scope

**Problem:** Subagent finds patterns outside the skill's intended domain

**Solutions:**
- Refine target directory to be more focused
- Update subagent prompt with clearer scope boundaries
- Filter findings before presenting to user
- Consider if skill scope should be expanded

### Validation Reveals Skill Scope Too Narrow

**Problem:** Validation finds many important patterns not covered by initial skill scope

**Solutions:**
- Discuss with user if skill scope should expand
- Consider creating multiple focused skills instead of one broad skill
- Update skill description to match actual scope

## Validation Checklist

Before moving to Phase 3, verify:

- [ ] Validated against 2-3 DIFFERENT directories than Phase 0 examples
- [ ] Consolidated findings from all validation runs
- [ ] Organized findings by priority (P1/P2/P3)
- [ ] Reviewed ALL P1 (Critical) findings with user
- [ ] Got user approval on which priorities to implement
- [ ] Implemented approved patterns
- [ ] Updated SKILL.md with high-level patterns only
- [ ] Created/updated reference files with full details
- [ ] All examples include file paths and line numbers
- [ ] No duplication between SKILL.md and reference files
