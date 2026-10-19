import logging

from typesafe_sdk import AsyncTypeSafeClient, Noul

from app.config import settings

logger = logging.getLogger(__name__)

# Passed to JEV verbatim; keep wording unchanged unless the product definition changes.
EATING_UPDATE_CRITERIA = """An eating update says the user ate or drank something with calories, or eating currently or will eat in future(all three tenses should be equally prioritised, tense should not create a difference), only the name of caloric food item in the statement without any quantity or time reference is also an eating update for example 'egg', 'fish', 'milk', 'prawns' or any specific animal part like 'chicken leg piece', 'goat liver', 'cow beef' etc should also be considered as an eating update. You need to decide wether the statement is eating update or not. The food should also be specifically mentioned what did you eat, very generalised vague food category without any item name wont count. It should also only deal with user's eating updates, not with any user's relatives/friends/family or any other referenced name.
If its a long text even with very less statement containing food update that fulfils previous mentioned criterias, consider it as an eating update."""  # noqa: E501

# JEV's noul is P(yes) in [0, 1]; strictly above this counts as an eating update.
EATING_UPDATE_THRESHOLD = 0.75

# One shared client (and connection pool) per process, created on first use inside the
# running event loop and closed on app shutdown.
_client: AsyncTypeSafeClient | None = None


def _get_client() -> AsyncTypeSafeClient:
    global _client
    if _client is None:
        _client = AsyncTypeSafeClient(api_key=settings.typesafe_api_key)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def eating_update_probability(transcript: str) -> float:
    """Ask JEV how likely the transcript is an eating update. Raises TypeSafeError on failure."""
    response = await _get_client().system_one(
        state=transcript,
        questions={"is_eating_update": Noul(instructions=EATING_UPDATE_CRITERIA)},
    )
    probability = response.nouls["is_eating_update"].noul
    logger.debug("JEV eating-update probability=%.3f model=%s", probability, response.model)
    return probability


async def is_eating_update(transcript: str) -> bool:
    return await eating_update_probability(transcript) > EATING_UPDATE_THRESHOLD
