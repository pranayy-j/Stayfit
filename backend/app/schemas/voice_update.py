from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

# ~1000 words of speech is roughly 6-7k characters; leave headroom.
MAX_TRANSCRIPT_CHARS = 10_000


class VoiceUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    voice_transcript: str = Field(
        alias="voice-transcript",
        min_length=1,
        max_length=MAX_TRANSCRIPT_CHARS,
        description="What the user said, transcribed. Up to ~1000 words.",
        examples=["Had two boiled eggs and black coffee for breakfast."],
    )
    timestamp: AwareDatetime = Field(
        description="When the user spoke, ISO-8601 with a UTC offset (e.g. +05:30 or Z).",
        examples=["2026-10-20T07:30:00+05:30"],
    )


class VoiceUpdateResponse(BaseModel):
    status: Literal["received"] = "received"
    is_eating_update: bool = Field(description="True if the transcript describes the user eating.")
