"""Payment provider port and simulated adapter (ADR-012).

All provider contact goes through this module. The simulated provider
is deterministic — token "tok_fail" declines charges — and dedupes by
idempotency reference, exercising the same flow a real adapter
(Stripe/Paystack) will. A real adapter is the only new code once a
registered business exists.

No card data ever touches this codebase: a real provider tokenizes
payment methods and payout destinations; we only ever see tokens.
"""

import os
from decimal import Decimal
from typing import Protocol


class ChargeDeclinedError(Exception):
    """The provider refused the charge. The caller turns this into a
    402 and posts nothing."""


class PaymentProvider(Protocol):
    def charge(
        self, *, amount: Decimal, currency: str, reference: str, token: str
    ) -> str:
        """Charge a client; returns the provider's charge reference.
        Must be idempotent on `reference`."""
        ...

    def transfer(
        self, *, amount: Decimal, currency: str, reference: str, destination: str
    ) -> str:
        """Pay out to a worker destination; returns a reference."""
        ...

    def refund(
        self,
        *,
        amount: Decimal,
        currency: str,
        reference: str,
        charge_reference: str,
    ) -> str:
        """Return a previous charge to the client; returns a reference."""
        ...


class SimulatedProvider:
    """In-memory stand-in: succeeds unless told to fail, dedupes by
    reference like a real provider's idempotency keys."""

    def __init__(self) -> None:
        self._charges: dict[str, str] = {}
        self._transfers: dict[str, str] = {}
        self._refunds: dict[str, str] = {}

    def charge(self, *, amount, currency, reference, token) -> str:
        if reference in self._charges:
            return self._charges[reference]
        if token == "tok_fail":
            raise ChargeDeclinedError("Simulated decline (tok_fail).")
        charge_ref = f"sim_charge:{reference}"
        self._charges[reference] = charge_ref
        return charge_ref

    def transfer(self, *, amount, currency, reference, destination) -> str:
        if reference in self._transfers:
            return self._transfers[reference]
        transfer_ref = f"sim_transfer:{reference}"
        self._transfers[reference] = transfer_ref
        return transfer_ref

    def refund(self, *, amount, currency, reference, charge_reference) -> str:
        if reference in self._refunds:
            return self._refunds[reference]
        refund_ref = f"sim_refund:{charge_reference}"
        self._refunds[reference] = refund_ref
        return refund_ref


_provider: PaymentProvider | None = None


def get_provider() -> PaymentProvider:
    """Provider selection via PAYMENT_PROVIDER (default: simulated)."""
    global _provider
    if _provider is None:
        name = os.getenv("PAYMENT_PROVIDER", "simulated")
        if name != "simulated":
            raise RuntimeError(f"Unknown payment provider: {name!r}.")
        _provider = SimulatedProvider()
    return _provider
