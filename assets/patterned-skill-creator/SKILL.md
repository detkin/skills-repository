---
name: patterned-skill-creator
description: This skill should be used when creating project-specific skills. Guides through a validation-driven workflow including initialization, validation against real codebase patterns, user approval, and best practices review to create actionable skills.
---

# Patterned Skill Creator

## Overview

Create project-specific skills using a validation-driven workflow that ensures skills are actionable and based on real codebase patterns, not generic documentation.

## When to Use This Skill

Use when the user requests:
- "Create a skill for X"
- "Make a skill to help with Y"
- "I want a skill that guides Z"

## Skill Creation Workflow

Follow these phases in order to create an effective, validated skill.

### Phase 0: Gather Requirements and Initial Examples

Collect requirements and initial examples to build the skill from.

Ask users:
1. **Purpose:** "What should this skill help with?"
2. **Usage examples:** "Can you give examples of how you'd use this?"
3. **Trigger conditions:** "What would you say to trigger this skill?"
4. **Initial code examples:** "Please provide 2-3 directories or code areas that represent this domain well."

**Examples should be diverse:**
- For testing skill: Different types of tests (integration, unit, async)
- For API skill: Different provider implementations
- For domain skill: Different modules in that domain

**Avoid overwhelming users** - Ask 2-3 questions at a time.

Conclude when you have: purpose, usage examples, and 2-3 initial code areas to analyze.

### Phase 1: Analyze Examples and Create Initial Skill

**Skip initialization if updating an existing skill (go straight to analysis).**

1. **Analyze initial code examples from Phase 0**

   Examine the 2-3 code areas provided to identify patterns:
   - What patterns are consistent across examples?
   - What utilities or helpers are commonly used?
   - What workflows do developers follow?
   - What common mistakes appear?

   For each pattern, consider:
   - How would I execute this from scratch?
   - What would help when doing this repeatedly?

   **Decision framework:**
   - Patterns documented in code → Document in `references/`
   - Same code rewritten each time → Store in `scripts/`
   - Same boilerplate files each time → Store in `assets/`

   **For codifying codebase patterns, most skills need only `references/`.**

2. **Initialize skill structure**

   Use the bundled init script:
   ```bash
   python .claude/skills/patterned-skill-creator/scripts/init_skill.py <skill-name> --path .claude/skills
   ```

   **Delete unused example files** - The init script creates examples to demonstrate structure. Delete what you don't need.

3. **Create initial SKILL.md based on analyzed patterns**

   Include:
   - Clear description (when to use this skill)
   - Basic workflow or quick start
   - Common patterns found in initial examples
   - Pointers to reference files

   **Keep it concise**: Aim for <5k words. Move details to references.

### Phase 2: Validate Against Different Code Areas (CRITICAL)

**Now validate the skill against DIFFERENT code areas than Phase 0 to catch gaps.**

1. **Ask user for NEW validation targets**

   **IMPORTANT:** Ask for 2-3 DIFFERENT code areas than the ones used in Phase 0.

   Ask: "I've created the initial skill based on [list Phase 0 examples]. To validate it comprehensively, please provide 2-3 DIFFERENT directories or code areas to check against."

   **Why different areas:**
   - Catches patterns missed in initial examples
   - Ensures comprehensive coverage
   - Validates skill works across diverse scenarios

2. **Launch validation subagent for each target**

   For EACH target directory from step 1, use Task tool with `subagent_type="Explore"`:

   ```
   Validate the <skill-name> skill against real code in <target-directory>.

   Read the skill:
   - .claude/skills/<skill-name>/SKILL.md
   - All files in .claude/skills/<skill-name>/references/

   Analyze code files in <target-directory> to identify:
   1. Patterns NOT documented in the skill
   2. Examples where skill documentation doesn't match real usage
   3. Directory/file organization patterns
   4. Common imports, utilities, or helpers
   5. Async patterns or other paradigm-specific patterns

   Output format:
   - Currently Documented: Brief summary
   - New Patterns Found: Detailed list with code examples and file paths
   - Recommendations: Prioritized as P1 (Critical), P2 (High Value), P3 (Nice to Have)
     with rationale for each priority level
   ```

3. **Review all findings with user**

   After all validation subagents complete, consolidate findings and present prioritized recommendations. Ask: "Which priorities should I add to the skill?"

4. **Implement approved additions**
   - Update SKILL.md with high-level patterns
   - Add detailed examples to references/*.md
   - Use real code examples with file paths from validation

### Phase 3: Review Against Best Practices

**Ensure skill is actionable, not just reference documentation.**

1. **Launch best practices review subagent**

   Use Task tool with `subagent_type="general-purpose"`:

   ```
   Review the <skill-name> skill against skill creation best practices.

   Read the skill files: .claude/skills/<skill-name>/SKILL.md and all references/*.md

   Evaluate against:
   - Actionable vs Reference: Does it tell what to DO? Does it have workflow steps?
   - Project-Specific vs Generic: Uses real codebase patterns or generic advice?
   - Conciseness: Dense and skimmable?
   - Code-First: Quick reference code snippets?
   - Progressive Disclosure: SKILL.md concise (<5k words), references for depth?

   Provide detailed report:
   - Strengths: What the skill does well
   - Weaknesses: Specific problems with quoted examples
   - Specific Examples: Quote sections that are problematic
   - Recommendations: Concrete suggestions with before/after examples
   - Rewrite Examples: Show 2-3 sections with before/after

   Focus on making it something an agent will USE while working, not just read once.
   ```

2. **Review findings with user**

   Present key problems and recommendations. Ask: "Should I implement these improvements?"

3. **Implement improvements**

   Common improvements:
   - Add workflow section ("What do I do first?")
   - Replace generic examples with real codebase patterns
   - Add "Examples to copy" pointing to actual files
   - Add troubleshooting workflows with specific commands
   - Make reference files project-specific, not tutorials

### Phase 4: Validate and Package

1. **Validate the skill**

   Always validate before finalizing:
   ```bash
   python .claude/skills/patterned-skill-creator/scripts/quick_validate.py .claude/skills/<skill-name>
   ```

   This validates:
   - YAML frontmatter format
   - Required fields present
   - File organization
   - Description quality
   - Word count limits (<5k for SKILL.md, <10k for references)

   Fix any errors or warnings reported.

2. **Ask about packaging**

   If the skill is in `.claude/skills/` directory, it's already usable locally.

   **Ask user:** "Should I create a distributable .zip package of this skill?"

   Reasons to package:
   - Sharing with other projects
   - Distributing to team members
   - Uploading to skill marketplace
   - Backup/version control

   Reasons to skip:
   - Skill is project-specific, staying in this repo
   - Local use only

3. **Package the skill (if approved)**

   ```bash
   python .claude/skills/patterned-skill-creator/scripts/package_skill.py .claude/skills/<skill-name>
   ```

   Note: This script runs validation again before packaging.

4. **Summarize for user**

   Provide concise summary:
   - Location: `.claude/skills/<skill-name>/`
   - Packaged: `<skill-name>.zip` (if created)
   - Contents: Brief overview of what's included
   - Trigger: When the skill will activate

### Phase 5: Iterate Based on Real Usage

After the skill is deployed and used on real tasks:

1. **Observe skill performance**
   - Use the skill on actual tasks
   - Notice where it struggles or falls short
   - Identify missing patterns or unclear guidance

2. **Gather feedback**
   - Users often request improvements right after using the skill
   - Fresh context from real usage reveals gaps

3. **Update and refine**
   - Add missing patterns discovered during usage
   - Clarify confusing sections
   - Add troubleshooting for errors encountered
   - Update examples based on real scenarios

4. **Revalidate and repackage**
   - Run validation to ensure quality
   - Package updated skill

Skills are living documents - iteration based on real usage is essential for quality.

## Key Principles

### 1. Validation-Driven Development

**Always validate against real code.** Skills based on assumptions fail when used.

**Two-stage approach:**
- **Phase 0:** Gather 2-3 initial examples → Build skill from them
- **Phase 2:** Gather 2-3 DIFFERENT examples → Validate and find gaps

**Example:** Creating a testing skill?
- Phase 0: Build from `tests/integration/`, `tests/unit/`
- Phase 2: Validate against `tests/services/`, `tests/models/` → Find 10 missing patterns
- Result: Comprehensive coverage from diverse areas

### 2. User-Approved Additions

**Never add everything found.** Present prioritized findings and get approval.

### 3. Actionable Over Reference

**Skills are workflows, not documentation.**

**Bad:** "Use factories for test data"

**Good:** "Before creating a factory, check these 3 locations: 1. app/tests/factories.py, 2. organization/tests/factories.py..."

### 4. Progressive Disclosure

**Keep SKILL.md concise (<5k words).**
- Overview and workflow
- Common patterns
- Pointers to references

**Move details to references (<10k words each):**
- Advanced patterns
- Edge cases
- Long examples

**CRITICAL: Avoid duplication** - Information should live in EITHER SKILL.md OR references, NOT BOTH. Prefer references for detailed information unless truly core to the skill. This keeps SKILL.md lean while maintaining discoverability.

**For large references (>10k words):** Include grep search patterns in SKILL.md to help find relevant sections without reading the entire file.

**Progressive disclosure levels:**
1. **Metadata** (~100 words) - Always loaded
2. **SKILL.md** (<5k words) - Loaded when skill triggers
3. **References** (<10k words each) - Loaded as needed
4. **Scripts** (unlimited*) - Executed WITHOUT loading into context

*Scripts can be executed without reading into context window, making them token-efficient for repeated code.

### 5. Project-Specific Patterns

**Use real codebase examples with file paths.**

Avoid generic examples. Always point to actual files and line numbers.

### 6. Writing Style

**Use imperative/infinitive form:**

**Good:** "Check existing factories before creating new ones"
**Bad:** "You should check existing factories"

## Bundled Scripts

This skill includes two utility scripts in the `scripts/` directory:

- **init_skill.py** - Initialize new skill directory structure with templates
- **package_skill.py** - Validate and package skills into distributable .zip files

Both scripts are self-contained and can be executed directly.

## Advanced Topics

See reference files for comprehensive guidance:
- `references/validation_workflow.md` - Detailed validation process with complete examples
- `references/best_practices_checklist.md` - Comprehensive review checklist
