from pathlib import Path

import yaml

CONFIG_FILE = Path("config.yml")
SAVE_FILE = Path("save.json")

with CONFIG_FILE.open() as f:
    config = yaml.safe_load(f)
