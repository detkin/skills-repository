# Best Practices Checklist

## Overview

Use this checklist to evaluate skills against best practices. This ensures skills are actionable, not just reference documentation.

## Evaluation Criteria

### 1. Actionable vs. Reference

**Question:** Does the skill tell the agent what to DO, or just explain concepts?

**Good signs:**
- Has "Workflow" or "Quick Start" section with numbered steps
- Starts with "What do I do first?"
- Includes specific commands to run
- Shows step-by-step process

**Bad signs:**
- Only explains concepts
- No clear entry point
- Says "you can" or "it's possible to" without showing how
- Reads like a tutorial, not a playbook

**Example - Bad:**
```markdown
Use factories for test data. Factories help create test objects.
```

**Example - Good:**
```markdown
## Test Writing Workflow

1. Find similar tests to copy
   Look at tests/<module>/test_<feature>.py

2. Identify required factories
   Check tests/factories.py

3. Run tests
   pytest tests/<module>/test_<feature>.py
```

### 2. Project-Specific vs. Generic

**Question:** Does it use real codebase patterns, or generic advice that could apply anywhere?

**Good signs:**
- Points to actual files with paths
- Shows real code from the project
- References project-specific utilities/helpers
- Includes file locations and line numbers

**Bad signs:**
- Generic examples that could be from any project
- No file paths or specific references
- Reads like a framework tutorial
- No mention of project conventions

**Example - Bad:**
```python
class UserFactory(Factory):
    name = "Test User"
```

**Example - Good:**
```python
From tests/factories.py:18-26:

class UserFactory(AsyncModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
```

### 3. Conciseness

**Question:** Is the SKILL.md dense and skimmable, or verbose with explanations?

**Good signs:**
- SKILL.md under 5k words
- Details moved to reference files
- Quick reference format
- Bullet points over paragraphs
- Code snippets over explanations

**Bad signs:**
- SKILL.md over 5k words
- Everything in one file
- Long explanatory paragraphs
- Detailed examples in main file

**Fix:** Move details to `references/*.md` files (each under 10k words)

### 4. Code-First

**Question:** Are there quick reference code snippets, or walls of text?

**Good signs:**
- Code examples in every section
- Examples show complete, runnable code
- Minimal explanation, maximum code
- "From <file>:<lines>" citations

**Bad signs:**
- Long paragraphs explaining what to do
- Code examples are incomplete
- More text than code
- No file references

### 5. Progressive Disclosure

**Question:** Is SKILL.md concise with references for depth?

**Three levels should be:**
1. **Metadata** (~100 words) - Name, description, when to use
2. **SKILL.md** (<5k words) - Overview, workflow, common patterns, pointers
3. **References** (<10k words each) - Advanced patterns, detailed examples, edge cases

**Check:**
- [ ] SKILL.md focuses on workflow and common patterns
- [ ] Detailed patterns moved to references/
- [ ] SKILL.md points to reference files
- [ ] No duplication between SKILL.md and references
- [ ] Reference files each under 10k words

### 6. Writing Style

**Question:** Uses imperative/infinitive form (verb-first), not second person?

**Good examples:**
- "Check existing factories before creating new ones"
- "Run tests with --reuse-db flag"
- "Use async methods in async contexts"

**Bad examples:**
- "You should check existing factories"
- "You can run tests with the --reuse-db flag"
- "If you need to test async code, you should use..."

## Comprehensive Review Checklist

### Structure

- [ ] Has clear "When to Use This Skill" section
- [ ] Includes workflow or quick start section
- [ ] Common patterns section with examples
- [ ] Troubleshooting section (if applicable)
- [ ] Points to reference files for advanced topics
- [ ] SKILL.md under 5k words

### Content Quality

- [ ] Uses real code examples from the project
- [ ] Includes file paths and line numbers
- [ ] Shows "Examples to copy" with actual files
- [ ] Troubleshooting includes specific commands
- [ ] All code examples are complete and runnable

### Writing Style

- [ ] Uses imperative/infinitive form throughout
- [ ] Objective, instructional language
- [ ] No second person ("you")
- [ ] Code-first approach
- [ ] Concise, dense content

### References

- [ ] Advanced patterns in reference files
- [ ] No duplication with SKILL.md
- [ ] Reference files under 10k words each
- [ ] Each reference covers one topic thoroughly

### Metadata

- [ ] Name is clear and descriptive
- [ ] Description includes trigger conditions
- [ ] Description uses third-person
- [ ] Description is specific, not generic

## Common Problems and Fixes

### Problem 1: Missing Workflow Section

**Symptom:** Skill explains concepts but doesn't show where to start

**Fix:** Add "Quick Start Workflow" or "Process" section at the top with numbered steps

**Template:**
```markdown
## Quick Start Workflow

When <doing task>:

1. **First step**
   - Check X
   - Look at Y

2. **Second step**
   - Run command Z
   - Verify output

3. **Third step**
   - Do final action
```

### Problem 2: Generic Examples

**Symptom:** Examples could apply to any project

**Fix:** Search codebase for actual usage, replace with real examples

**Before:**
```python
def test_example():
    obj = Factory()
    assert obj.name is not None
```

**After:**
```python
From tests/integration/test_api.py:45-48:

def test_api_client_success():
    client = ClientFactory()
    response = client.fetch_data()
    assert response.status_code == 200
```

### Problem 3: No Troubleshooting

**Symptom:** Skill doesn't help when things go wrong

**Fix:** Add troubleshooting section with common errors and solutions

**Template:**
```markdown
## Troubleshooting

### Error X

**Symptom:** [What the user sees]

**Solution:**
1. Check [specific thing]
2. Run [specific command]
3. Verify [expected outcome]

### Error Y

[Similar structure]
```

### Problem 4: Too Long

**Symptom:** SKILL.md over 5k words, hard to skim

**Fix:** Move details to reference files

**Keep in SKILL.md:**
- Overview
- Workflow
- Common patterns (brief)
- Pointers to references

**Move to references:**
- Advanced patterns
- Detailed explanations
- Edge cases
- Long examples

### Problem 5: No Real File References

**Symptom:** Examples don't point to actual code

**Fix:** Add file paths and line numbers to all examples

**Format:**
```markdown
From <path>/<to>/<file>:<start-line>-<end-line>:

```<language>
[actual code from file]
```

See also:
- <path>/<to>/<related-file>
- <path>/<to>/<another-file>
```

## Review Process

### Step 1: Read SKILL.md

- [ ] Can you immediately tell what the skill does?
- [ ] Is there a clear entry point (workflow/quick start)?
- [ ] Are there code examples in each section?
- [ ] Does it point to real files in the project?

### Step 2: Check Examples

- [ ] Are examples from the actual project?
- [ ] Do examples include file paths?
- [ ] Are examples complete and runnable?
- [ ] Do examples show actual patterns from the code?

### Step 3: Evaluate Structure

- [ ] Is SKILL.md concise (<5k words)?
- [ ] Are details in reference files?
- [ ] Is there clear progressive disclosure?
- [ ] No duplication between files?

### Step 4: Test Actionability

Imagine you're an agent seeing this skill for the first time:

- [ ] Can you tell what to do first?
- [ ] Are the steps clear and specific?
- [ ] Can you find actual code to copy?
- [ ] Are commands provided where needed?

If any answer is "no", the skill needs improvement.

## Before/After Examples

### Example 1: Adding Workflow

**Before:**
```markdown
# Test Writer

Use pytest for tests. Tests should be in tests/ directory.
```

**After:**
```markdown
# Test Writer

## Test Writing Workflow

1. **Find similar tests**
   Look at tests/<module>/test_<feature>.py

2. **Copy structure**
   Use function-style tests

3. **Run tests**
   pytest tests/<module>/

4. **Validate**
   make check-types
```

### Example 2: Making Project-Specific

**Before:**
```markdown
Use factories for test data:

```python
obj = Factory()
```
```

**After:**
```markdown
Before creating a factory, check:
1. tests/factories.py
2. tests/fixtures/factories.py

From tests/factories.py:23-30:

```python
class EntityFactory(AsyncFactory):
    name = factory.Faker("company")
    slug = factory.LazyAttribute(lambda o: slugify(o.name))
```
```

### Example 3: Adding Troubleshooting

**Before:**
```markdown
Run tests with pytest.
```

**After:**
```markdown
## Running Tests

```bash
pytest tests/<module>/
```

## Troubleshooting

### Test Fails with "Module not found"

1. Check test file location:
   ```bash
   ls tests/<module>/test_<feature>.py
   ```

2. Verify imports use correct paths

3. Run from project root:
   ```bash
   cd <project-root> && pytest tests/
   ```
```

## Final Checklist

Before considering the skill complete:

- [ ] Validated against real code (Phase 2 complete)
- [ ] Best practices review complete (Phase 3 complete)
- [ ] All "Good signs" present, "Bad signs" fixed
- [ ] SKILL.md under 5k words
- [ ] All examples include file paths
- [ ] Troubleshooting section added
- [ ] Reference files created for advanced topics
- [ ] Tested by imagining you're an agent using it

If all boxes checked, skill is ready to package!
