import uuid
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

# ~250 words of speech.
MAX_TRANSCRIPT_CHARS = 1_500


class VoiceUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    voice_transcript: str = Field(
        alias="voice-transcript",
        min_length=1,
        # Enforced in the controller (413 "Transcript too long") rather than by Pydantic, so the
        # FE gets a clear message; still advertised in the OpenAPI schema.
        json_schema_extra={"maxLength": MAX_TRANSCRIPT_CHARS},
        description=f"What the user said, transcribed. Up to {MAX_TRANSCRIPT_CHARS} characters.",
        examples=["Had two boiled eggs and black coffee for breakfast."],
    )
    timestamp: AwareDatetime = Field(
        description="When the user spoke, ISO-8601 with a UTC offset (e.g. +05:30 or Z).",
        examples=["2026-10-20T07:30:00+05:30"],
    )


class VoiceUpdateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="ID of the stored voice update.")
    status: Literal["received"] = "received"
    created_at: datetime = Field(description="When the server stored the update (UTC).")
    is_eating_update: bool = Field(description="True if the transcript describes the user eating.")
    eating_status: Literal["logged", "needs_detail"] | None = Field(
        default=None,
        description=(
            "logged: food items were found. needs_detail: sounded like eating but no specific "
            "food was named; ask the user what they ate. null: not an eating update."
        ),
    )
