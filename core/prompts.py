from pathlib import Path
from string import Template

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(name: str, **kwargs) -> str:
    tpl = Template((_PROMPTS_DIR / name).read_text(encoding="utf-8"))
    return tpl.substitute(**kwargs)
