"""Anthropic SDK wrapper with cost logging + monthly budget kill switch.

Every call goes through `call()`. Logs tokens + cost to agent_runs.
Raises BudgetExceeded if month-to-date cost > MONTHLY_BUDGET_USD.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "retreats.db"
load_dotenv(ROOT / ".env")

HAIKU = os.getenv("HAIKU_MODEL", "claude-haiku-4-5-20251001")
SONNET = os.getenv("SONNET_MODEL", "claude-sonnet-4-6")
MONTHLY_BUDGET = float(os.getenv("MONTHLY_BUDGET_USD", "4"))

PRICES_PER_1M = {
    HAIKU: {"in": 0.80, "out": 4.0, "cache_write": 1.0, "cache_read": 0.08},
    SONNET: {"in": 3.0, "out": 15.0, "cache_write": 3.75, "cache_read": 0.30}
}


class BudgetExceeded(Exception):
    pass


def _month_cost() -> float:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM agent_runs WHERE strftime('%Y-%m', started_at) = strftime('%Y-%m', 'now')"
    )
    row = cur.fetchone()
    conn.close()
    return float(row[0] or 0)


def _check_budget():
    spent = _month_cost()
    if spent >= MONTHLY_BUDGET:
        raise BudgetExceeded(f"Monthly budget exceeded: ${spent:.3f} >= ${MONTHLY_BUDGET:.2f}")


def _cost(model: str, usage: Any) -> float:
    p = PRICES_PER_1M.get(model)
    if not p:
        return 0.0
    inp = getattr(usage, "input_tokens", 0)
    out = getattr(usage, "output_tokens", 0)
    cache_w = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_r = getattr(usage, "cache_read_input_tokens", 0) or 0
    return (
        inp * p["in"] + out * p["out"]
        + cache_w * p["cache_write"] + cache_r * p["cache_read"]
    ) / 1_000_000


def log_run(agent_name: str, started_at: str, finished_at: str,
            tokens_in: int, tokens_out: int, cost_usd: float,
            items_processed: int, status: str, errors: str = ""):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO agent_runs (agent_name, started_at, finished_at, tokens_in, tokens_out, cost_usd, items_processed, status, errors) VALUES (?,?,?,?,?,?,?,?,?)",
        (agent_name, started_at, finished_at, tokens_in, tokens_out, cost_usd, items_processed, status, errors)
    )
    conn.commit()
    conn.close()


_client = None


def client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic()
    return _client


def call(model: str, system: str | list, messages: list, max_tokens: int = 4096,
         tools: list | None = None, tool_choice: dict | None = None):
    """Make an Anthropic API call. Returns the raw message response.
    Caller must extract content. Logs cost to caller's tracker (do it after)."""
    _check_budget()
    kwargs = dict(model=model, max_tokens=max_tokens, system=system, messages=messages)
    if tools:
        kwargs["tools"] = tools
    if tool_choice:
        kwargs["tool_choice"] = tool_choice
    return client().messages.create(**kwargs)


def cost_of(model: str, usage: Any) -> float:
    return _cost(model, usage)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
