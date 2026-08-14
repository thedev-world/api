from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class GitHubScoreInputs:
    commits_alltime: int
    prs_contributions_alltime: int
    reviews_alltime: int
    private_contributions_alltime: int
    stars_per_repo: tuple[int, ...]
    forks_received: int
    followers: int
    account_created_at: datetime
