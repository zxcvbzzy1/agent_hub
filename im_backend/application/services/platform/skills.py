"""SkillFileService: CRUD for skill markdown files in agent_flow/skills/.

Skills are stored as <skill_id>.md files in DEFAULT_SKILLS_DIR with a simple
frontmatter format parsed by domain.skill.loader.  After any mutation
bootstrap_skills(force=True) is called so the live in-process retriever
reflects the change immediately.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from im_backend.infra.agent_flow_bridge.pathing import ensure_agent_flow_path

ensure_agent_flow_path()

from domain.skill.loader import DEFAULT_SKILLS_DIR, load_skill_file, load_skills_from_dir  # noqa: E402
from domain.skill import bootstrap_skills  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Convert a human-readable name to a safe filename stem (skill_id)."""
    # Normalise unicode (NFKC keeps most CJK characters intact)
    text = unicodedata.normalize("NFKC", name).strip().lower()
    # Replace whitespace and ASCII punctuation with dash
    text = re.sub(r"[\s\-_/\\.,;:!?@#$%^&*()+=\[\]{}<>|`~\"']+", "-", text)
    # Strip leading/trailing dashes
    text = text.strip("-")
    # Collapse multiple consecutive dashes
    text = re.sub(r"-{2,}", "-", text)
    return text or "skill"


def _validate_skill_id(skill_id: str) -> None:
    """Raise ValueError if skill_id is not a safe single-segment filename."""
    if not skill_id:
        raise ValueError("skill_id must not be empty")
    if "/" in skill_id or "\\" in skill_id or ".." in skill_id:
        raise ValueError(f"skill_id contains illegal characters: {skill_id!r}")


def _skill_path(skill_id: str) -> Path:
    return DEFAULT_SKILLS_DIR / f"{skill_id}.md"


def _write_skill_file(path: Path, name: str, description: str, tags: list[str], content: str) -> None:
    tags_str = ", ".join(tags)
    text = f"---\nname: {name}\ndescription: {description}\ntags: {tags_str}\n---\n{content}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _skill_to_dict(skill) -> dict:
    return {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "tags": list(skill.tags),
        "content": skill.content,
        "source": skill.source,
    }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class SkillFileService:
    """Stateless CRUD service over skill markdown files."""

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list_skills(self) -> list[dict]:
        skills = load_skills_from_dir(DEFAULT_SKILLS_DIR)
        return [_skill_to_dict(s) for s in skills]

    def get_skill(self, skill_id: str) -> dict:
        _validate_skill_id(skill_id)
        path = _skill_path(skill_id)
        if not path.exists():
            raise KeyError(f"skill '{skill_id}' not found")
        skill = load_skill_file(path)
        return _skill_to_dict(skill)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create_skill(
        self,
        name: str,
        content: str,
        description: str = "",
        tags: list[str] | None = None,
        skill_id: str | None = None,
    ) -> dict:
        name = (name or "").strip()
        content = (content or "").strip()
        if not name:
            raise ValueError("name must not be empty")
        if not content:
            raise ValueError("content must not be empty")

        if skill_id is None:
            skill_id = _slugify(name)
        else:
            skill_id = skill_id.strip()

        _validate_skill_id(skill_id)

        path = _skill_path(skill_id)
        if path.exists():
            raise ValueError(f"skill '{skill_id}' already exists")

        _write_skill_file(path, name, description or "", tags or [], content)
        bootstrap_skills(force=True)
        return _skill_to_dict(load_skill_file(path))

    def update_skill(
        self,
        skill_id: str,
        name: str,
        content: str,
        description: str = "",
        tags: list[str] | None = None,
    ) -> dict:
        _validate_skill_id(skill_id)
        name = (name or "").strip()
        content = (content or "").strip()
        if not name:
            raise ValueError("name must not be empty")
        if not content:
            raise ValueError("content must not be empty")

        path = _skill_path(skill_id)
        if not path.exists():
            raise KeyError(f"skill '{skill_id}' not found")

        _write_skill_file(path, name, description or "", tags or [], content)
        bootstrap_skills(force=True)
        return _skill_to_dict(load_skill_file(path))

    def delete_skill(self, skill_id: str) -> None:
        _validate_skill_id(skill_id)
        path = _skill_path(skill_id)
        if not path.exists():
            raise KeyError(f"skill '{skill_id}' not found")
        path.unlink()
        bootstrap_skills(force=True)
