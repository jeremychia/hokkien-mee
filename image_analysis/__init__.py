__version__ = "0.1.0"

from pathlib import Path
import yaml

_yaml_path = Path(__file__).parent / "data" / "ingredients.yaml"
_config = yaml.safe_load(_yaml_path.read_text())
INGREDIENTS: list[str] = _config["names"]

STYLE_CLASSES = ["wet", "dry"]
