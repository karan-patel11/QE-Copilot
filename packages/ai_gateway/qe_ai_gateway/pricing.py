"""Per-model rate table and cost estimation (§18 L1758).

Rates are configuration, not constants of the code: they change without the
software changing. The name ``estimated_cost`` is honest — this is a local
computation from the table below, not a billing figure from the provider.
"""

from __future__ import annotations

import decimal
from dataclasses import dataclass

from qe_ai_gateway.contracts import TokenUsage

#: Cost is carried as Decimal end-to-end to match ``model_runs.estimated_cost``
#: (NUMERIC(12, 6)). Float would introduce rounding drift into a column that
#: gets summed for cost roll-ups.
_QUANTUM = decimal.Decimal("0.000001")

#: Rates are per **million** tokens, which is how they are published.
_MILLION = decimal.Decimal(1_000_000)


@dataclass(frozen=True, slots=True)
class ModelRates:
    """Per-million-token rates in USD for one model.

    Cache reads and cache writes are billed at their own rates rather than at
    the input rate: reads are far cheaper, writes carry a premium. Folding
    either into ``input`` would misprice every cached call.
    """

    input_per_mtok: decimal.Decimal
    output_per_mtok: decimal.Decimal
    cache_read_per_mtok: decimal.Decimal
    cache_write_per_mtok: decimal.Decimal


def _rates(input_usd: str, output_usd: str) -> ModelRates:
    """Build rates from published input/output prices.

    Cache multipliers are the standard ones: reads at 0.1x input, 5-minute-TTL
    writes at 1.25x input.
    """
    base_input = decimal.Decimal(input_usd)
    return ModelRates(
        input_per_mtok=base_input,
        output_per_mtok=decimal.Decimal(output_usd),
        cache_read_per_mtok=base_input * decimal.Decimal("0.1"),
        cache_write_per_mtok=base_input * decimal.Decimal("1.25"),
    )


#: Known models. A model absent from this table is a cost-estimation failure,
#: not a silent zero — see :func:`estimate_cost`.
RATE_TABLE: dict[str, ModelRates] = {
    "claude-opus-5": _rates("5.00", "25.00"),
    "claude-sonnet-5": _rates("3.00", "15.00"),
    "claude-haiku-4-5": _rates("1.00", "5.00"),
    # The mock bills nothing; it makes no provider call. Present so the
    # deterministic tier exercises the same code path as a real adapter.
    "mock-model": ModelRates(
        input_per_mtok=decimal.Decimal(0),
        output_per_mtok=decimal.Decimal(0),
        cache_read_per_mtok=decimal.Decimal(0),
        cache_write_per_mtok=decimal.Decimal(0),
    ),
}


class UnknownModelError(KeyError):
    """Raised when a model has no entry in :data:`RATE_TABLE`."""


def estimate_cost(model: str, usage: TokenUsage) -> decimal.Decimal:
    """Estimated USD cost of one call, summing all four token classes.

    Raises :class:`UnknownModelError` for an unpriced model rather than
    returning zero: a silent 0.00 in ``model_runs.estimated_cost`` is
    indistinguishable from a genuinely free call, and would quietly corrupt
    every cost roll-up built on that column.
    """
    try:
        rates = RATE_TABLE[model]
    except KeyError as exc:
        raise UnknownModelError(
            f"No rate-table entry for model {model!r}; cost cannot be estimated."
        ) from exc

    total = (
        decimal.Decimal(usage.input_tokens) * rates.input_per_mtok
        + decimal.Decimal(usage.output_tokens) * rates.output_per_mtok
        + decimal.Decimal(usage.cache_read_input_tokens) * rates.cache_read_per_mtok
        + decimal.Decimal(usage.cache_creation_input_tokens) * rates.cache_write_per_mtok
    ) / _MILLION

    # ROUND_HALF_UP, not banker's rounding: this is money, and the column it
    # lands in has exactly six decimal places.
    return total.quantize(_QUANTUM, rounding=decimal.ROUND_HALF_UP)


__all__ = ["RATE_TABLE", "ModelRates", "UnknownModelError", "estimate_cost"]
