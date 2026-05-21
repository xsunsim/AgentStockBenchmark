from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentstockbenchmark.settings import PROMPTS_DIR


@dataclass(frozen=True)
class PromptArtifact:
    prompt_id: str
    path: Path


def list_prompts(prompts_dir: Path = PROMPTS_DIR) -> list[PromptArtifact]:
    if not prompts_dir.exists():
        return []

    prompts: list[PromptArtifact] = []
    for child in sorted(prompts_dir.iterdir()):
        prompt_path = child / "prompt.md"
        if child.is_dir() and prompt_path.exists():
            prompts.append(PromptArtifact(prompt_id=child.name, path=prompt_path))
    return prompts


def load_prompt(prompt_id: str, prompts_dir: Path = PROMPTS_DIR) -> str:
    prompt_path = prompts_dir / prompt_id / "prompt.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"prompt not found: {prompt_path}")
    return prompt_path.read_text()
