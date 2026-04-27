from pathlib import Path

from ruamel.yaml import YAML

from bot.main import COG_SPECS, _load_cog_class


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "bot" / "config"


def load_yaml(path: Path):
    yaml = YAML(typ="safe")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.load(handle)


def test_config_examples_parse_and_stay_yaml_only():
    examples = sorted(CONFIG_DIR.glob("*.yaml.example"))

    assert examples, "bot/config should ship YAML templates"
    assert not list(CONFIG_DIR.glob("*.json*")), "legacy JSON config templates belong on the archive branch"

    for path in examples:
        data = load_yaml(path)
        assert isinstance(data, dict), f"{path} should parse to a mapping"


def test_cog_specs_match_feature_flags_and_config_templates():
    main_config = load_yaml(CONFIG_DIR / "main.yaml.example")
    feature_flags = set(main_config["features"])
    spec_features = {spec["feature"] for spec in COG_SPECS}

    assert spec_features == feature_flags

    for spec in COG_SPECS:
        spec_text = " ".join(str(value) for value in spec.values())
        assert "notebook" not in spec_text.lower()
        assert "tickets_new" not in spec_text.lower()

        for config_name in spec["required_configs"]:
            assert (CONFIG_DIR / f"{config_name}.yaml.example").exists()


def test_cog_specs_import_the_registered_class():
    for spec in COG_SPECS:
        cog_class = _load_cog_class(spec["module_path"], spec["class_name"])

        assert cog_class.__name__ == spec["class_name"]
