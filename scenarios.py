# scenarios.py
from dataclasses import dataclass
import random


@dataclass(frozen=True)
class Scenario:
    name: str
    task_period_sec: int
    slack_min_sec: int
    slack_max_sec: int

    def sample_deadline_slack(self, rng: random.Random) -> int:
        return rng.randint(self.slack_min_sec, self.slack_max_sec)


SCENARIOS = {
    "low": Scenario(
        name="low",
        task_period_sec=15,
        slack_min_sec=60,
        slack_max_sec=120,
    ),
    
    "medium": Scenario(
        name="medium",
        task_period_sec=10,
        slack_min_sec=35,
        slack_max_sec=70,
    ),
   
    "high": Scenario(
        name="high",
        task_period_sec=6,
        slack_min_sec=18,
        slack_max_sec=40,
    ),
}

