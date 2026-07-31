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

    The four classes are **disjoint** — :func:`estimate_cost` sums them
    independently. Adapters are responsible for expressing their vendor's usage
    in those terms; Groq reports cached tokens *inside* its prompt total, so its
    adapter subtracts before populating :class:`TokenUsage` (ADR-0210 §2).
    """

    input_per_mtok: decimal.Decimal
    output_per_mtok: decimal.Decimal
    cache_read_per_mtok: decimal.Decimal
    cache_write_per_mtok: decimal.Decimal


def _rates(input_usd: str, output_usd: str, cached_input_usd: str | None = None) -> ModelRates:
    """Build rates from published prices (ADR-0210, groq.com/pricing).

    ``cached_input_usd`` defaults to the full input rate when Groq publishes no
    cached price for the model. Assuming the 50% discount the gpt-oss models get
    would *understate* cost; assuming none can only overstate it, and overstating
    is the safe direction for a budget ceiling (ADR-0208).

    Cache **writes** are $0 on every model: Groq provides prompt caching at no
    additional cost, and has no cache-creation token class at all.
    """
    base_input = decimal.Decimal(input_usd)
    return ModelRates(
        input_per_mtok=base_input,
        output_per_mtok=decimal.Decimal(output_usd),
        cache_read_per_mtok=(
            decimal.Decimal(cached_input_usd) if cached_input_usd is not None else base_input
        ),
        cache_write_per_mtok=decimal.Decimal(0),
    )


#: Known models, per **million** tokens in USD.
#: Source: https://groq.com/pricing retrieved 2026-07-31 (ADR-0210 Decision 4).
#: A model absent from this table is a cost-estimation failure, not a silent
#: zero — see :func:`estimate_cost`.
RATE_TABLE: dict[str, ModelRates] = {
    # Strict structured output (constrained decoding) — the default.
    "openai/gpt-oss-120b": _rates("0.15", "0.60", "0.075"),
    "openai/gpt-oss-20b": _rates("0.075", "0.30", "0.0375"),
    "moonshotai/kimi-k2-instruct-0905": _rates("1.00", "3.00", "0.50"),
    # No cached-input price published for these; see _rates docstring.
    "llama-3.3-70b-versatile": _rates("0.59", "0.79"),
    "llama-3.1-8b-instant": _rates("0.05", "0.08"),
    "qwen/qwen3.6-27b": _rates("0.60", "3.00"),
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
