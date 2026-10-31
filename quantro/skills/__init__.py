"""
Quantro Skills System
Discovers, indexes, and loads custom skill definitions from .quantro/skills/ and ~/.quantro/skills/.
"""

from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass

from quantro.config import SKILLS_GLOBAL_DIR


@dataclass
class Skill:
    name: str
    path: Path
    description: str
    content: str


class SkillManager:
    """Discovers and parses local repository skills and global user skills."""

    def __init__(self, project_root: Any):
        self.project_root = (Path(project_root) if project_root else Path.cwd()).resolve()
        self.local_dir = self.project_root / ".quantro" / "skills"
        self.global_dir = SKILLS_GLOBAL_DIR

    def discover(self) -> List[Skill]:
        skills: List[Skill] = []
        seen = set()

        # Check local repo skills first, then global skills
        dirs_to_check = [self.local_dir, self.global_dir]

        for base_dir in dirs_to_check:
            if not base_dir.exists() or not base_dir.is_dir():
                continue

            for skill_path in base_dir.iterdir():
                skill_file = None
                if skill_path.is_file() and skill_path.suffix in (".md", ".txt"):
                    skill_file = skill_path
                elif skill_path.is_dir() and (skill_path / "SKILL.md").exists():
                    skill_file = skill_path / "SKILL.md"

                if skill_file and skill_path.name not in seen:
                    seen.add(skill_path.name)
                    try:
                        raw = skill_file.read_text(encoding="utf-8")
                        # First line or header as description
                        lines = [line.strip() for line in raw.splitlines() if line.strip()]
                        desc = lines[0].lstrip("#").strip() if lines else "No description"
                        skills.append(Skill(
                            name=skill_path.stem if skill_path.is_file() else skill_path.name,
                            path=skill_file,
                            description=desc,
                            content=raw
                        ))
                    except Exception:
                        continue

        return skills


skill_manager = SkillManager(Path.cwd())
