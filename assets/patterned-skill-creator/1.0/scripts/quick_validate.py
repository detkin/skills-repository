#!/usr/bin/env python3
"""
Quick validation script for skills - minimal version
"""

import os
import re
import sys
from pathlib import Path


def count_words(text):
    """Count words in markdown text (excluding frontmatter and code blocks)"""
    # Remove frontmatter
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL)
    # Remove code blocks
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    # Count words
    words = text.split()
    return len(words)


def validate_skill(skill_path):
    """Basic validation of a skill"""
    skill_path = Path(skill_path)
    warnings = []

    # Check SKILL.md exists
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return False, "SKILL.md not found", warnings

    # Read and validate frontmatter
    content = skill_md.read_text()
    if not content.startswith("---"):
        return False, "No YAML frontmatter found", warnings

    # Extract frontmatter
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format", warnings

    frontmatter = match.group(1)

    # Check required fields
    if "name:" not in frontmatter:
        return False, "Missing 'name' in frontmatter", warnings
    if "description:" not in frontmatter:
        return False, "Missing 'description' in frontmatter", warnings

    # Extract name for validation
    name_match = re.search(r"name:\s*(.+)", frontmatter)
    if name_match:
        name = name_match.group(1).strip()
        # Check naming convention (hyphen-case: lowercase with hyphens)
        if not re.match(r"^[a-z0-9-]+$", name):
            return (
                False,
                f"Name '{name}' should be hyphen-case (lowercase letters, digits, and hyphens only)",
                warnings,
            )
        if name.startswith("-") or name.endswith("-") or "--" in name:
            return False, f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens", warnings

    # Extract and validate description
    desc_match = re.search(r"description:\s*(.+)", frontmatter)
    if desc_match:
        description = desc_match.group(1).strip()
        # Check for angle brackets
        if "<" in description or ">" in description:
            return False, "Description cannot contain angle brackets (< or >)", warnings

    # Validate SKILL.md word count
    skill_word_count = count_words(content)
    if skill_word_count > 5000:
        return False, f"SKILL.md has {skill_word_count} words (should be <5000 words)", warnings
    elif skill_word_count > 4500:
        warnings.append(f"Warning: SKILL.md has {skill_word_count} words, approaching 5k limit")

    # Validate reference files word count
    references_dir = skill_path / "references"
    if references_dir.exists():
        for ref_file in references_dir.glob("*.md"):
            ref_content = ref_file.read_text()
            ref_word_count = count_words(ref_content)
            if ref_word_count > 10000:
                return False, f"{ref_file.name} has {ref_word_count} words (should be <10k words)", warnings
            elif ref_word_count > 9000:
                warnings.append(f"Warning: {ref_file.name} has {ref_word_count} words, approaching 10k limit")

    return True, "Skill is valid!", warnings


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python quick_validate.py <skill_directory>")
        sys.exit(1)

    valid, message, warnings = validate_skill(sys.argv[1])

    # Print warnings first
    for warning in warnings:
        print(warning)

    # Print validation result
    print(message)
    sys.exit(0 if valid else 1)
