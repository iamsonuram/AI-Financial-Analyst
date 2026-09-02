"""Data-access layer for the Visualizations tab.

This module reuses SQLAgent's exact period conditions and metric columns so the
charts always reflect the same current-vs-prior figures the investigation
engine produces. It adds no new analytical logic, only read-only queries over
the existing finance_data table.
"""

import sqlite3

import pandas as pd

from config import DATABASE_PATH
from agents.sql_agent import SQLAgent, build_date_period, build_window_period


class VisualsData:
    """Read-only current-vs-prior (or single-window) financial data by dimension."""

    def __init__(self, database_path=DATABASE_PATH):
        self.database_path = database_path
        self.conn = sqlite3.connect(database_path)
        self.sql_agent = SQLAgent(database_path)

    def close(self):
        self.conn.close()

    # ------------------------------------------------------------
    # Period helpers
    # ------------------------------------------------------------

    @staticmethod
    def period_from_analysis(response):
        """
        Rebuild a period dict from an existing analysis response so charts
        match the currently displayed analysis period.

        Window (date-range) analyses carry a window flag: the period describes
        the selected range only and must NOT be turned into a comparison.
        """
        if not response:
            return None
        mode = response.get("period_mode", "quarter")
        if response.get("window"):
            return build_window_period(
                response.get("current_start") or response.get("current_year"),
                response.get("current_end") or response.get("current_quarter"),
            )
        if mode == "custom":
            return build_date_period(
                response.get("current_start") or response.get("current_year"),
                response.get("current_end") or response.get("current_quarter"),
            )
        return {
            "mode": "quarter",
            "current_year": response.get("current_year"),
            "current_quarter": response.get("current_quarter"),
            "previous_year": response.get("previous_year"),
            "previous_quarter": response.get("previous_quarter"),
        }

    @staticmethod
    def default_quarter_period():
        return SQLAgent.get_analysis_period()

    @staticmethod
    def _period_label(period):
        if period.get("window"):
            return (
                f"{period['current_start']} to {period['current_end']}"
            )
        if period.get("mode") == "custom":
            return (
                f"{period['current_start']} to {period['current_end']} "
                f"vs {period['previous_start']} to {period['previous_end']}"
            )
        return (
            f"{period['current_year']} Q{period['current_quarter']} vs "
            f"{period['previous_year']} Q{period['previous_quarter']}"
        )

    @staticmethod
    def _short_label(period):
        if period.get("window"):
            return (
                f"{period['current_start']} – {period['current_end']}"
            )
        if period.get("mode") == "custom":
            return (
                f"{period['current_start']} – {period['current_end']}"
            )
        return (
            f"Q{period['current_quarter']} {period['current_year']} vs "
            f"Q{period['previous_quarter']} {period['previous_year']}"
        )

    # ------------------------------------------------------------
    # Queries (reuse SQLAgent's period + metric logic)
    # ------------------------------------------------------------

    def _fetch(self, sql):
        return pd.read_sql(sql, self.conn)

    def quarter_snapshot(self, period, region, market_unit):
        """Single-row current-vs-prior snapshot of all metrics."""
        sql = self.sql_agent._generate_quarter_sql(
            period, region, market_unit
        )
        return self._fetch(sql)

    def dimension_breakdown(self, dimension, period, region, market_unit):
        """Current-vs-prior grouped by a dimension (MLOB, UW_Portfolio, etc.)."""
        if dimension not in self.sql_agent.HIERARCHY:
            raise ValueError(f"Unsupported dimension: {dimension}")
        sql = self.sql_agent._generate_dimension_sql(
            dimension, period, region, market_unit
        )
        return self._fetch(sql)

    def market_renewal_activity(self, period, region, market_unit):
        """
        Market-wide business status breakdown (New Business / Renewal /
        Cancelled): counts and current-period premium & technical result.
        """
        current_cond = self.sql_agent._period_condition(period, "current")
        where = (
            f"Region = '{self.sql_agent._escape_sql_value(region)}' "
            f"AND Market_Unit = '{self.sql_agent._escape_sql_value(market_unit)}' "
            f"AND ({current_cond})"
        )
        sql = f"""
SELECT
    Renewal_Category AS status,
    COUNT(*) AS record_count,
    SUM(Premium) AS premium,
    SUM(Technical_Result) AS technical_result
FROM finance_data
WHERE {where}
GROUP BY Renewal_Category
ORDER BY premium DESC;
"""
        return self._fetch(sql)

    def top_portfolios(self, period, region, market_unit, limit=10):
        """
        Top UW portfolios by absolute Technical Result change across the whole
        market (regardless of MLOB), for the portfolio comparison chart.
        """
        where_mlob = self.sql_agent._build_where_clause(
            period, region, market_unit
        )
        sql = f"""
SELECT
    UW_Portfolio AS portfolio,
    {self.sql_agent._metric_columns(period)},
    COUNT(*) AS Record_Count
FROM finance_data
WHERE {where_mlob}
GROUP BY UW_Portfolio
ORDER BY ABS(Technical_Result_Change) DESC
LIMIT {int(limit)};
"""
        return self._fetch(sql)
