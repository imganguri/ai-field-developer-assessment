"""Deterministic in-memory fixtures; no production customer/payment systems."""
from __future__ import annotations
from uuid import uuid5, NAMESPACE_URL

CUSTOMERS = {
    "CUST-12345": {"customer_id": "CUST-12345", "name": "Ada Example", "email": "ada@example.test", "status": "active"},
    "CUST-67890": {"customer_id": "CUST-67890", "name": "Lin Example", "email": "lin@example.test", "status": "active"},
}

def get_customer(customer_id: str) -> dict | None:
    record = CUSTOMERS.get(customer_id)
    return dict(record) if record else None

def refund(customer_id: str, amount: float, reason: str) -> dict:
    ref = "rf_" + uuid5(NAMESPACE_URL, f"{customer_id}:{amount:.2f}:{reason}").hex[:12]
    return {"customer_id": customer_id, "amount": amount, "reason": reason, "status": "simulated", "refund_reference": ref}
