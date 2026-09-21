from src.matching.client import MinhaReceitaClient
from src.matching.eligibility import EligibilityVerdict, evaluate_eligibility, load_eligibility_config
from src.matching.scoring import matching_score, recommend, score_match
from src.matching.service import (
    CompanyMatch,
    CompanyOpportunityResult,
    MatchmakingResult,
    MatchmakingService,
    OpportunityMatch,
)

__all__ = [
    "CompanyMatch",
    "CompanyOpportunityResult",
    "EligibilityVerdict",
    "MatchmakingResult",
    "MatchmakingService",
    "MinhaReceitaClient",
    "OpportunityMatch",
    "evaluate_eligibility",
    "load_eligibility_config",
    "matching_score",
    "recommend",
    "score_match",
]
