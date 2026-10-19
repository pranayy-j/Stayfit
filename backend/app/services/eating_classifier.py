import logging

from langchain_core.runnables import Runnable
from langchain_typesafe import ClassifierRequest, ClassifierResponse, Noul, TypeSafeClassifier
from langchain_typesafe.client import (
    TypeSafeAPIConnectionError,
    TypeSafeError,
    TypeSafeInternalServerError,
    TypeSafeRateLimitError,
)

from app.config import settings

logger = logging.getLogger(__name__)

# Passed to JEV verbatim; keep wording unchanged unless the product definition changes.
EATING_UPDATE_CRITERIA = """An eating update says the user ate or drank something with calories, or eating currently or will eat in future(all three tenses should be equally prioritised, tense should not create a difference), only the name of caloric food item in the statement without any quantity or time reference is also an eating update for example 'egg', 'fish', 'milk', 'prawns' or any specific animal part like 'chicken leg piece', 'goat liver', 'cow beef' etc should also be considered as an eating update. You need to decide wether the statement is eating update or not. The food should also be specifically mentioned what did you eat, very generalised vague food category without any item name wont count. It should also only deal with user's eating updates, not with any user's relatives/friends/family or any other referenced name.
If its a long text even with very less statement containing food update that fulfils previous mentioned criterias, consider it as an eating update."""  # noqa: E501

# JEV's noul is P(yes) in [0, 1]; strictly above this counts as an eating update.
EATING_UPDATE_THRESHOLD = 0.75

TIMEOUT_SECONDS = 10.0
# Retry only transient failures (network, timeouts, 429, 5xx); a bad key or request won't heal.
RETRYABLE_ERRORS = (TypeSafeAPIConnectionError, TypeSafeRateLimitError, TypeSafeInternalServerError)
MAX_ATTEMPTS = 3


class ClassificationError(Exception):
    """JEV could not classify the transcript (misconfiguration or API failure)."""


# One long-lived classifier (and HTTP connection pool) per process, created on first use so
# a missing API key fails the request rather than app startup; closed on app shutdown.
_classifier: TypeSafeClassifier | None = None
_runnable: Runnable[ClassifierRequest, ClassifierResponse] | None = None


def _get_runnable() -> Runnable[ClassifierRequest, ClassifierResponse]:
    global _classifier, _runnable
    if _runnable is None:
        try:
            _classifier = TypeSafeClassifier(
                api_key=settings.typesafe_api_key or "", timeout=TIMEOUT_SECONDS
            )
        except ValueError as e:  # raised for a missing API key
            raise ClassificationError(str(e)) from e
        _runnable = _classifier.with_retry(
            retry_if_exception_type=RETRYABLE_ERRORS,
            wait_exponential_jitter=True,
            stop_after_attempt=MAX_ATTEMPTS,
        )
    return _runnable


async def close_client() -> None:
    global _classifier, _runnable
    if _classifier is not None and _classifier.async_client is not None:
        await _classifier.async_client.aclose()
    _classifier = _runnable = None


async def eating_update_probability(transcript: str) -> float:
    """Ask JEV how likely the transcript is an eating update. Raises ClassificationError."""
    try:
        response = await _get_runnable().ainvoke(
            {
                "state": transcript,
                "questions": {"is_eating_update": Noul(instructions=EATING_UPDATE_CRITERIA)},
            },
            config={"run_name": "eating_update_classifier"},
        )
    except TypeSafeError as e:
        raise ClassificationError(str(e)) from e
    probability = response.nouls["is_eating_update"].noul
    logger.debug("JEV eating-update probability=%.3f model=%s", probability, response.model)
    return probability


async def is_eating_update(transcript: str) -> bool:
    return await eating_update_probability(transcript) > EATING_UPDATE_THRESHOLD
