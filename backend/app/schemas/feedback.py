from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    # The signed-in user is taken from the access token, so these two
    # fields are not used. They are still accepted so that existing
    # clients keep working.
    username: str | None = Field(default=None, max_length=100)
    role: str | None = None

    relevance: int = Field(..., ge=1, le=5)
    accuracy: int = Field(..., ge=1, le=5)
    usefulness: int = Field(..., ge=1, le=5)
    clarity: int = Field(..., ge=1, le=5)
    timeliness: int = Field(..., ge=1, le=5)

    comments: str | None = None
