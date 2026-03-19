import pytest
from src.browser.config import BrowserConfig, ExplorationConfig


def test_browser_config_defaults():
    config = BrowserConfig()
    assert config.timeout == 30
    assert config.checkpoint_interval == 5
    assert config.max_steps == 20
    assert config.headless is True


def test_exploration_config_defaults():
    config = ExplorationConfig()
    assert config.novelty_threshold == 0.85
    assert config.no_new_findings_limit == 3
    assert config.error_rate_threshold == 0.5
