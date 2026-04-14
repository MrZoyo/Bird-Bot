# bot/utils/config.py
import json
from pathlib import Path
from typing import Dict, Any, Optional


class Config:
    _instance = None
    _configs: Dict[str, Dict[str, Any]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_config_path(self, config_name: str = 'main') -> Path:
        """Get the default path of a configuration file."""
        return Path(__file__).parent.parent / 'config' / f'config_{config_name}.json'

    def config_exists(self, config_name: str = 'main') -> bool:
        """Check whether a configuration file exists on disk."""
        return self.get_config_path(config_name).exists()

    def load_config(
        self,
        file_path: Optional[str] = None,
        config_name: str = 'main',
        silent: bool = False
    ) -> Dict[str, Any]:
        """
        Load a configuration file.

        Args:
            file_path: Optional path to config file. If None, uses default path based on config_name
            config_name: Name of the configuration to load (e.g., 'main', 'role_cog', etc.)
            silent: Whether to suppress missing/parse warnings for optional checks

        Returns:
            Dict containing the configuration
        """
        if file_path is None:
            # Default path structure: bot/config/config_{name}.json
            file_path = self.get_config_path(config_name)
        else:
            file_path = Path(file_path)

        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                self._configs[config_name] = json.load(file)
        except FileNotFoundError:
            if config_name == 'main' and not silent:
                print(f"Configuration file {file_path} not found. Creating empty config.")
            self._configs[config_name] = {}
        except json.JSONDecodeError:
            if not silent:
                print(f"Could not parse the JSON configuration file {file_path}. Please check its syntax.")
            self._configs[config_name] = {}

        # If this is the main config, verify required keys
        if config_name == 'main':
            self._verify_main_config()

        return self._configs[config_name]

    def _verify_main_config(self):
        """Verify that the main config contains all required keys."""
        required_keys = ['token', 'logging_file', 'db_path', 'guild_id']
        for key in required_keys:
            if key not in self._configs['main']:
                print(f"Missing required key '{key}' in main configuration file. Please add it.")
                self._configs['main'][key] = None

    def get_config(self, config_name: str = 'main', silent: bool = False) -> Dict[str, Any]:
        """
        Get a configuration by name. Loads it if not already loaded.

        Args:
            config_name: Name of the configuration to get
            silent: Whether to suppress missing/parse warnings when loading

        Returns:
            Dict containing the configuration
        """
        if config_name not in self._configs:
            self.load_config(config_name=config_name, silent=silent)
        return self._configs[config_name]

    def reload_config(self, config_name: str = 'main', silent: bool = False) -> Dict[str, Any]:
        """
        Force reload a configuration from disk.

        Args:
            config_name: Name of the configuration to reload
            silent: Whether to suppress missing/parse warnings while reloading

        Returns:
            Dict containing the reloaded configuration
        """
        return self.load_config(config_name=config_name, silent=silent)

    def get_feature_flags(self) -> Dict[str, bool]:
        """Get feature flags from main config."""
        features = self.get_config('main').get('features', {})
        return features if isinstance(features, dict) else {}

    def is_feature_enabled(self, feature_name: str, default: bool = True) -> bool:
        """Check whether a feature is enabled in main config."""
        feature_value = self.get_feature_flags().get(feature_name, default)
        if isinstance(feature_value, bool):
            return feature_value
        return default

    def reload_all(self) -> None:
        """Reload all known configurations from disk."""
        for config_name in list(self._configs.keys()):
            self.reload_config(config_name)


# Create a singleton instance
config = Config()
