"""
city/autonomy.py — Default autonomy for the fully-autonomous city.

The charter (BUILD_PLAN §0) keeps each building's decision loop ownable.
`city.runtime.can_execute()` then decides whether a building's runtime may
execute its write / destructive skills on its own:

    human_led       -> read skills only (never executes writes/destructive)
    human_assisted  -> read + write; destructive still needs a human
    autonomous      -> read + write + destructive (within budget, logged)

We set every building to `autonomous` so it fully self-drives, EXCEPT the
money / irreversible buildings, which stay at `human_assisted` so their
destructive actions (discounts, inventory adjusts, trades, sells, transfers)
remain behind the operator approval queue until explicitly widened.

Defaults are only applied when a building has no explicit autonomy set, so
operator overrides in `agent_config` are always respected.
"""
from __future__ import annotations

# Buildings whose destructive skills touch money / are hard to reverse.
# They stay at human_assisted: the runtime auto-runs their read+write
# skills, but their destructive money-moves are blocked (approval required).
MONEY_AGENTS = frozenset({
    "shopify",
    "crypto_trading",
    "finance_treasury",
    "finance_building",
    "product_flipping",
})

NON_MONEY_LEVEL = "autonomous"
MONEY_LEVEL = "human_assisted"


def default_level(name: str) -> str:
    """The autonomy a building should default to."""
    return MONEY_LEVEL if name in MONEY_AGENTS else NON_MONEY_LEVEL


def ensure_defaults(registry) -> None:
    """Set each building's autonomy to its default only if it has not been
    explicitly configured yet. `registry` is the {name: agent} map returned
    by discover_and_build() / get_registry()."""
    from city.orchestrator import AgentConfig

    for name in registry:
        # Ask the config store directly so we can tell "explicit
        # human_assisted" apart from "never configured".
        existing = AgentConfig(name).get("autonomy")
        if existing is None:
            AgentConfig(name).set(
                "autonomy", default_level(name), category="runtime", secret=False
            )
