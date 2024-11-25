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

    def load_config(self, file_path: Optional[str] = None, config_name: str = 'main') -> Dict[str, Any]:
        """
        Load a configuration file.

        Args:
            file_path: Optional path to config file. If None, uses default path based on config_name
            config_name: Name of the configuration to load (e.g., 'main', 'role_cog', etc.)

        Returns:
            Dict containing the configuration
        """
        if file_path is None:
            # Default path structure: bot/config/config_{name}.json
            file_path = Path(__file__).parent.parent / 'config' / f'config_{config_name}.json'
        else:
            file_path = Path(file_path)

        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                self._configs[config_name] = json.load(file)
        except FileNotFoundError:
            print(f"Configuration file {file_path} not found. Creating empty config.")
            self._configs[config_name] = {}
        except json.JSONDecodeError:
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

    def get_config(self, config_name: str = 'main') -> Dict[str, Any]:
        """
        Get a configuration by name. Loads it if not already loaded.

        Args:
            config_name: Name of the configuration to get

        Returns:
            Dict containing the configuration
        """
        if config_name not in self._configs:
            self.load_config(config_name=config_name)
        return self._configs[config_name]

    def reload_config(self, config_name: str = 'main') -> Dict[str, Any]:
        """
        Force reload a configuration from disk.

        Args:
            config_name: Name of the configuration to reload

        Returns:
            Dict containing the reloaded configuration
        """
        return self.load_config(config_name=config_name)

    def reload_all(self) -> None:
        """Reload all known configurations from disk."""
        for config_name in list(self._configs.keys()):
            self.reload_config(config_name)


# Create a singleton instance
config = Config()
