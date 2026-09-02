import re
import time
from datetime import datetime

import pandas as pd

from config import DATABASE_PATH
from agents.sql_agent import SQLAgent
from agents.sql_executor import SQLExecutor
from agents.sql_validator import SQLValidator
from llm.openrouter_client import OpenRouterClient


class AnalystOrchestrator:
    """
    Deterministic financial investigation orchestrator.

    The LLM is used only for the final executive commentary.
    Driver selection is performed in Python from SQL results so that:
      * the same data always produces the same drill-down;
      * multiple material contributors can be selected;
      * contributors are selected until they explain at least 80% of
        the parent Technical Result movement, with a minimum of three
        contributors whenever three or more are available;
      * the full driver path is preserved for the final commentary.

    Investigation hierarchy:
        Quarter comparison
          -> Main_Line_of_Business
          -> UW_Portfolio (for each selected MLOB)
          -> Cedent_Name (for each selected portfolio)
          -> Renewal_Category (for each selected cedent)

    SQL is deliberately kept in backend history/logs. UI events expose
    the analytical question, result table, selected drivers and coverage,
    but never require the UI to display generated SQL.
    """

    DRIVER_HIERARCHY = [
        "Main_Line_of_Business",
        "UW_Portfolio",
        "Cedent_Name",
    ]

    FINAL_CATEGORY = "Renewal_Category"

    COVERAGE_TARGET = 0.80
    MIN_DRIVERS = 3
    MAX_DRIVERS = 8
    RECONCILIATION_TOLERANCE = 0.005

    def __init__(self):
        self.sql_agent = SQLAgent(DATABASE_PATH)
        self.sql_validator = SQLValidator(DATABASE_PATH)
        self.sql_executor = SQLExecutor(DATABASE_PATH)
        self.llm = OpenRouterClient()

    # =========================================================
    # PERIOD
    # =========================================================

    @staticmethod
    def get_current_period():
        today = datetime.now()
        year = today.year
        month = today.month

        if month <= 3:
            quarter = 1
        elif month <= 6:
            quarter = 2
        elif month <= 9:
            quarter = 3
        else:
            quarter = 4

        if quarter == 1:
            previous_year = year - 1
            previous_quarter = 4
        else:
            previous_year = year
            previous_quarter = quarter - 1

        return {
            "mode": "quarter",
            "current_year": year,
            "current_quarter": quarter,
            "previous_year": previous_year,
            "previous_quarter": previous_quarter,
        }

    # =========================================================
    # PERIOD LABELS
    # =========================================================

    @staticmethod
    def _period_labels(period):
        """Human-readable labels for the analysis period."""
        if period.get("window"):
            # Date-range window mode: no comparison period exists. Every label
            # describes the selected window and the label never says "versus".
            current_label = (
                f"{period['current_start']} to {period['current_end']}"
            )
            return {
                "current_label": current_label,
                "previous_label": current_label,
                "comparison_label": current_label,
            }
        if period.get("mode") == "custom":
            current_label = (
                f"{period['current_start']} to {period['current_end']}"
            )
            previous_label = (
                f"{period['previous_start']} to {period['previous_end']}"
            )
            comparison_label = f"{current_label} versus {previous_label}"
        else:
            current_label = (
                f"{period['current_year']} Q{period['current_quarter']}"
            )
            previous_label = (
                f"{period['previous_year']} Q{period['previous_quarter']}"
            )
            comparison_label = f"{current_label} versus {previous_label}"
        return {
            "current_label": current_label,
            "previous_label": previous_label,
            "comparison_label": comparison_label,
        }

    # =========================================================
    # EVENT HELPER
    # =========================================================

    @staticmethod
    def _send_progress(progress_callback, event):
        if progress_callback is None:
            return
        try:
            progress_callback(event)
        except Exception:
            # UI progress must never break the financial analysis.
            pass

    # =========================================================
    # DATA HELPERS
    # =========================================================

    @staticmethod
    def _find_column(dataframe, candidates):
        if dataframe is None:
            return None
        lookup = {str(c).lower(): c for c in dataframe.columns}
        for candidate in candidates:
            if candidate in dataframe.columns:
                return candidate
            found = lookup.get(str(candidate).lower())
            if found is not None:
                return found
        return None

    @classmethod
    def _find_change_column(cls, dataframe):
        return cls._find_column(
            dataframe,
            [
                "Technical_Result_Change",
                "Change_TR",
                "TR_Change",
                "Change_in_Technical_Result",
                "change_in_technical_result",
                "Change",
            ],
        )

    @classmethod
    def _find_current_previous_columns(cls, dataframe):
        current = cls._find_column(
            dataframe,
            [
                "Technical_Result_Current",
                "Current_Technical_Result",
                "Technical_Result_Current_Quarter",
            ],
        )
        previous = cls._find_column(
            dataframe,
            [
                "Technical_Result_Previous",
                "Previous_Technical_Result",
                "Technical_Result_Previous_Quarter",
            ],
        )
        return current, previous

    @staticmethod
    def _numeric(series):
        return pd.to_numeric(series, errors="coerce")

    @staticmethod
    def _safe_float(value):
        if value is None:
            return None
        try:
            result = float(value)
            if pd.isna(result):
                return None
            return result
        except (TypeError, ValueError):
            try:
                cleaned = str(value).replace(",", "").replace("$", "").strip()
                result = float(cleaned)
                return None if pd.isna(result) else result
            except (TypeError, ValueError):
                return None

    @classmethod
    def _overall_change(cls, dataframe):
        if dataframe is None or dataframe.empty:
            return 0.0

        change_col = cls._find_change_column(dataframe)
        current_col, previous_col = cls._find_current_previous_columns(dataframe)

        if current_col and previous_col:
            current = cls._safe_float(dataframe[current_col].iloc[0])
            previous = cls._safe_float(dataframe[previous_col].iloc[0])
            if current is not None and previous is not None:
                return current - previous

        if change_col:
            values = cls._numeric(dataframe[change_col]).dropna()
            if not values.empty:
                return float(values.iloc[0]) if len(values) == 1 else float(values.sum())

        return 0.0

    @staticmethod
    def _movement_direction(change):
        if change < 0:
            return "negative"
        if change > 0:
            return "positive"
        return "neutral"

    @staticmethod
    def _movement_text(change):
        if change < 0:
            return "deteriorated"
        if change > 0:
            return "improved"
        return "remained broadly unchanged"

    # =========================================================
    # WITHIN-WINDOW MOVEMENT HELPERS (DATE-RANGE MODE)
    # =========================================================

    @classmethod
    def _within_window_movements(cls, series_df):
        """Detect month-over-month movements within a window's monthly series.

        The series_df is the "Movement" investigation result (one row per
        calendar month, each with monthly *_Change / *_Current columns). We
        compare consecutive months *within the window* to describe financial
        activity that is happening inside the selected range. No comparison
        against an outside period is ever made.
        """
        if series_df is None or series_df.empty:
            return None
        change_col = cls._find_change_column(series_df)
        if change_col is None:
            return None
        month_col = cls._find_column(series_df, ["Month"])
        if month_col is None:
            return None

        rows = series_df.sort_values(month_col).reset_index(drop=True)
        movements = []
        for idx, row in rows.iterrows():
            value = cls._safe_float(row.get(change_col))
            if value is None:
                continue
            if idx > 0:
                prior = cls._safe_float(rows[change_col].iloc[idx - 1])
                if prior is not None and abs(prior) > 1e-9:
                    pct = (value - prior) / abs(prior) * 100.0
                else:
                    pct = None
            else:
                pct = None
            movements.append(
                {
                    "month": str(row.get(month_col)),
                    "value": value,
                    "month_over_month_pct": pct,
                }
            )
        if not movements:
            return None
        return {
            "movements": movements,
            "peak_month": max(movements, key=lambda m: m["value"]),
            "trough_month": min(movements, key=lambda m: m["value"]),
        }

    @staticmethod
    def _movement_bundle_text(window_movements):
        """Plain-text description of within-window monthly movements for evidence."""
        if not window_movements:
            return "No monthly breakdown was available for the selected window."
        lines = []
        for m in window_movements["movements"]:
            pct = (
                f" ({m['month_over_month_pct']:.1f}% vs prior month in window)"
                if m["month_over_month_pct"] is not None
                else ""
            )
            lines.append(
                f"Month {m['month']}: Technical Result {format_financial(m['value'])}{pct}"
            )
        lines.append(
            f"Highest month in window: {window_movements['peak_month']['month']} "
            f"({format_financial(window_movements['peak_month']['value'])})"
        )
        lines.append(
            f"Lowest month in window: {window_movements['trough_month']['month']} "
            f"({format_financial(window_movements['trough_month']['value'])})"
        )
        return "\n".join(lines)

    # =========================================================
    # DRIVER SELECTION
    # =========================================================

    @classmethod
    def _select_material_drivers(
        cls,
        dataframe,
        dimension,
        parent_change,
        min_drivers=None,
        target=None,
        max_drivers=None,
    ):
        """
        Select material contributors in the direction of the parent move.

        Selection rule:
          1. keep only contributors whose TR change has the same sign as
             the parent movement;
          2. sort by absolute TR change descending;
          3. keep rows until cumulative absolute contribution reaches 80%
             of the parent movement;
          4. always keep at least three rows when three aligned rows exist;
          5. cap the result at MAX_DRIVERS.

        This is intentionally deterministic; no LLM decides which driver
        gets selected.
        """
        if dataframe is None or dataframe.empty:
            return [], {
                "target": target or cls.COVERAGE_TARGET,
                "coverage": 0.0,
                "parent_change": parent_change,
                "selected_change_sum": 0.0,
                "aligned_change_sum": 0.0,
                "message": "No data available for driver selection.",
            }

        dimension_col = cls._find_column(dataframe, [dimension])
        change_col = cls._find_change_column(dataframe)
        if dimension_col is None or change_col is None:
            return [], {
                "target": target or cls.COVERAGE_TARGET,
                "coverage": 0.0,
                "parent_change": parent_change,
                "selected_change_sum": 0.0,
                "aligned_change_sum": 0.0,
                "message": "Required dimension or Technical Result change column is unavailable.",
            }

        target = target if target is not None else cls.COVERAGE_TARGET
        min_drivers = min_drivers if min_drivers is not None else cls.MIN_DRIVERS
        max_drivers = max_drivers if max_drivers is not None else cls.MAX_DRIVERS

        df = dataframe[[dimension_col, change_col]].copy()
        df[change_col] = cls._numeric(df[change_col])
        df = df.dropna(subset=[change_col])
        df = df[df[dimension_col].notna()].copy()
        if df.empty:
            return [], {
                "target": target,
                "coverage": 0.0,
                "parent_change": parent_change,
                "selected_change_sum": 0.0,
                "aligned_change_sum": 0.0,
                "message": "No valid dimensional changes were available.",
            }

        # If the SQL ever returns duplicate dimension values, aggregate them.
        df = (
            df.groupby(dimension_col, dropna=False, as_index=False)[change_col]
            .sum()
        )

        direction = 1 if parent_change >= 0 else -1
        if parent_change == 0:
            # No meaningful parent direction. Select largest absolute movers.
            aligned = df[df[change_col] != 0].copy()
        elif direction < 0:
            aligned = df[df[change_col] < 0].copy()
        else:
            aligned = df[df[change_col] > 0].copy()

        if aligned.empty:
            return [], {
                "target": target,
                "coverage": 0.0,
                "parent_change": parent_change,
                "selected_change_sum": 0.0,
                "aligned_change_sum": 0.0,
                "message": "No contributors aligned with the parent movement were found.",
            }

        aligned["_abs_change"] = aligned[change_col].abs()
        aligned = aligned.sort_values("_abs_change", ascending=False).reset_index(drop=True)

        parent_abs = abs(float(parent_change))
        aligned_abs = float(aligned["_abs_change"].sum())

        selected_rows = []
        cumulative_abs = 0.0

        for _, row in aligned.iterrows():
            if len(selected_rows) >= max_drivers:
                break

            selected_rows.append(row)
            cumulative_abs += float(row["_abs_change"])

            reached_target = parent_abs > 0 and cumulative_abs >= target * parent_abs
            reached_minimum = len(selected_rows) >= min_drivers

            if reached_target and reached_minimum:
                break

        selected = []
        for row in selected_rows:
            selected.append(
                {
                    "dimension": dimension,
                    "driver": str(row[dimension_col]),
                    "change": float(row[change_col]),
                    "direction": "positive" if row[change_col] > 0 else "negative",
                    "absolute_change": float(row["_abs_change"]),
                }
            )

        coverage = cumulative_abs / parent_abs if parent_abs > 0 else 0.0
        return selected, {
            "target": target,
            "coverage": coverage,
            "parent_change": float(parent_change),
            "selected_change_sum": float(sum(x["change"] for x in selected)),
            "aligned_change_sum": float(aligned[change_col].sum()),
            "aligned_absolute_change": aligned_abs,
            "selected_absolute_change": cumulative_abs,
            "direction": "positive" if parent_change > 0 else "negative" if parent_change < 0 else "neutral",
            "message": (
                f"Selected {len(selected)} contributor(s), covering {coverage * 100:.1f}% "
                f"of the parent Technical Result movement."
            ),
        }

    @classmethod
    def _select_absolute_movers(cls, dataframe, dimension, max_drivers=None):
        """Select the largest absolute contributors (single-window mode).

        In window mode there is no parent movement sign to align with, so we
        select purely by absolute Technical Result magnitude within the window.
        """
        if dataframe is None or dataframe.empty:
            return [], {
                "target": cls.COVERAGE_TARGET,
                "coverage": 0.0,
                "parent_change": None,
                "selected_change_sum": 0.0,
                "aligned_change_sum": 0.0,
                "message": "No data available for driver selection.",
            }
        dimension_col = cls._find_column(dataframe, [dimension])
        change_col = cls._find_change_column(dataframe)
        if dimension_col is None or change_col is None:
            return [], {
                "target": cls.COVERAGE_TARGET,
                "coverage": 0.0,
                "parent_change": None,
                "selected_change_sum": 0.0,
                "aligned_change_sum": 0.0,
                "message": "Required dimension or Technical Result column is unavailable.",
            }
        max_drivers = max_drivers if max_drivers is not None else cls.MAX_DRIVERS
        df = dataframe[[dimension_col, change_col]].copy()
        df[change_col] = cls._numeric(df[change_col])
        df = df.dropna(subset=[change_col])
        df = df[df[dimension_col].notna()].copy()
        if df.empty:
            return [], {
                "target": cls.COVERAGE_TARGET,
                "coverage": 0.0,
                "parent_change": None,
                "selected_change_sum": 0.0,
                "aligned_change_sum": 0.0,
                "message": "No valid dimensional values were available.",
            }
        df = df.groupby(dimension_col, dropna=False, as_index=False)[change_col].sum()
        df["_abs"] = df[change_col].abs()
        df = df.sort_values("_abs", ascending=False).reset_index(drop=True)
        selected_rows = df.head(max_drivers)
        selected = []
        for _, row in selected_rows.iterrows():
            selected.append(
                {
                    "dimension": dimension,
                    "driver": str(row[dimension_col]),
                    "change": float(row[change_col]),
                    "direction": "positive" if row[change_col] > 0 else "negative" if row[change_col] < 0 else "neutral",
                    "absolute_change": float(row["_abs"]),
                }
            )
        total = float(df[change_col].sum())
        selected_sum = float(sum(x["change"] for x in selected))
        return selected, {
            "target": cls.COVERAGE_TARGET,
            "coverage": (selected_sum / total) if total != 0 else 0.0,
            "parent_change": None,
            "selected_change_sum": selected_sum,
            "aligned_change_sum": total,
            "message": (
                f"Selected {len(selected)} largest in-window contributor(s) by absolute magnitude."
            ),
        }

    @classmethod
    def _select_all_categories(cls, dataframe, dimension="Renewal_Category"):
        """Return all available renewal categories, sorted by absolute TR change."""
        if dataframe is None or dataframe.empty:
            return []
        dim_col = cls._find_column(dataframe, [dimension])
        change_col = cls._find_change_column(dataframe)
        if not dim_col or not change_col:
            return []
        df = dataframe[[dim_col, change_col]].copy()
        df[change_col] = cls._numeric(df[change_col])
        df = df.dropna(subset=[dim_col, change_col])
        df = df.groupby(dim_col, as_index=False)[change_col].sum()
        df["_abs"] = df[change_col].abs()
        df = df.sort_values("_abs", ascending=False)
        return [
            {
                "dimension": dimension,
                "driver": str(row[dim_col]),
                "change": float(row[change_col]),
                "direction": "positive" if row[change_col] > 0 else "negative" if row[change_col] < 0 else "neutral",
                "absolute_change": float(row["_abs"]),
            }
            for _, row in df.iterrows()
        ]

    # =========================================================
    # COMPONENT METRICS
    # =========================================================

    @classmethod
    def _metric_snapshot(cls, dataframe):
        """Return current, previous and change values for useful financial metrics."""
        if dataframe is None or dataframe.empty:
            return {}

        out = {}
        for metric in ["Premium", "Claims", "Commission", "Expenses", "Technical_Result"]:
            current = cls._find_column(dataframe, [f"{metric}_Current"])
            previous = cls._find_column(dataframe, [f"{metric}_Previous"])
            change = cls._find_column(dataframe, [f"{metric}_Change"])
            if current or previous or change:
                values = {
                    "current": cls._safe_float(dataframe[current].iloc[0]) if current else None,
                    "previous": cls._safe_float(dataframe[previous].iloc[0]) if previous else None,
                    "change": cls._safe_float(dataframe[change].iloc[0]) if change else None,
                }
                if values["change"] is None and values["current"] is not None and values["previous"] is not None:
                    values["change"] = values["current"] - values["previous"]
                out[metric] = values
        return out

    # =========================================================
    # SQL EXECUTION
    # =========================================================

    def _execute_sql(self, **kwargs):
        sql = self.sql_agent.generate_sql(**kwargs)

        # SQL remains backend-only. It is stored/logged, not sent to the UI.
        print("\n================ GENERATED SQL ================")
        print(sql)
        print("================================================\n")

        valid, message = self.sql_validator.validate(sql)
        if not valid:
            return {
                "success": False,
                "message": message,
                "sql": sql,
                "data": None,
                "execution_time": 0,
            }

        execution = self.sql_executor.execute(sql)
        if not execution["success"]:
            return {
                "success": False,
                "message": execution["message"],
                "sql": sql,
                "data": None,
                "execution_time": execution.get("execution_time", 0),
            }

        return {
            "success": True,
            "message": "",
            "sql": sql,
            "data": execution["data"],
            "execution_time": execution.get("execution_time", 0),
        }

    def _run_investigation(
        self,
        number,
        level,
        question,
        region,
        market_unit,
        period=None,
        focus_dimension=None,
        focus_value=None,
        context_filters=None,
        progress_callback=None,
        sql_history=None,
        result_history=None,
        investigation_history=None,
    ):
        """Execute one SQL investigation and emit a clean UI event."""
        sql_history = sql_history if sql_history is not None else []
        result_history = result_history if result_history is not None else []
        investigation_history = investigation_history if investigation_history is not None else []

        self._send_progress(
            progress_callback,
            {
                "type": "investigation_start",
                "investigation": number,
                "level": level,
                "question": question,
                "focus_dimension": focus_dimension,
                "focus_value": focus_value,
            },
        )
        self._send_progress(
            progress_callback,
            {
                "type": "sql_generating",
                "investigation": number,
                "level": level,
            },
        )

        result = self._execute_sql(
            question=question,
            region=region,
            market_unit=market_unit,
            investigation_level=level,
            focus_dimension=focus_dimension,
            focus_value=focus_value,
            context_filters=context_filters,
            period=period,
        )

        if not result["success"]:
            self._send_progress(
                progress_callback,
                {
                    "type": "error",
                    "investigation": number,
                    "level": level,
                    "message": result["message"],
                },
            )
            return None

        self._send_progress(
            progress_callback,
            {
                "type": "sql_executed",
                "investigation": number,
                "level": level,
                "execution_time": result["execution_time"],
            },
        )

        dataframe = result["data"]
        if dataframe is None or dataframe.empty:
            self._send_progress(
                progress_callback,
                {
                    "type": "error",
                    "investigation": number,
                    "level": level,
                    "message": "No data returned for this investigation.",
                },
            )
            return None

        sql_history.append(
            {
                "investigation": number,
                "question": question,
                "sql": result["sql"],
            }
        )
        result_history.append(
            {
                "investigation": number,
                "question": question,
                "data": dataframe.copy(),
                "level": level,
                "focus_dimension": focus_dimension,
                "focus_value": focus_value,
                "context_filters": context_filters or {},
            }
        )

        self._send_progress(
            progress_callback,
            {
                "type": "result",
                "investigation": number,
                "level": level,
                "question": question,
                "data": dataframe.copy(),
                "rows": len(dataframe),
                "execution_time": result["execution_time"],
                "focus_dimension": focus_dimension,
                "focus_value": focus_value,
            },
        )

        return result

    # =========================================================
    # RECONCILIATION / COVERAGE
    # =========================================================

    @classmethod
    def _reconciliation(cls, dataframe, parent_change):
        change_col = cls._find_change_column(dataframe)
        if dataframe is None or dataframe.empty or change_col is None:
            return {
                "reconciles": False,
                "parent_change": parent_change,
                "child_sum": None,
                "unallocated_change": None,
                "coverage_percent": None,
                "message": "Child-level Technical Result changes could not be reconciled.",
            }

        changes = cls._numeric(dataframe[change_col]).dropna()
        if changes.empty or parent_change is None:
            return {
                "reconciles": False,
                "parent_change": parent_change,
                "child_sum": None,
                "unallocated_change": None,
                "coverage_percent": None,
                "message": "No numeric child-level changes were available.",
            }

        child_sum = float(changes.sum())
        unallocated = float(parent_change - child_sum)
        denominator = max(abs(float(parent_change)), 1.0)
        reconciles = abs(unallocated) / denominator <= cls.RECONCILIATION_TOLERANCE
        coverage = (child_sum / parent_change * 100.0) if abs(parent_change) > 1e-9 else None

        return {
            "reconciles": reconciles,
            "parent_change": float(parent_change),
            "child_sum": child_sum,
            "unallocated_change": unallocated,
            "coverage_percent": coverage,
            "message": (
                "Child-level changes reconcile to the parent movement."
                if reconciles
                else f"Child-level changes do not fully reconcile; unallocated movement is {format_financial(unallocated)}."
            ),
        }

    # =========================================================
    # COMMENTARY EVIDENCE
    # =========================================================

    @staticmethod
    def _compact_dataframe(dataframe, max_rows=20):
        if dataframe is None or dataframe.empty:
            return "No rows returned."
        df = dataframe.head(max_rows).copy()
        for col in df.select_dtypes(include="number").columns:
            df[col] = df[col].round(2)
        try:
            return df.to_markdown(index=False)
        except Exception:
            return df.to_string(index=False)

    @classmethod
    def _driver_lines(cls, selected, coverage):
        if not selected:
            return "None selected."
        lines = [
            f"Selected contributors cover {coverage.get('coverage', 0) * 100:.1f}% of the parent Technical Result movement."
        ]
        for item in selected:
            lines.append(
                f"- {item['driver']}: {format_financial(item['change'])} ({item['direction']})"
            )
        return "\n".join(lines)

    @classmethod
    def _build_commentary_evidence(
        cls,
        period,
        region,
        market_unit,
        overall_change,
        quarter_dataframe,
        quarter_metrics,
        mblob_results,
        portfolio_results,
        cedent_results,
        renewal_results,
    ):
        parts = []
        labels = cls._period_labels(period)
        current_label = labels["current_label"]
        previous_label = labels["previous_label"]

        parts.append(
            f"MARKET CONTEXT\nRegion: {region}\nMarket Unit: {market_unit}\n"
            f"Current period: {current_label}\nPrevious period: {previous_label}\n"
            f"Overall Technical Result change: {format_financial(overall_change)}\n"
            f"Overall movement: {cls._movement_text(overall_change)}"
        )

        parts.append(
            "QUARTER FINANCIAL CONTEXT\n"
            + cls._format_metric_evidence(quarter_metrics)
        )
        parts.append(
            "QUARTER RESULT TABLE\n" + cls._compact_dataframe(quarter_dataframe, 5)
        )

        parts.append("MAIN LINE OF BUSINESS DRIVERS")
        for item in mblob_results:
            parts.append(
                f"MLOB DRIVER SELECTION\n"
                f"{item['dimension']} = {item['driver']}\n"
                f"Change: {format_financial(item['change'])}\n"
                f"Direction: {item['direction']}\n"
                f"Coverage: {item['coverage'] * 100:.1f}% of market TR movement"
            )

        for item in portfolio_results:
            parts.append(
                f"UW PORTFOLIO ANALYSIS\n"
                f"MLOB: {item['parent_value']}\n"
                f"Parent MLOB change: {format_financial(item.get('parent_change'))}\n"
                f"Selected portfolio: {item['driver']}\n"
                f"Portfolio change: {format_financial(item['change'])}\n"
                f"Coverage within MLOB: {item['coverage'] * 100:.1f}%\n"
                f"Result table:\n{cls._compact_dataframe(item['data'], 12)}"
            )

        for item in cedent_results:
            parts.append(
                f"CEDENT ANALYSIS\n"
                f"MLOB: {item['mlob']}\n"
                f"UW Portfolio: {item['portfolio']}\n"
                f"Parent portfolio change: {format_financial(item['parent_change'])}\n"
                f"Selected cedent: {item['driver']}\n"
                f"Cedent change: {format_financial(item['change'])}\n"
                f"Coverage within portfolio: {item['coverage'] * 100:.1f}%\n"
                f"Result table:\n{cls._compact_dataframe(item['data'], 12)}"
            )

        for item in renewal_results:
            parts.append(
                f"RENEWAL / NEW BUSINESS / CANCELLED ANALYSIS\n"
                f"MLOB: {item['mlob']}\n"
                f"UW Portfolio: {item['portfolio']}\n"
                f"Cedent: {item['cedent']}\n"
                f"Parent cedent change: {format_financial(item['parent_change'])}\n"
                f"All available business categories are retained below; they are not reduced to a single category.\n"
                f"Result table:\n{cls._compact_dataframe(item['data'], 12)}"
            )

        parts.append(
            "INTERPRETATION RULES FOR COMMENTARY\n"
            "Use only the retrieved financial evidence. Distinguish observed movement from inferred cause. "
            "Use Premium, Claims, Commission and Expenses changes to explain the financial context when present. "
            "Use Renewal_Category rows to determine whether New Business, Renewal or Cancelled activity materially "
            "contributed. Do not claim pricing, market conditions, underwriting strategy, catastrophe events, claim "
            "severity or other causes unless the supplied evidence directly supports them."
        )

        return "\n\n".join(parts)

    @classmethod
    def _build_window_evidence(
        cls,
        period,
        region,
        market_unit,
        overall_tr,
        window_dataframe,
        window_metrics,
        window_movements,
        mlob_results,
        portfolio_results,
        cedent_results,
        renewal_results,
    ):
        """Evidence for the date-range (window) commentary.

        The date-range mode is an investigation *of the selected period*:
        it reports the financial activity within [start, end], the material
        activity at each drill-down level (MLOB -> Portfolio -> Cedent ->
        Renewal/New Business/Cancelled), and the within-window monthly
        movements. It NEVER references a comparison period.
        """
        parts = []
        labels = cls._period_labels(period)
        window_label = labels["current_label"]

        parts.append(
            f"MARKET CONTEXT\nRegion: {region}\nMarket Unit: {market_unit}\n"
            f"Selected window: {window_label}\n"
            f"Technical Result within the window: {format_financial(overall_tr)}\n"
            f"Within-window financial activity is reported below."
        )
        parts.append(
            "WINDOW FINANCIAL CONTEXT\n"
            "The figures below are the totals recorded within the selected window.\n"
            + cls._format_metric_evidence(window_metrics)
        )
        parts.append(
            "WINDOW RESULT TABLE\n" + cls._compact_dataframe(window_dataframe, 5)
        )
        parts.append("WITHIN-WINDOW MONTHLY MOVEMENT\n" + cls._movement_bundle_text(window_movements))

        parts.append("MAIN LINE OF BUSINESS ACTIVITY")
        for item in mlob_results:
            parts.append(
                f"MLOB ACTIVITY\n"
                f"{item['dimension']} = {item['driver']}\n"
                f"Technical Result in window: {format_financial(item['change'])}\n"
                f"Direction: {item['direction']}\n"
                f"Share of market TR activity: {item['coverage'] * 100:.1f}%"
            )

        for item in portfolio_results:
            parts.append(
                f"UW PORTFOLIO ACTIVITY\n"
                f"MLOB: {item['parent_value']}\n"
                f"Parent MLOB TR in window: {format_financial(item.get('parent_change'))}\n"
                f"Portfolio: {item['driver']}\n"
                f"Portfolio TR in window: {format_financial(item['change'])}\n"
                f"Share within MLOB: {item['coverage'] * 100:.1f}%\n"
                f"Result table:\n{cls._compact_dataframe(item['data'], 12)}"
            )

        for item in cedent_results:
            parts.append(
                f"CEDENT ACTIVITY\n"
                f"MLOB: {item['mlob']}\n"
                f"UW Portfolio: {item['portfolio']}\n"
                f"Parent portfolio TR in window: {format_financial(item['parent_change'])}\n"
                f"Cedent: {item['driver']}\n"
                f"Cedent TR in window: {format_financial(item['change'])}\n"
                f"Share within portfolio: {item['coverage'] * 100:.1f}%\n"
                f"Result table:\n{cls._compact_dataframe(item['data'], 12)}"
            )

        for item in renewal_results:
            parts.append(
                f"RENEWAL / NEW BUSINESS / CANCELLED ACTIVITY\n"
                f"MLOB: {item['mlob']}\n"
                f"UW Portfolio: {item['portfolio']}\n"
                f"Cedent: {item['cedent']}\n"
                f"Parent cedent TR in window: {format_financial(item['parent_change'])}\n"
                f"All available business categories are retained below.\n"
                f"Result table:\n{cls._compact_dataframe(item['data'], 12)}"
            )

        parts.append(
            "INTERPRETATION RULES FOR COMMENTARY\n"
            "Describe the financial activity observed WITHIN the selected window. "
            "Explain which months or sub-periods within the window show the largest "
            "movements, and which Main Line of Business, UW Portfolio, Cedent and "
            "business category (New Business/Renewal/Cancelled) drove them. "
            "Do NOT compare the selected window against any other period and do not "
            "invent a root cause the evidence does not support."
        )

        return "\n\n".join(parts)

    @staticmethod
    def _format_metric_evidence(metrics):
        if not metrics:
            return "No component metrics were available."
        lines = []
        for metric, values in metrics.items():
            lines.append(
                f"{metric}: current {format_financial(values.get('current'))}; "
                f"previous {format_financial(values.get('previous'))}; "
                f"change {format_financial(values.get('change'))}"
            )
        return "\n".join(lines)

    # =========================================================
    # FINAL COMMENTARY
    # =========================================================

    def _generate_commentary(
        self,
        question,
        region,
        market_unit,
        period,
        evidence,
    ):
        labels = self._period_labels(period)
        current_label = labels["current_label"]
        previous_label = labels["previous_label"]
        comparison_label = labels["comparison_label"]

        prompt = f"""
You are a senior P&C Finance analyst writing an executive commentary for management.

Market Unit: {market_unit}
Region: {region}
Current period: {current_label}
Previous period: {previous_label}

The analyst has already performed deterministic period-over-period driver analysis.
Your task is to turn the supplied evidence into a clear business explanation.

EVIDENCE
========
{evidence}
========

WRITE THE COMMENTARY

Write 4 to 6 short paragraphs.

Paragraph 1: State the overall Technical Result movement, current and previous TR when available,
and the most important financial context from Premium, Claims, Commission and Expenses.

Paragraph 2: Explain the material Main Line of Business drivers. Mention multiple selected MLOBs,
not only the largest one, when they collectively explain a substantial share of the movement.

Paragraph 3: Explain the material UW Portfolios and show which MLOB each belongs to.

Paragraph 4: Explain the material Cedents and which MLOB and UW Portfolio each belongs to.

Paragraph 5: Explain the Renewal/New Business/Cancelled pattern. Explicitly distinguish whether
the observed movement is associated with new business loss/gain, renewal movement, cancellations,
or a combination. Use the actual category changes.

Final paragraph: Give a practical management recommendation grounded in the observed evidence.
For example, if premium contracted while claims also fell, explain that lower claims partially offset
premium erosion rather than claiming that claims were "low" without evidence. If New Business fell,
recommend investigating the new-business pipeline/retention or portfolio-level business opportunity,
but do not invent the reason for the fall. If claims increased materially, identify claims as a key
observed pressure. Recommendations must be proportional to the evidence.

IMPORTANT ANALYTICAL RULES
1. The selected drivers were chosen using an 80% cumulative absolute-contribution rule. Preserve that
   multi-driver view in the commentary.
2. Do not collapse several drivers into one generic statement.
3. Never invent a root cause that is not in the evidence.
4. Never imply that Renewal is inherently good or Cancelled is inherently bad.
5. Do not say "the market is good/bad" unless the evidence supports a balanced conclusion. Prefer
   precise wording such as "Technical Result improved despite lower premium because claims declined"
   when the supplied numbers support it.
6. Financial values should be expressed in readable units such as $16.22M, -$7.39M and 18.69M.
7. Do not repeat the same number unnecessarily.

OUTPUT FORMAT — VERY IMPORTANT
Return plain text only.
Do NOT use Markdown.
Do NOT use #, *, **, _, __, backticks, bullet points, numbered lists, tables, LaTeX, HTML, or emojis.
Do NOT use mathematical notation such as M_{{x}} or $...$ for formatting.
Use normal words and currency values directly.
Start with exactly this one-line title:
Executive Commentary – {market_unit} | {comparison_label}
Then a blank line and the paragraphs.
Do not add any other heading.
Do not mention that you are an AI.
Do not mention SQL or the investigation process.
"""

        response = self.llm.generate(prompt)
        print("\n================ RAW EXECUTIVE COMMENTARY ================")
        print(response)
        print("===========================================================\n")
        return clean_commentary_text(response)

    # =========================================================
    # POLISHED EXECUTIVE COMMENTARY (STORY)
    # =========================================================

    def polish_commentary(
        self,
        region,
        market_unit,
        comparison_label,
        market_unit_kpis,
        detailed_commentary,
    ):
        """
        Turn the market-level KPIs and the detailed driver analysis into a
        polished, story-style executive commentary a reader can grasp quickly.

        The detailed analysis is used as the ground truth so the polished
        version never contradicts the numeric drill-down. The KPIs form the
        crisp market snapshot (premium, Technical Result, TCR and new-business
        expected figures) that opens the story.
        """
        kpi_lines = []
        if market_unit_kpis:
            for label, value in market_unit_kpis.items():
                kpi_lines.append(f"- {label}: {str(value).strip()[:100]}")
        kpi_text = "\n".join(kpi_lines) if kpi_lines else "No KPIs available."

        if not detailed_commentary:
            detailed_commentary = "No detailed analysis available."

        prompt = f"""
You are an executive business storyteller, not a data summarizer.
Transform the analytical output below into a short, clear Executive Commentary
that explains what happened in this market and why.
Write for a business user who may not be an insurance/reinsurance expert.
The reader should understand the story without needing to interpret tables or
numbers.

Market Unit: {market_unit}
Region: {region}
Comparison period: {comparison_label}

MARKET-LEVEL KPIs (dashboard snapshot)
=======================================
{kpi_text}
=======================================

DETAILED ANALYSIS (ground truth; do not contradict it)
=======================================
{detailed_commentary}
=======================================

Follow this structure naturally:

1. Start with the current quarter's overall performance and compare it with the
   previous quarter.
2. Explain the main reason for the change.
3. Identify the 2-3 Lines of Business that contributed most and briefly explain
   what happened within them.
4. Mention portfolio or account/cedent-level drivers only when they materially
   explain the movement. Do not list every portfolio or cedent.
5. Explain whether the change is mainly related to new business, renewals,
   cancellations, claims, or premium movement.
6. End with a concise business takeaway or area that deserves attention.

WRITING RULES
- Tell a story, do not reproduce the analysis.
- Prioritize meaning over numbers. Use numbers only when they help explain the
  story. Format values in readable units such as $1.23B, $45.6M and 79.3%.
- Use simple, natural business language. Avoid jargon where possible; if an
  insurance term is necessary, make its meaning clear from context.
- Do not use phrases such as "the data indicates", "signalling that",
  "collectively contributed", "material deterioration" or "underwriting
  criteria" unless clearly supported and necessary.
- Do not list long sequences of portfolios or cedents.
- Do not repeat information already obvious from the KPI cards.
- Keep the commentary concise: 3-5 short paragraphs, approximately 250-350
  words maximum.
- Use clear transitions such as "The main concern...", "Most of the decline
  came from...", "At the portfolio level..." and "Overall...".
- Make the commentary understandable to someone seeing the market for the
  first time.
- Be balanced: clearly distinguish between what is performing well and what
  requires attention.
- Do not exaggerate a decline or describe a market as weak if the underlying
  KPIs show it remains profitable.
- Do not invent causes, recommendations, relationships, or facts that are not
  present in the analytical input. Do not make assumptions beyond the supplied
  analysis.
- Preserve all important figures accurately. Never change, calculate, or infer
  a number unless it is explicitly provided in the input.

Above all, answer this question through the narrative:

"What happened in this market this quarter, what caused it, where did it
happen, and what should the reader pay attention to?"

FORMATTING
- Do not use Markdown, bullets, asterisks, backticks, tables, headings or
  emojis. Return plain text only.
- Start with exactly this one-line title:
Executive Commentary – {market_unit} | {comparison_label}
Then a blank line, then the paragraphs.
- Do not say "the AI", "the model" or mention SQL/agents.
"""

        response = self.llm.generate(prompt, temperature=0.3)
        print("\n================ POLISHED EXECUTIVE COMMENTARY ================")
        print(response)
        print("===============================================================\n")
        return clean_commentary_text(response)

    def _generate_window_commentary(
        self,
        region,
        market_unit,
        period,
        overall_tr,
        window_movements,
        evidence,
    ):
        """Windowing executive commentary.

        This is an investigation of the selected date range: it explains what
        financial activity occurred within the window and the material drivers
        at each level. It NEVER compares the window against another period.
        """
        labels = self._period_labels(period)
        window_label = labels["current_label"]
        movement_text = self._movement_bundle_text(window_movements)

        prompt = f"""
You are a senior P&C Finance analyst writing an executive commentary for management
about financial activity within a specific date range.

Market Unit: {market_unit}
Region: {region}
Selected window: {window_label}

This is a single-window investigation. The figures represent the financial activity
recorded WITHIN the selected date range only. Do not compare this window against any
previous, next or equivalent period. Investigate what happened inside this window.

EVIDENCE
========
{evidence}
========

WRITE THE COMMENTARY

Write 4 to 6 short paragraphs.

Paragraph 1: State the overall Technical Result within the window and the most
important financial context from Premium, Claims, Commission and Expenses recorded
in that range.

Paragraph 2: Describe the within-window monthly movements, calling out the months
with the largest positive or negative Technical Result within the range. Use only
the actual monthly figures. {movement_text}

Paragraph 3: Explain the Main Lines of Business that drove the activity within the
window. Mention multiple MLOBs when they collectively explain a substantial share.

Paragraph 4: Explain the material UW Portfolios and Cedents and which MLOB and
UW Portfolio each belongs to.

Paragraph 5: Explain the Renewal/New Business/Cancelled pattern within the window.
Distinguish whether the activity is associated with new business, renewals,
cancellations, or a combination.

Final paragraph: Give a practical management recommendation grounded in the observed
in-window evidence.

IMPORTANT ANALYTICAL RULES
1. Do not say "versus", "compared with", "prior period" or "previous period".
   This is not a comparison.
2. Do not invent a root cause that is not in the evidence.
3. Financial values should be expressed in readable units such as $16.22M or -$7.39M.
4. Say "within the selected period" when describing the analysis scope.

OUTPUT FORMAT — VERY IMPORTANT
Return plain text only.
Do NOT use Markdown.
Do NOT use #, *, **, _, __, backticks, bullet points, numbered lists, tables, LaTeX, HTML, or emojis.
Do NOT use mathematical notation.
Use normal words and currency values directly.
Start with exactly this one-line title:
Executive Commentary – {market_unit} | {window_label}
Then a blank line and the paragraphs.
Do not add any other heading.
Do not mention that you are an AI.
Do not mention SQL or the investigation process.
"""

        response = self.llm.generate(prompt)
        print("\n================ WINDOW EXECUTIVE COMMENTARY ================")
        print(response)
        print("=============================================================\n")
        return clean_commentary_text(response)

    def _polish_window_commentary(
        self,
        region,
        market_unit,
        window_label,
        market_unit_kpis,
        detailed_commentary,
    ):
        """Window-specific polished commentary (date-range / single-window story)."""
        kpi_lines = []
        if market_unit_kpis:
            for label, value in market_unit_kpis.items():
                kpi_lines.append(f"- {label}: {str(value).strip()[:100]}")
        kpi_text = "\n".join(kpi_lines) if kpi_lines else "No KPIs available."

        if not detailed_commentary:
            detailed_commentary = "No detailed analysis available."

        prompt = f"""
You are an executive business storyteller, not a data summarizer.
Transform the analytical output below into a short, clear Executive Commentary
that explains what happened within the selected date range and why.
Write for a business user who may not be an insurance/reinsurance expert.
The reader should understand the story without needing to interpret tables or
numbers.

Market Unit: {market_unit}
Region: {region}
Selected period: {window_label}

The analysis below is a single-window investigation: it describes financial
activity recorded WITHIN the selected date range only. Do NOT compare it against
any other period.

MARKET-LEVEL KPIs (dashboard snapshot)
=======================================
{kpi_text}
=======================================

DETAILED ANALYSIS (ground truth; do not contradict it)
=======================================
{detailed_commentary}
=======================================

Follow this structure naturally:

1. Start by describing the overall financial activity observed within the
   selected period.
2. Explain the main driver(s) of that activity.
3. Identify the 2-3 Lines of Business that contributed most and briefly explain
   what happened within them.
4. Mention portfolio or account/cedent-level drivers only when they materially
   explain the activity. Do not list every portfolio or cedent.
5. Explain whether the activity is mainly related to new business, renewals,
   cancellations, claims, or premium movement.
6. End with a concise business takeaway or area that deserves attention.

WRITING RULES
- Tell a story, do not reproduce the analysis.
- Prioritize meaning over numbers. Use numbers only when they help explain the
  story. Format values in readable units such as $1.23B, $45.6M and 79.3%.
- Use simple, natural business language.
- Do NOT use the words "versus", "compared with", "prior period" or "previous
  period", and do not reference any period outside the selected window.
- Do not invent causes, recommendations, relationships, or facts that are not
  present in the analytical input.
- Keep the commentary concise: 3-5 short paragraphs, approximately 250-350 words
  maximum.

Above all, answer this question through the narrative:

"What financial activity happened within this selected date range, what drove it,
where did it happen, and what should the reader pay attention to?"

FORMATTING
- Do not use Markdown, bullets, asterisks, backticks, tables, headings or
  emojis. Return plain text only.
- Start with exactly this one-line title:
Executive Commentary – {market_unit} | {window_label}
Then a blank line, then the paragraphs.
- Do not say "the AI", "the model" or mention SQL/agents.
"""

        response = self.llm.generate(prompt, temperature=0.3)
        print("\n================ POLISHED WINDOW COMMENTARY ================")
        print(response)
        print("=============================================================\n")
        return clean_commentary_text(response)

    # =========================================================
    # MAIN ANALYSIS
    # =========================================================

    def analyze(
        self,
        question,
        region,
        market_unit,
        driver1=None,
        driver2=None,
        period=None,
        progress_callback=None,
    ):
        del driver1, driver2  # kept only for backwards compatibility

        start_time = time.time()
        if period is None:
            period = self.get_current_period()
        labels = self._period_labels(period)
        comparison_label = labels["comparison_label"]
        period_text = comparison_label

        sql_history = []
        result_history = []
        investigation_history = []
        next_number = 1

        self._send_progress(
            progress_callback,
            {
                "type": "period",
                "current_year": period["current_year"],
                "current_quarter": period["current_quarter"],
                "previous_year": period["previous_year"],
                "previous_quarter": period["previous_quarter"],
                "label": comparison_label,
            },
        )

        # ---------------------------------------------------------
        # 1. Overall period comparison
        # ---------------------------------------------------------
        quarter_question = (
            f"Compare Technical Result, Premium, Claims, Commission and Expenses for "
            f"{comparison_label} for the selected market."
        )
        quarter_result = self._run_investigation(
            number=next_number,
            level="Quarter",
            question=quarter_question,
            region=region,
            market_unit=market_unit,
            period=period,
            progress_callback=progress_callback,
            sql_history=sql_history,
            result_history=result_history,
            investigation_history=investigation_history,
        )
        if quarter_result is None:
            return self._failure("The quarter comparison could not be completed.", sql_history, result_history)

        quarter_df = quarter_result["data"]
        overall_change = self._overall_change(quarter_df)
        direction = self._movement_direction(overall_change)
        self._send_progress(
            progress_callback,
            {
                "type": "overall_movement",
                "change": overall_change,
                "direction": direction,
                "text": self._movement_text(overall_change),
            },
        )
        quarter_metrics = self._metric_snapshot(quarter_df)
        investigation_history.append(
            {
                "investigation": next_number,
                "level": "Quarter",
                "focus_dimension": None,
                "focus_value": None,
                "selected_drivers": [],
                "coverage": 1.0,
                "change": overall_change,
                "direction": direction,
                "evidence_status": "overall_movement",
            }
        )
        next_number += 1

        # ---------------------------------------------------------
        # 2. Main Line of Business drivers
        # ---------------------------------------------------------
        mlob_question = (
            f"Compare Technical Result by Main_Line_of_Business for {comparison_label}. "
            f"Identify material contributors to the overall {format_financial(overall_change)} movement."
        )
        mlob_result = self._run_investigation(
            number=next_number,
            level="Main_Line_of_Business",
            question=mlob_question,
            region=region,
            market_unit=market_unit,
            period=period,
            progress_callback=progress_callback,
            sql_history=sql_history,
            result_history=result_history,
            investigation_history=investigation_history,
        )
        if mlob_result is None:
            return self._failure("Main Line of Business analysis could not be completed.", sql_history, result_history)

        mlob_df = mlob_result["data"]
        selected_mlob, mlob_coverage = self._select_material_drivers(
            mlob_df,
            "Main_Line_of_Business",
            overall_change,
        )
        self._send_driver_event(progress_callback, next_number, "Main_Line_of_Business", selected_mlob, mlob_coverage)
        investigation_history.append(
            {
                "investigation": next_number,
                "level": "Main_Line_of_Business",
                "focus_dimension": None,
                "focus_value": None,
                "selected_drivers": selected_mlob,
                "coverage": mlob_coverage.get("coverage", 0.0),
                "change": overall_change,
                "direction": direction,
                "evidence_status": "80_percent_driver_selection",
            }
        )
        next_number += 1

        mblob_evidence = []
        for driver in selected_mlob:
            mblob_evidence.append(
                {
                    "dimension": "Main_Line_of_Business",
                    "driver": driver["driver"],
                    "change": driver["change"],
                    "direction": driver["direction"],
                    "coverage": mlob_coverage.get("coverage", 0.0),
                }
            )

        # ---------------------------------------------------------
        # 3. UW portfolios for EACH selected MLOB
        # ---------------------------------------------------------
        portfolio_evidence = []
        selected_portfolios = []

        for mlob in selected_mlob:
            value = mlob["driver"]
            q = (
                f"Compare Technical Result by UW_Portfolio within Main_Line_of_Business '{value}' "
                f"for {comparison_label}."
            )
            result = self._run_investigation(
                number=next_number,
                level="UW_Portfolio",
                question=q,
                region=region,
                market_unit=market_unit,
                period=period,
                focus_dimension="Main_Line_of_Business",
                focus_value=value,
                progress_callback=progress_callback,
                sql_history=sql_history,
                result_history=result_history,
                investigation_history=investigation_history,
            )
            if result is None:
                next_number += 1
                continue

            df = result["data"]
            selected, coverage = self._select_material_drivers(
                df,
                "UW_Portfolio",
                mlob["change"],
            )
            self._send_driver_event(progress_callback, next_number, "UW_Portfolio", selected, coverage, parent_value=value)
            investigation_history.append(
                {
                    "investigation": next_number,
                    "level": "UW_Portfolio",
                    "focus_dimension": "Main_Line_of_Business",
                    "focus_value": value,
                    "selected_drivers": selected,
                    "coverage": coverage.get("coverage", 0.0),
                    "change": mlob["change"],
                    "direction": mlob["direction"],
                    "evidence_status": "80_percent_driver_selection",
                }
            )
            next_number += 1

            for portfolio in selected:
                selected_portfolios.append(
                    {
                        **portfolio,
                        "mlob": value,
                        "parent_change": mlob["change"],
                    }
                )
                portfolio_evidence.append(
                    {
                        **portfolio,
                        "parent_value": value,
                        "parent_change": mlob["change"],
                        "coverage": coverage.get("coverage", 0.0),
                        "data": df.copy(),
                    }
                )

        # ---------------------------------------------------------
        # 4. Cedents for EACH selected portfolio
        # ---------------------------------------------------------
        cedent_evidence = []
        selected_cedents = []

        for portfolio in selected_portfolios:
            mlob = portfolio["mlob"]
            portfolio_name = portfolio["driver"]
            q = (
                f"Compare Technical Result by Cedent_Name within Main_Line_of_Business '{mlob}' "
                f"and UW_Portfolio '{portfolio_name}' for {comparison_label}."
            )
            result = self._run_investigation(
                number=next_number,
                level="Cedent_Name",
                question=q,
                region=region,
                market_unit=market_unit,
                period=period,
                context_filters={
                    "Main_Line_of_Business": mlob,
                    "UW_Portfolio": portfolio_name,
                },
                progress_callback=progress_callback,
                sql_history=sql_history,
                result_history=result_history,
                investigation_history=investigation_history,
            )
            if result is None:
                next_number += 1
                continue

            df = result["data"]
            selected, coverage = self._select_material_drivers(
                df,
                "Cedent_Name",
                portfolio["change"],
            )
            self._send_driver_event(
                progress_callback,
                next_number,
                "Cedent_Name",
                selected,
                coverage,
                parent_value=portfolio_name,
            )
            investigation_history.append(
                {
                    "investigation": next_number,
                    "level": "Cedent_Name",
                    "focus_dimension": "UW_Portfolio",
                    "focus_value": portfolio_name,
                    "parent_mlob": mlob,
                    "selected_drivers": selected,
                    "coverage": coverage.get("coverage", 0.0),
                    "change": portfolio["change"],
                    "direction": portfolio["direction"],
                    "evidence_status": "80_percent_driver_selection",
                }
            )
            next_number += 1

            for cedent in selected:
                selected_cedents.append(
                    {
                        **cedent,
                        "mlob": mlob,
                        "portfolio": portfolio_name,
                        "parent_change": portfolio["change"],
                    }
                )
                cedent_evidence.append(
                    {
                        **cedent,
                        "mlob": mlob,
                        "portfolio": portfolio_name,
                        "parent_change": portfolio["change"],
                        "coverage": coverage.get("coverage", 0.0),
                        "data": df.copy(),
                    }
                )

        # ---------------------------------------------------------
        # 5. Renewal/New Business/Cancelled for EACH selected cedent
        # ---------------------------------------------------------
        renewal_evidence = []

        # Deduplicate the selected paths before querying.
        seen = set()
        for cedent in selected_cedents:
            key = (cedent["mlob"], cedent["portfolio"], cedent["driver"])
            if key in seen:
                continue
            seen.add(key)

            mlob, portfolio, cedent_name = key
            q = (
                f"Compare Technical Result by Renewal_Category for Cedent_Name '{cedent_name}', "
                f"UW_Portfolio '{portfolio}' and Main_Line_of_Business '{mlob}' for "
                f"{comparison_label}. Show New Business, Renewal and Cancelled activity."
            )
            result = self._run_investigation(
                number=next_number,
                level="Renewal_Category",
                question=q,
                region=region,
                market_unit=market_unit,
                period=period,
                context_filters={
                    "Main_Line_of_Business": mlob,
                    "UW_Portfolio": portfolio,
                    "Cedent_Name": cedent_name,
                },
                progress_callback=progress_callback,
                sql_history=sql_history,
                result_history=result_history,
                investigation_history=investigation_history,
            )
            if result is None:
                next_number += 1
                continue

            df = result["data"]
            categories = self._select_all_categories(df)
            self._send_progress(
                progress_callback,
                {
                    "type": "driver_selected",
                    "investigation": next_number,
                    "level": "Renewal_Category",
                    "drivers": categories,
                    "coverage": 1.0,
                    "selection_rule": "All available business categories retained for interpretation.",
                },
            )
            investigation_history.append(
                {
                    "investigation": next_number,
                    "level": "Renewal_Category",
                    "focus_dimension": "Cedent_Name",
                    "focus_value": cedent_name,
                    "parent_mlob": mlob,
                    "parent_portfolio": portfolio,
                    "selected_drivers": categories,
                    "coverage": 1.0,
                    "change": cedent["change"],
                    "direction": cedent["direction"],
                    "evidence_status": "all_business_categories",
                }
            )
            renewal_evidence.append(
                {
                    "mlob": mlob,
                    "portfolio": portfolio,
                    "cedent": cedent_name,
                    "parent_change": cedent["change"],
                    "data": df.copy(),
                    "categories": categories,
                }
            )
            next_number += 1

        # ---------------------------------------------------------
        # Final evidence and commentary
        # ---------------------------------------------------------
        evidence = self._build_commentary_evidence(
            period=period,
            region=region,
            market_unit=market_unit,
            overall_change=overall_change,
            quarter_dataframe=quarter_df,
            quarter_metrics=quarter_metrics,
            mblob_results=mblob_evidence,
            portfolio_results=portfolio_evidence,
            cedent_results=cedent_evidence,
            renewal_results=renewal_evidence,
        )

        self._send_progress(
            progress_callback,
            {
                "type": "commentary_generating",
                "message": "All material drivers collected. Generating executive commentary...",
            },
        )

        try:
            commentary = self._generate_commentary(
                question=question,
                region=region,
                market_unit=market_unit,
                period=period,
                evidence=evidence,
            )
        except Exception as exc:
            commentary = (
                f"Executive Commentary – {market_unit} | {comparison_label}\n\n"
                f"The Technical Result {self._movement_text(overall_change)} by {format_financial(overall_change)}. "
                f"Detailed commentary generation failed: {exc}"
            )

        self._send_progress(
            progress_callback,
            {
                "type": "commentary_ready",
                "commentary": commentary,
            },
        )

        return {
            "success": True,
            "region": region,
            "market_unit": market_unit,
            "current_year": period["current_year"],
            "current_quarter": period["current_quarter"],
            "previous_year": period["previous_year"],
            "previous_quarter": period["previous_quarter"],
            "period_mode": period.get("mode", "quarter"),
            "period": period_text,
            "overall_change": overall_change,
            "movement_direction": direction,
            "sql_history": sql_history,
            "result_history": result_history,
            "investigation_history": investigation_history,
            "investigations": len(result_history),
            "commentary": commentary,
            "chart": None,
            "rows": len(quarter_df),
            "execution_time": round(time.time() - start_time, 3),
            "driver_summary": {
                "main_line_of_business": selected_mlob,
                "uw_portfolios": selected_portfolios,
                "cedents": selected_cedents,
                "renewal_analyses": renewal_evidence,
            },
        }

    def analyze_window(
        self,
        question,
        region,
        market_unit,
        period,
        progress_callback=None,
    ):
        """Single-window date-range analysis.

        Investigates the financial activity WITHIN [period.current_start,
        period.current_end] only. There is no previous period: the aim is to
        explain what happened inside the selected window, not to compare it
        against another period.

        Flow mirrors analyze() but uses direct window totals (no _Previous)
        so the same result_history/polish path stays compatible downstream.
        """
        start_time = time.time()
        labels = self._period_labels(period)
        window_label = labels["current_label"]

        sql_history = []
        result_history = []
        investigation_history = []
        next_number = 1

        self._send_progress(
            progress_callback,
            {
                "type": "window",
                "current_year": period.get("current_year"),
                "current_quarter": period.get("current_quarter"),
                "previous_year": period.get("previous_year"),
                "previous_quarter": period.get("previous_quarter"),
                "label": window_label,
            },
        )

        # ---------------------------------------------------------
        # 1. Window totals + daily/monthly movement series
        # ---------------------------------------------------------
        window_question = (
            f"Summarize Premium, Claims, Commission, Expenses and Technical Result "
            f"recorded within {window_label} for the selected market."
        )
        window_result = self._run_investigation(
            number=next_number,
            level="Quarter",
            question=window_question,
            region=region,
            market_unit=market_unit,
            period=period,
            progress_callback=progress_callback,
            sql_history=sql_history,
            result_history=result_history,
            investigation_history=investigation_history,
        )
        if window_result is None:
            return self._failure("The window analysis could not be completed.", sql_history, result_history)

        window_df = window_result["data"]
        overall_tr = self._safe_float(window_df["Technical_Result_Current"].iloc[0])
        if overall_tr is None:
            overall_tr = self._overall_change(window_df)
        window_metrics = self._metric_snapshot(window_df)
        investigation_history.append(
            {
                "investigation": next_number,
                "level": "Quarter",
                "focus_dimension": None,
                "focus_value": None,
                "selected_drivers": [],
                "coverage": 1.0,
                "change": overall_tr,
                "direction": self._movement_direction(overall_tr),
                "evidence_status": "window_total",
            }
        )
        next_number += 1

        # Within-window monthly movements (no comparison to any outside period).
        movement_result = self._run_investigation(
            number=next_number,
            level="Movement",
            question=(
                f"Break the Technical Result within {window_label} into monthly buckets "
                f"to detect within-window movements for the selected market."
            ),
            region=region,
            market_unit=market_unit,
            period=period,
            progress_callback=progress_callback,
            sql_history=sql_history,
            result_history=result_history,
            investigation_history=investigation_history,
        )
        window_movements = None
        if movement_result is not None:
            window_movements = self._within_window_movements(movement_result["data"])
        if window_movements:
            investigation_history.append(
                {
                    "investigation": next_number,
                    "level": "Movement",
                    "focus_dimension": None,
                    "focus_value": None,
                    "selected_drivers": [],
                    "coverage": 1.0,
                    "change": overall_tr,
                    "direction": self._movement_direction(overall_tr),
                    "evidence_status": "within_window_movement",
                }
            )
        next_number += 1

        # ---------------------------------------------------------
        # 2. Main Line of Business activity (within-window totals)
        # ---------------------------------------------------------
        mlob_question = (
            f"Summarize Technical Result by Main_Line_of_Business recorded within "
            f"{window_label}. Identify material contributors to the window's "
            f"{format_financial(overall_tr)} Technical Result."
        )
        mlob_result = self._run_investigation(
            number=next_number,
            level="Main_Line_of_Business",
            question=mlob_question,
            region=region,
            market_unit=market_unit,
            period=period,
            progress_callback=progress_callback,
            sql_history=sql_history,
            result_history=result_history,
            investigation_history=investigation_history,
        )
        if mlob_result is None:
            return self._failure("Main Line of Business analysis could not be completed.", sql_history, result_history)

        mlob_df = mlob_result["data"]
        # Single-window mode: select material activity by absolute magnitude.
        selected_mlob, mlob_coverage = self._select_material_drivers(
            mlob_df,
            "Main_Line_of_Business",
            overall_tr if overall_tr else 0.0,
        )
        if not selected_mlob:
            # window mode uses absolute magnitudes; fall back to largest movers.
            selected_mlob, mlob_coverage = self._select_absolute_movers(mlob_df, "Main_Line_of_Business")
        self._send_driver_event(progress_callback, next_number, "Main_Line_of_Business", selected_mlob, mlob_coverage)
        investigation_history.append(
            {
                "investigation": next_number,
                "level": "Main_Line_of_Business",
                "focus_dimension": None,
                "focus_value": None,
                "selected_drivers": selected_mlob,
                "coverage": mlob_coverage.get("coverage", 0.0),
                "change": overall_tr,
                "direction": self._movement_direction(overall_tr),
                "evidence_status": "window_driver_selection",
            }
        )
        next_number += 1

        mblob_evidence = []
        for driver in selected_mlob:
            mblob_evidence.append(
                {
                    "dimension": "Main_Line_of_Business",
                    "driver": driver["driver"],
                    "change": driver["change"],
                    "direction": driver["direction"],
                    "coverage": mlob_coverage.get("coverage", 0.0),
                }
            )

        # ---------------------------------------------------------
        # 3. UW portfolios for each selected MLOB
        # ---------------------------------------------------------
        portfolio_evidence = []
        selected_portfolios = []

        for mlob in selected_mlob:
            value = mlob["driver"]
            q = (
                f"Summarize Technical Result by UW_Portfolio within Main_Line_of_Business "
                f"'{value}' recorded within {window_label}."
            )
            result = self._run_investigation(
                number=next_number,
                level="UW_Portfolio",
                question=q,
                region=region,
                market_unit=market_unit,
                period=period,
                focus_dimension="Main_Line_of_Business",
                focus_value=value,
                progress_callback=progress_callback,
                sql_history=sql_history,
                result_history=result_history,
                investigation_history=investigation_history,
            )
            if result is None:
                next_number += 1
                continue

            df = result["data"]
            selected, coverage = self._select_material_drivers(
                df,
                "UW_Portfolio",
                mlob["change"] if mlob["change"] else 0.0,
            )
            if not selected:
                selected, coverage = self._select_absolute_movers(df, "UW_Portfolio")
            self._send_driver_event(progress_callback, next_number, "UW_Portfolio", selected, coverage, parent_value=value)
            investigation_history.append(
                {
                    "investigation": next_number,
                    "level": "UW_Portfolio",
                    "focus_dimension": "Main_Line_of_Business",
                    "focus_value": value,
                    "selected_drivers": selected,
                    "coverage": coverage.get("coverage", 0.0),
                    "change": mlob["change"],
                    "direction": mlob["direction"],
                    "evidence_status": "window_driver_selection",
                }
            )
            next_number += 1

            for portfolio in selected:
                selected_portfolios.append(
                    {
                        **portfolio,
                        "mlob": value,
                        "parent_change": mlob["change"],
                    }
                )
                portfolio_evidence.append(
                    {
                        **portfolio,
                        "parent_value": value,
                        "parent_change": mlob["change"],
                        "coverage": coverage.get("coverage", 0.0),
                        "data": df.copy(),
                    }
                )

        # ---------------------------------------------------------
        # 4. Cedents for each selected portfolio
        # ---------------------------------------------------------
        cedent_evidence = []
        selected_cedents = []

        for portfolio in selected_portfolios:
            mlob = portfolio["mlob"]
            portfolio_name = portfolio["driver"]
            q = (
                f"Summarize Technical Result by Cedent_Name within Main_Line_of_Business "
                f"'{mlob}' and UW_Portfolio '{portfolio_name}' recorded within {window_label}."
            )
            result = self._run_investigation(
                number=next_number,
                level="Cedent_Name",
                question=q,
                region=region,
                market_unit=market_unit,
                period=period,
                context_filters={
                    "Main_Line_of_Business": mlob,
                    "UW_Portfolio": portfolio_name,
                },
                progress_callback=progress_callback,
                sql_history=sql_history,
                result_history=result_history,
                investigation_history=investigation_history,
            )
            if result is None:
                next_number += 1
                continue

            df = result["data"]
            selected, coverage = self._select_material_drivers(
                df,
                "Cedent_Name",
                portfolio["change"] if portfolio["change"] else 0.0,
            )
            if not selected:
                selected, coverage = self._select_absolute_movers(df, "Cedent_Name")
            self._send_driver_event(
                progress_callback,
                next_number,
                "Cedent_Name",
                selected,
                coverage,
                parent_value=portfolio_name,
            )
            investigation_history.append(
                {
                    "investigation": next_number,
                    "level": "Cedent_Name",
                    "focus_dimension": "UW_Portfolio",
                    "focus_value": portfolio_name,
                    "parent_mlob": mlob,
                    "selected_drivers": selected,
                    "coverage": coverage.get("coverage", 0.0),
                    "change": portfolio["change"],
                    "direction": portfolio["direction"],
                    "evidence_status": "window_driver_selection",
                }
            )
            next_number += 1

            for cedent in selected:
                selected_cedents.append(
                    {
                        **cedent,
                        "mlob": mlob,
                        "portfolio": portfolio_name,
                        "parent_change": portfolio["change"],
                    }
                )
                cedent_evidence.append(
                    {
                        **cedent,
                        "mlob": mlob,
                        "portfolio": portfolio_name,
                        "parent_change": portfolio["change"],
                        "coverage": coverage.get("coverage", 0.0),
                        "data": df.copy(),
                    }
                )

        # ---------------------------------------------------------
        # 5. Renewal / New Business / Cancelled for each selected cedent
        # ---------------------------------------------------------
        renewal_evidence = []

        seen = set()
        for cedent in selected_cedents:
            key = (cedent["mlob"], cedent["portfolio"], cedent["driver"])
            if key in seen:
                continue
            seen.add(key)

            mlob, portfolio, cedent_name = key
            q = (
                f"Summarize Technical Result by Renewal_Category for Cedent_Name "
                f"'{cedent_name}', UW_Portfolio '{portfolio}' and Main_Line_of_Business "
                f"'{mlob}' recorded within {window_label}. Show New Business, Renewal "
                f"and Cancelled activity."
            )
            result = self._run_investigation(
                number=next_number,
                level="Renewal_Category",
                question=q,
                region=region,
                market_unit=market_unit,
                period=period,
                context_filters={
                    "Main_Line_of_Business": mlob,
                    "UW_Portfolio": portfolio,
                    "Cedent_Name": cedent_name,
                },
                progress_callback=progress_callback,
                sql_history=sql_history,
                result_history=result_history,
                investigation_history=investigation_history,
            )
            if result is None:
                next_number += 1
                continue

            df = result["data"]
            categories = self._select_all_categories(df)
            self._send_progress(
                progress_callback,
                {
                    "type": "driver_selected",
                    "investigation": next_number,
                    "level": "Renewal_Category",
                    "drivers": categories,
                    "coverage": 1.0,
                    "selection_rule": "All available business categories retained for interpretation.",
                },
            )
            investigation_history.append(
                {
                    "investigation": next_number,
                    "level": "Renewal_Category",
                    "focus_dimension": "Cedent_Name",
                    "focus_value": cedent_name,
                    "parent_mlob": mlob,
                    "parent_portfolio": portfolio,
                    "selected_drivers": categories,
                    "coverage": 1.0,
                    "change": cedent["change"],
                    "direction": cedent["direction"],
                    "evidence_status": "all_business_categories",
                }
            )
            renewal_evidence.append(
                {
                    "mlob": mlob,
                    "portfolio": portfolio,
                    "cedent": cedent_name,
                    "parent_change": cedent["change"],
                    "data": df.copy(),
                    "categories": categories,
                }
            )
            next_number += 1

        # ---------------------------------------------------------
        # Final evidence and commentary
        # ---------------------------------------------------------
        evidence = self._build_window_evidence(
            period=period,
            region=region,
            market_unit=market_unit,
            overall_tr=overall_tr,
            window_dataframe=window_df,
            window_metrics=window_metrics,
            window_movements=window_movements,
            mlob_results=mblob_evidence,
            portfolio_results=portfolio_evidence,
            cedent_results=cedent_evidence,
            renewal_results=renewal_evidence,
        )

        self._send_progress(
            progress_callback,
            {
                "type": "commentary_generating",
                "message": "All material activity collected. Generating executive commentary...",
            },
        )

        try:
            commentary = self._generate_window_commentary(
                region=region,
                market_unit=market_unit,
                period=period,
                overall_tr=overall_tr,
                window_movements=window_movements,
                evidence=evidence,
            )
        except Exception as exc:
            commentary = (
                f"Executive Commentary – {market_unit} | {window_label}\n\n"
                f"Within the selected period the Technical Result was {format_financial(overall_tr)}. "
                f"Detailed commentary generation failed: {exc}"
            )

        self._send_progress(
            progress_callback,
            {
                "type": "commentary_ready",
                "commentary": commentary,
            },
        )

        return {
            "success": True,
            "region": region,
            "market_unit": market_unit,
            "current_year": period.get("current_year"),
            "current_quarter": period.get("current_quarter"),
            "previous_year": period.get("previous_year"),
            "previous_quarter": period.get("previous_quarter"),
            "period_mode": "custom",
            "window": True,
            "overall_change": overall_tr,
            "movement_direction": self._movement_direction(overall_tr),
            "sql_history": sql_history,
            "result_history": result_history,
            "investigation_history": investigation_history,
            "investigations": len(result_history),
            "commentary": commentary,
            "chart": None,
            "rows": len(window_df),
            "execution_time": round(time.time() - start_time, 3),
            "driver_summary": {
                "main_line_of_business": selected_mlob,
                "uw_portfolios": selected_portfolios,
                "cedents": selected_cedents,
                "renewal_analyses": renewal_evidence,
            },
        }

    @staticmethod
    def _send_driver_event(
        progress_callback,
        investigation,
        level,
        drivers,
        coverage,
        parent_value=None,
    ):
        event = {
            "type": "driver_selected",
            "investigation": investigation,
            "level": level,
            "drivers": drivers,
            "coverage": coverage.get("coverage", 0.0),
            "target": coverage.get("target", AnalystOrchestrator.COVERAGE_TARGET),
            "parent_value": parent_value,
            "selection_rule": "Largest same-direction contributors until 80% coverage, with at least 3 when available.",
        }
        # Backward-compatible single-driver fields.
        if drivers:
            event["driver"] = drivers[0]["driver"]
            event["change"] = drivers[0]["change"]
            event["direction"] = drivers[0]["direction"]
        AnalystOrchestrator._send_progress(progress_callback, event)

    @staticmethod
    def _failure(message, sql_history, result_history):
        return {
            "success": False,
            "message": message,
            "sql_history": sql_history,
            "result_history": result_history,
            "investigations": len(result_history),
        }


def format_financial(value):
    if value is None:
        return "N/A"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "N/A"

    sign = "-" if value < 0 else ""
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"{sign}${absolute / 1_000_000_000:.2f}B"
    if absolute >= 1_000_000:
        return f"{sign}${absolute / 1_000_000:.2f}M"
    if absolute >= 1_000:
        return f"{sign}${absolute / 1_000:.2f}K"
    return f"{sign}${absolute:.2f}"


def clean_commentary_text(text):
    """
    Remove accidental Markdown/LaTeX formatting artifacts while keeping
    the financial meaning and paragraph structure intact.
    """
    if not text:
        return ""

    text = str(text).strip()
    text = re.sub(r"^```(?:text|markdown)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    # LaTeX delimiters and common subscript constructs.
    text = text.replace("\\(", "").replace("\\)", "")
    text = text.replace("\\[", "").replace("\\]", "")
    text = re.sub(r"_\{([^{}]+)\}", r" \1", text)
    text = re.sub(r"\^\{([^{}]+)\}", r" \1", text)
    text = re.sub(r"\\text\{([^{}]+)\}", r"\1", text)

    # Markdown emphasis markers should never reach the UI.
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"(?<!\w)\*", "", text)
    text = text.replace("`", "")

    # Remove stray LaTeX commands but preserve currency symbols.
    text = re.sub(r"\\[a-zA-Z]+", "", text)
    text = text.replace("{", "").replace("}", "")

    # Remove Markdown bullets/numbering if the model ignored the prompt.
    cleaned_lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s*[-•]\s+", "", line)
        line = re.sub(r"^\s*\d+[.)]\s+", "", line)
        line = " ".join(line.strip().split())
        cleaned_lines.append(line)

    # Preserve paragraph breaks while avoiding excessive blank lines.
    paragraphs = []
    current = []
    for line in cleaned_lines:
        if line:
            current.append(line)
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))

    return "\n\n".join(paragraphs).strip()