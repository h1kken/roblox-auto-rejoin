import json
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
DEFAULT_CONFIG = {
    "rejoin_if_in_other_place": True,
}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG.copy())
        return DEFAULT_CONFIG.copy()

    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        save_config(DEFAULT_CONFIG.copy())
        return DEFAULT_CONFIG.copy()

    config = DEFAULT_CONFIG.copy()
    config.update(data)
    return config


def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(config, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def get_rejoin_if_in_other_place() -> bool:
    return bool(load_config()["rejoin_if_in_other_place"])


def set_rejoin_if_in_other_place(value: bool) -> None:
    config = load_config()
    config["rejoin_if_in_other_place"] = value
    save_config(config)
