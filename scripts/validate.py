#!/usr/bin/env python3
"""Validate every skill in .claude/skills and every agent in .claude/agents.

Checks that each SKILL.md has parseable frontmatter whose `name` matches its
directory, that it carries a description (the description is what makes a skill
trigger), that any file a skill points at actually exists, and that the
frontmatter only asks Claude Code for things it can grant. Agents get the same
frontmatter checks against the fields the sub-agent docs define.

Run with: python3 scripts/validate.py
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".claude" / "skills"
AGENTS = ROOT / ".claude" / "agents"
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# An explicit pointer at a bundled file, e.g. `<skill dir>/scripts/build.py`.
# Anchored on the `<skill dir>/` prefix so paths that merely look similar --
# `docs/assets/custom.css` inside a config example -- are not mistaken for one.
REF_RE = re.compile(r"<skill dir>/([A-Za-z0-9._/-]+)")
# A Markdown link target. Code spans and fences are stripped before this runs,
# so an example path inside backticks is never mistaken for a link.
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
CODE_RE = re.compile(r"```.*?```|`[^`\n]*`", re.S)
# `subagent_type: "checker"` in a spawn instruction names an agent that has to
# exist, either as a file here or as one Claude Code ships.
SPAWN_RE = re.compile(r"subagent_type:\s*\"([A-Za-z0-9_-]+)\"")
BUILTIN_AGENTS = {"general-purpose", "Explore", "Plan"}

# Claude Code's documented limit for a skill description in listings.
DESCRIPTION_MAX = 1536
AGENT_MODELS = {"sonnet", "opus", "haiku", "fable", "inherit"}
EFFORTS = {"low", "medium", "high", "xhigh", "max"}
COLORS = {"red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"}

errors: list[str] = []


def frontmatter(path: pathlib.Path) -> dict[str, str] | None:
    """Extract top-level `key: value` pairs from a Markdown file's frontmatter.

    Deliberately not a YAML parser: only the scalar keys checked here (`name`,
    `description`) need reading, and staying dependency-free means this runs
    anywhere with a bare python3. List values fold into one string with their
    `- ` markers kept, which is enough to test membership.
    """
    text = path.read_text()
    if not text.startswith("---\n"):
        errors.append(f"{path.relative_to(ROOT)}: missing frontmatter")
        return None
    end = text.find("\n---", 4)
    if end == -1:
        errors.append(f"{path.relative_to(ROOT)}: unterminated frontmatter")
        return None

    fields: dict[str, str] = {}
    key = None
    for line in text[4:end].splitlines():
        match = re.match(r"^([a-zA-Z-]+):\s*(.*)$", line)
        if match:
            key = match.group(1)
            fields[key] = match.group(2).strip()
        elif key and line.startswith((" ", "\t")):
            # A folded or indented continuation of the previous scalar, or a
            # list item; comments carry nothing worth keeping.
            fields[key] = f"{fields[key]} {line.split('#', 1)[0].strip()}".strip()
    return fields


def list_items(value: str) -> list[str]:
    """Split a folded YAML list (`- Read - Grep`) or a space/comma string into items."""
    if "- " in value:
        return [item.strip() for item in value.split("- ") if item.strip()]
    return [item for item in re.split(r"[,\s]+", value) if item]


def check_links(path: pathlib.Path) -> None:
    """Every relative Markdown link must resolve, and no Cursor `mdc:` links survive.

    These are the two ways a skill copied out of another repo silently rots:
    a link to a sibling rules file that does not exist here, or a Cursor-flavoured
    link Claude Code does not understand.
    """
    text = path.read_text()
    if "mdc:" in text:
        errors.append(f"{path.relative_to(ROOT)}: contains Cursor 'mdc:' links; use plain Markdown links")
    prose = CODE_RE.sub("", text)
    for target in sorted(set(LINK_RE.findall(prose))):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
            continue
        rel = target.split("#", 1)[0]
        if rel and not (path.parent / rel).exists():
            errors.append(f"{path.relative_to(ROOT)}: link to missing '{target}'")


def check_spawns(path: pathlib.Path, agent_names: set[str]) -> None:
    text = path.read_text()
    for name in sorted(set(SPAWN_RE.findall(text))):
        if name not in agent_names and name not in BUILTIN_AGENTS:
            errors.append(f"{path.relative_to(ROOT)}: spawns unknown agent '{name}' (no .claude/agents/{name}.md)")


agent_files = sorted(AGENTS.glob("*.md"))
agent_names = {agent.stem for agent in agent_files}

skills = sorted(SKILLS.glob("*/SKILL.md"))
if not skills:
    errors.append("no skills found under .claude/skills")

for skill in skills:
    fields = frontmatter(skill)
    if fields is None:
        continue
    rel = skill.relative_to(ROOT)
    name = fields.get("name")
    if name != skill.parent.name:
        errors.append(f"{rel}: name '{name}' != directory '{skill.parent.name}'")
    if name and not NAME_RE.match(name):
        errors.append(f"{rel}: name '{name}' is not kebab-case")
    description = fields.get("description", "")
    if not description:
        errors.append(f"{rel}: no description (it is what makes the skill trigger)")
    elif len(description) > DESCRIPTION_MAX:
        errors.append(f"{rel}: description is {len(description)} chars; Claude Code lists at most {DESCRIPTION_MAX}")

    # `allowed-tools` pre-approves tools by their real names. The subagent tool
    # is `Agent`; a `Task` entry grants nothing and every fan-out prompts.
    for tool in list_items(fields.get("allowed-tools", "")):
        if tool == "Task":
            errors.append(f"{rel}: allowed-tools lists 'Task'; the subagent tool is 'Agent'")
    if "effort" in fields and fields["effort"] not in EFFORTS:
        errors.append(f"{rel}: effort '{fields['effort']}' is not one of {sorted(EFFORTS)}")

    text = skill.read_text()
    for ref in sorted(set(REF_RE.findall(text))):
        if not (skill.parent / ref).exists():
            errors.append(f"{rel}: points at missing '{ref}'")
    check_links(skill)
    check_spawns(skill, agent_names)

    # The other direction: a bundled file nothing mentions is dead weight, and
    # usually means a rename left the skill pointing somewhere else.
    for bundled in sorted(skill.parent.rglob("*")):
        if not bundled.is_file() or bundled.name == "SKILL.md":
            continue
        if bundled.name not in text:
            errors.append(f"{rel}: bundles unreferenced '{bundled.relative_to(skill.parent)}'")

for agent in agent_files:
    fields = frontmatter(agent)
    if fields is None:
        continue
    rel = agent.relative_to(ROOT)
    if fields.get("name") != agent.stem:
        errors.append(f"{rel}: name '{fields.get('name')}' != filename '{agent.stem}'")
    if not NAME_RE.match(agent.stem):
        errors.append(f"{rel}: name '{agent.stem}' is not kebab-case")
    if not fields.get("description"):
        errors.append(f"{rel}: no description (it is how the orchestrator picks the agent)")
    model = fields.get("model")
    if model and model not in AGENT_MODELS and not model.startswith("claude-"):
        errors.append(f"{rel}: model '{model}' is neither an alias {sorted(AGENT_MODELS)} nor a claude-* id")
    if "effort" in fields and fields["effort"] not in EFFORTS:
        errors.append(f"{rel}: effort '{fields['effort']}' is not one of {sorted(EFFORTS)}")
    if "color" in fields and fields["color"] not in COLORS:
        errors.append(f"{rel}: color '{fields['color']}' is not one of {sorted(COLORS)}")
    for tool in list_items(fields.get("tools", "")):
        if tool == "Task":
            errors.append(f"{rel}: tools lists 'Task'; the subagent tool is 'Agent'")
    check_links(agent)
    check_spawns(agent, agent_names)

for problem in errors:
    print(f"error: {problem}", file=sys.stderr)

print(f"{len(skills)} skills, {len(agent_files)} agents")
sys.exit(1 if errors else 0)
