"""Strict input schemas for the customer tools."""
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

CustomerId = Annotated[str, StringConstraints(pattern=r"^CUST-[0-9]{5}$", strict=True)]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

class CustomerLookup(StrictModel):
    customer_id: CustomerId

class RefundRequest(StrictModel):
    customer_id: CustomerId
    amount: Annotated[float, Field(gt=0, allow_inf_nan=False, strict=True)]
    reason: Annotated[str, Field(min_length=10, strict=True)]

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must contain non-whitespace characters")
        return value
