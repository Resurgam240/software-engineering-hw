"""HTTP command DTOs: reject unknown fields rather than trusting actor or role input."""

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class StrictModel(BaseModel):
    """Every DTO rejects additional properties, including forged role and actor IDs."""

    model_config = ConfigDict(extra="forbid")


class RegisterInput(StrictModel):
    """Public registration can only create an ordinary user."""

    username: str = Field(max_length=20)
    password: str = Field(max_length=64)
    nickname: str = Field(default="", max_length=40)


class LoginInput(StrictModel):
    """Bound inputs before hashing or database lookups."""

    username: str = Field(max_length=100)
    password: str = Field(max_length=64)


class ContentInput(StrictModel):
    """A draft may omit fields that submission later requires."""

    title: str = Field(max_length=200)
    category: str | None = None
    condition: str | None = None
    price: str | None = None
    description: str = Field(default="", max_length=500)
    image_ids: list[str] = Field(default_factory=list, max_length=3)


class EditInput(ContentInput):
    """Edits identify both the observed state and the observed public content."""

    expected_row_version: StrictInt
    content_version: StrictInt


class StateInput(StrictModel):
    """Product lifecycle transitions always carry the observed row version."""

    expected_row_version: StrictInt


class SubmitInput(StateInput):
    """Submission is bound to a specific content version."""

    content_version: StrictInt


class WithdrawInput(StateInput):
    """Withdrawal cannot act on a replaced review batch."""

    batch_id: str


class ReserveInput(SubmitInput):
    """Private message is only accepted by the reservation creation endpoint."""

    product_id: str
    message: str = Field(max_length=200)


class ReservationStateInput(StateInput):
    """Two-row changes require two expected versions."""

    expected_reservation_version: StrictInt


class ReservationReasonInput(ReservationStateInput):
    """Cancellation and rejection require a meaningful reason."""

    reason: str = Field(max_length=200)


class ReviewInput(SubmitInput):
    """Review binds batch, content, state, and an explicit decision."""

    batch_id: str
    decision: str
    reason: str = Field(default="", max_length=200)


class ViolationInput(SubmitInput):
    """A reserved product additionally supplies its active reservation version."""

    reason: str = Field(max_length=200)
    batch_id: str | None = None
    expected_reservation_version: StrictInt | None = None


class PrivateAccessInput(StrictModel):
    """Each administrative read records a new purpose and reason."""

    purpose: str
    reason: str = Field(max_length=200)
