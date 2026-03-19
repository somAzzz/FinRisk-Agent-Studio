from dataclasses import dataclass


@dataclass
class BrowserConfig:
    timeout: int = 30
    checkpoint_interval: int = 5
    max_steps: int = 20
    headless: bool = True


@dataclass
class ExplorationConfig:
    novelty_threshold: float = 0.85
    no_new_findings_limit: int = 3
    error_rate_threshold: float = 0.5
