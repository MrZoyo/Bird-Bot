# bot/utils/config.py
import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ruamel.yaml import YAML


def _new_yaml() -> YAML:
    """Fresh round-trip YAML instance.

    ruamel.yaml's round-trip parser preserves comments and formatting so
    `save_config` can rewrite a YAML file without losing operator notes.
    A new instance per call avoids any shared-state concern between
    concurrent loads / saves.
    """
    yaml = YAML(typ='rt')
    yaml.preserve_quotes = True
    return yaml


class Config:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._configs: Dict[str, Any] = {}
            cls._instance._locales: Dict[Tuple[str, str], Any] = {}
        return cls._instance

    # ---- Path helpers ---------------------------------------------------

    def _config_dir(self) -> Path:
        return Path(__file__).parent.parent / 'config'

    def _locales_dir(self) -> Path:
        return Path(__file__).parent.parent / 'locales'

    def get_yaml_path(self, config_name: str) -> Path:
        return self._config_dir() / f'{config_name}.yaml'

    def get_config_path(self, config_name: str = 'main') -> Path:
        return self.get_yaml_path(config_name)

    def config_exists(self, config_name: str = 'main') -> bool:
        return self.get_yaml_path(config_name).exists()

    # ---- Config load / get / reload ------------------------------------

    def load_config(
        self,
        config_name: str = 'main',
        silent: bool = False,
    ) -> Dict[str, Any]:
        """Load a config by name from ``bot/config/<name>.yaml``."""
        yaml_path = self.get_yaml_path(config_name)

        loaded: Any = None
        if yaml_path.exists():
            try:
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    loaded = _new_yaml().load(f)
            except Exception as e:
                if not silent:
                    print(f"Could not parse YAML config {yaml_path}: {e}")
        elif config_name == 'main' and not silent:
            print(
                f"No config file found for '{config_name}' "
                f"(looked for {yaml_path.name}). Creating empty config."
            )

        self._configs[config_name] = loaded if loaded is not None else {}

        if config_name == 'main':
            self._verify_main_config()

        return self._configs[config_name]

    def _verify_main_config(self) -> None:
        required_keys = ['token', 'logging_file', 'db_path', 'guild_id']
        main = self._configs['main']
        for key in required_keys:
            if key not in main:
                print(
                    f"Missing required key '{key}' in main configuration. "
                    "Please add it."
                )
                main[key] = None

        # Defaulted keys (minimal P1-4 schema): operators who migrate from
        # a pre-P1-6 JSON main.config won't have these keys. We add them
        # with sane defaults rather than hard-failing, so existing deploys
        # keep working and only break on fields we genuinely need.
        main.setdefault('locale', 'zh_CN')
        main.setdefault('log_backup_count', 14)

    def get_config(
        self,
        config_name: str = 'main',
        silent: bool = False,
    ) -> Dict[str, Any]:
        if config_name not in self._configs:
            self.load_config(config_name=config_name, silent=silent)
        return self._configs[config_name]

    def reload_config(
        self,
        config_name: str = 'main',
        silent: bool = False,
    ) -> Dict[str, Any]:
        return self.load_config(config_name=config_name, silent=silent)

    def get_feature_flags(self) -> Dict[str, bool]:
        features = self.get_config('main').get('features', {})
        return features if isinstance(features, dict) else {}

    def is_feature_enabled(self, feature_name: str, default: bool = True) -> bool:
        feature_value = self.get_feature_flags().get(feature_name, default)
        if isinstance(feature_value, bool):
            return feature_value
        return default

    def reload_all(self) -> None:
        for config_name in list(self._configs.keys()):
            self.reload_config(config_name)

    # ---- Locale (i18n) --------------------------------------------------

    def _default_locale(self) -> str:
        return self.get_config('main').get('locale', 'zh_CN')

    def get_locale(
        self,
        name: str,
        lang: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Load (and cache) a locale YAML from ``bot/locales/<lang>/<name>.yaml``.

        ``lang`` defaults to ``main.locale`` (falling back to ``zh_CN``).
        Missing files return an empty dict; callers should treat that as
        "no translation available" and fall back through i18n.t()'s chain.
        """
        lang = lang or self._default_locale()
        key = (lang, name)
        if key not in self._locales:
            self._locales[key] = self._load_locale(lang, name)
        return self._locales[key]

    def _load_locale(self, lang: str, name: str) -> Dict[str, Any]:
        path = self._locales_dir() / lang / f'{name}.yaml'
        if not path.exists():
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return _new_yaml().load(f) or {}
        except Exception as e:
            print(f"Could not parse locale file {path}: {e}")
            return {}

    def reload_locale(
        self,
        name: str,
        lang: Optional[str] = None,
    ) -> Dict[str, Any]:
        lang = lang or self._default_locale()
        self._locales.pop((lang, name), None)
        return self.get_locale(name, lang)

    # ---- Async save (P2-3 unified writer) -------------------------------

    async def save_config(
        self,
        config_name: str,
        data: Optional[Dict[str, Any]] = None,
        *,
        reload: bool = True,
    ) -> Dict[str, Any]:
        """Atomically write a config to YAML.

        - Round-trips through ruamel.yaml so comments and formatting
          survive (this matters because `.yaml.example` templates carry
          ops-facing comments that must not be clobbered).
        - Writes to a sibling tempfile then ``os.replace`` for crash-safe
          swap: a half-written YAML file cannot be observed.
        - When ``data`` is None, the current in-memory config is written
          back (useful after mutating ``self._configs[name]`` in place).
        - When ``reload`` is True (default), re-reads the file so callers
          immediately see the canonical parsed form.
        """
        yaml_path = self.get_yaml_path(config_name)
        yaml_path.parent.mkdir(parents=True, exist_ok=True)

        payload = data if data is not None else self._configs.get(config_name, {})

        def _write() -> None:
            fd, tmp_path = tempfile.mkstemp(
                prefix=f'.{config_name}.',
                suffix='.yaml',
                dir=str(yaml_path.parent),
            )
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    _new_yaml().dump(payload, f)
                os.replace(tmp_path, yaml_path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

        await asyncio.to_thread(_write)

        if reload:
            self.load_config(config_name=config_name)
        return self._configs.get(config_name, {})


# Create a singleton instance
config = Config()
