from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GithubScoreInputs:
    commits_alltime: int
    prs_contributions_alltime: int
    reviews_alltime: int
    stars_per_repo: tuple[int, ...]
    forks_received: int
    followers: int
    years_on_github: int
