import json
import sys
from pathlib import Path

from ruamel.yaml import YAML

import tools.migrate_config_to_yaml as migration


def read_yaml(path: Path):
    yaml = YAML(typ="safe")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.load(handle)


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_legacy_json_config_migrates_to_yaml_locale_and_seed(tmp_path, monkeypatch, capsys):
    """Temporary upgrade smoke for the one-shot config JSON -> YAML migrator."""
    config_dir = tmp_path / "bot" / "config"
    locale_dir = tmp_path / "bot" / "locales" / "zh_CN"
    tools_dir = tmp_path / "tools"
    config_dir.mkdir(parents=True)
    locale_dir.mkdir(parents=True)
    tools_dir.mkdir()

    classification_file = tools_dir / "field_classification.yaml"
    seed_file = tools_dir / "migration_db_seed.json"
    report_file = tools_dir / "migration_report.md"

    classification_file.write_text(
        """
main:
  yaml:
    - token
    - guild_id
    - admin_channel_id
    - features
    - locale
tickets:
  db:
    - ticket_types
voicechannel:
  db:
    - channel_configs
""".lstrip(),
        encoding="utf-8",
    )

    write_json(
        config_dir / "config_main.json",
        {
            "_comment": "dropped by migration",
            "token": "REAL_TOKEN_SHOULD_NOT_REACH_EXAMPLE",
            "guild_id": 123456789012345678,
            "admin_channel_id": 123456789012345679,
            "features": {
                "tickets_new": False,
                "voicechannel": True,
            },
            "locale": "zh_CN",
        },
    )
    write_json(
        config_dir / "config_tickets_new.json",
            {
                "ticket_channel_id": 123456789012345680,
                "messages": {
                    "created": "ticket created",
                },
            "ticket_types": {
                "support": {
                    "description": "Support request",
                    "guide": "Describe the issue",
                    "button_color": "primary",
                    "admin_roles": [123456789012345681],
                    "admin_users": [123456789012345682],
                },
            },
        },
    )
    write_json(
        config_dir / "config_voicechannel.json",
        {
            "channel_configs": {
                "123456789012345683": {
                    "name_prefix": "Room",
                    "type": "public",
                },
            },
            "control_panel": {
                "title": "Control panel",
            },
        },
    )

    monkeypatch.setattr(migration, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(migration, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(migration, "LOCALE_DIR", locale_dir)
    monkeypatch.setattr(migration, "CLASSIFY_FILE", classification_file)
    monkeypatch.setattr(migration, "SEED_FILE", seed_file)
    monkeypatch.setattr(migration, "REPORT_FILE", report_file)
    monkeypatch.setattr(sys, "argv", ["migrate_config_to_yaml.py"])

    assert migration.main() == 0

    captured = capsys.readouterr()
    assert "migrated tickets_new" in captured.out
    assert "tickets" in captured.out
    assert "Wrote DB seed:" in captured.out
    assert "migration_db_seed.json" in captured.out

    main_yaml = read_yaml(config_dir / "main.yaml")
    assert "_comment" not in main_yaml
    assert main_yaml["features"] == {
        "voicechannel": True,
        "tickets": False,
    }

    main_example = read_yaml(config_dir / "main.yaml.example")
    assert main_example["token"] == "YOUR_BOT_TOKEN"
    assert main_example["guild_id"] == 1145141919810
    assert main_example["admin_channel_id"] == 1145141919810

    tickets_yaml = read_yaml(config_dir / "tickets.yaml")
    assert tickets_yaml == {"ticket_channel_id": 123456789012345680}
    assert not (config_dir / "tickets_new.yaml").exists()

    tickets_example = read_yaml(config_dir / "tickets.yaml.example")
    assert tickets_example["ticket_channel_id"] == 1145141919810

    tickets_locale = read_yaml(locale_dir / "tickets.yaml")
    assert tickets_locale == {"messages": {"created": "ticket created"}}

    seed = json.loads(seed_file.read_text(encoding="utf-8"))
    assert "tickets_new" not in seed
    assert seed["tickets"]["ticket_types"]["support"]["admin_roles"] == [
        123456789012345681
    ]
    assert seed["voicechannel"]["channel_configs"]["123456789012345683"] == {
        "name_prefix": "Room",
        "type": "public",
    }

    report = report_file.read_text(encoding="utf-8")
    assert "| tickets | `ticket_types` | db | classification |" in report
    assert "| voicechannel | `channel_configs` | db | classification |" in report
