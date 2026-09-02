from datetime import date, datetime, timedelta
import calendar

from database.schema_reader import SchemaReader


def _last_day_of_month(year, month):
    return date(year, month, calendar.monthrange(year, month)[1])


def build_window_period(start_date, end_date):
    """
    Build a single-window analysis period from calendar from/to dates.

    Unlike build_date_period, this does NOT compute any previous/comparison
    window. Date-range commentary is an investigation of the selected window
    only: the engine analyses the financial activity that occurred within
    [start_date, end_date] and explains movements *within* that range.

    Returns a period dict with window=True, accepted by SQLAgent and
    AnalystOrchestrator for the window analysis path.
    """
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = date.fromisoformat(end_date)

    if start_date > end_date:
        raise ValueError("The 'From' date must not be after the 'To' date.")

    return {
        "mode": "custom",
        "window": True,
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "current_start": start_date.isoformat(),
        "current_end": end_date.isoformat(),
        "current_year": start_date.year,
        "current_quarter": (start_date.month - 1) // 3 + 1,
    }


def build_date_period(start_date, end_date):
    """
    Build a custom analysis period from calendar from/to dates.

    The selected window becomes the current period. The previous period is
    the calendar window immediately preceding it:

      * when the selection spans whole months (e.g. a full quarter), the
        previous period is the same number of immediately preceding months,
        so picking 2025 Q1 compares against 2024 Q4;
      * otherwise the previous period is the equal-length day window directly
        before the selection.

    The comparison/change logic downstream keeps working exactly as it does
    for the quarter-over-quarter mode.

    Returns a period dict accepted by SQLAgent and AnalystOrchestrator.
    """
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = date.fromisoformat(end_date)

    if start_date > end_date:
        raise ValueError("The 'From' date must not be after the 'To' date.")

    if start_date.day == 1 and end_date == _last_day_of_month(end_date.year, end_date.month):
        # Whole-month selection: use the same number of preceding months.
        month_count = (
            (end_date.year - start_date.year) * 12
            + (end_date.month - start_date.month)
            + 1
        )
        previous_end_index = start_date.year * 12 + (start_date.month - 1) - 1
        previous_start_index = previous_end_index - (month_count - 1)
        previous_end = _last_day_of_month(
            previous_end_index // 12, previous_end_index % 12 + 1
        )
        previous_start = date(
            previous_start_index // 12, previous_start_index % 12 + 1, 1
        )
    else:
        # Partial-month selection: equal-length day window immediately before.
        duration = (end_date - start_date).days + 1
        previous_end = start_date - timedelta(days=1)
        previous_start = previous_end - timedelta(days=duration - 1)

    return {
        "mode": "custom",
        "current_start": start_date.isoformat(),
        "current_end": end_date.isoformat(),
        "previous_start": previous_start.isoformat(),
        "previous_end": previous_end.isoformat(),
        "current_year": start_date.year,
        "current_quarter": (start_date.month - 1) // 3 + 1,
        "previous_year": previous_end.year,
        "previous_quarter": (previous_end.month - 1) // 3 + 1,
    }


class SQLAgent:
    """Generates controlled SQLite queries for quarter-over-quarter financial analysis."""

    HIERARCHY = [
        "Main_Line_of_Business",
        "UW_Portfolio",
        "Cedent_Name",
        "Renewal_Category",
    ]

    ALLOWED_FILTER_COLUMNS = {
        "Region",
        "Market_Unit",
        "Main_Line_of_Business",
        "UW_Portfolio",
        "Cedent_Name",
        "Renewal_Category",
    }

    METRICS = [
        "Premium",
        "Claims",
        "Commission",
        "Expenses",
        "Technical_Result",
    ]

    def __init__(self, database_path):
        self.schema_reader = SchemaReader(database_path)

    @staticmethod
    def get_analysis_period():
        today = datetime.now()
        current_year = today.year
        month = today.month

        if month <= 3:
            current_quarter = 1
        elif month <= 6:
            current_quarter = 2
        elif month <= 9:
            current_quarter = 3
        else:
            current_quarter = 4

        if current_quarter == 1:
            previous_year = current_year - 1
            previous_quarter = 4
        else:
            previous_year = current_year
            previous_quarter = current_quarter - 1

        return {
            "mode": "quarter",
            "current_year": current_year,
            "current_quarter": current_quarter,
            "previous_year": previous_year,
            "previous_quarter": previous_quarter,
        }

    @staticmethod
    def _quarter_condition(column, quarter):
        return (
            f"(CAST({column} AS TEXT) = 'Q{quarter}' "
            f"OR CAST({column} AS TEXT) = '{quarter}')"
        )

    @classmethod
    def _period_condition(cls, period, which):
        """Build the SQL predicate selecting one side of the comparison period."""
        if period.get("window"):
            # Date-range window mode: there IS no comparison period. Only the
            # selected window is ever queried, for any 'which'.
            start = period["current_start"]
            end = period["current_end"]
            return (
                f"(CAST(Booking_Date AS TEXT) >= '{start}' "
                f"AND CAST(Booking_Date AS TEXT) <= '{end}')"
            )
        if period.get("mode") == "custom":
            start = period[f"{which}_start"]
            end = period[f"{which}_end"]
            return (
                f"(CAST(Booking_Date AS TEXT) >= '{start}' "
                f"AND CAST(Booking_Date AS TEXT) <= '{end}')"
            )
        year = period[f"{which}_year"]
        quarter = period[f"{which}_quarter"]
        return (
            f"(Accounting_Year = {year} AND "
            f"{cls._quarter_condition('Accounting_Quarter', quarter)})"
        )

    @staticmethod
    def _escape_sql_value(value):
        return str(value).replace("'", "''")

    def _value_condition(self, column, value):
        """Build a safe equality or IN predicate for known filter columns."""
        if column not in self.ALLOWED_FILTER_COLUMNS:
            raise ValueError(f"Unsupported filter column: {column}")

        if isinstance(value, (list, tuple, set)):
            values = [self._escape_sql_value(v) for v in value if v is not None]
            if not values:
                return None
            quoted = ", ".join(f"'{v}'" for v in values)
            return f"{column} IN ({quoted})"

        if value is None:
            return None

        return f"{column} = '{self._escape_sql_value(value)}'"

    def _build_where_clause(
        self,
        period,
        region,
        market_unit,
        focus_dimension=None,
        focus_value=None,
        context_filters=None,
    ):
        current = self._period_condition(period, "current")
        previous = self._period_condition(period, "previous")
        period_condition = f"(({current}) OR ({previous}))"

        conditions = [
            self._value_condition("Region", region),
            self._value_condition("Market_Unit", market_unit),
            period_condition,
        ]

        if context_filters:
            for column, value in context_filters.items():
                condition = self._value_condition(column, value)
                if condition:
                    conditions.append(condition)

        if focus_dimension and focus_value:
            condition = self._value_condition(focus_dimension, focus_value)
            if condition:
                conditions.append(condition)

        return "\nAND ".join(c for c in conditions if c)

    @classmethod
    def _period_sum(cls, metric, period, which):
        return f"""
        SUM(
            CASE
                WHEN {cls._period_condition(period, which)}
                THEN {metric}
                ELSE 0
            END
        )
        """

    @classmethod
    def _metric_columns(cls, period):
        if period.get("window"):
            # Date-range window mode: financial activity is measured *within*
            # the selected window only. Change columns carry the within-window
            # total so dimension ordering by magnitude works; no _Previous is
            # produced (there is no comparison period to analyse).
            pieces = []
            for metric in cls.METRICS:
                current = cls._period_sum(metric, period, "current")
                pieces.extend(
                    [
                        f"{current} AS {metric}_Current",
                        f"{current} AS {metric}_Change",
                    ]
                )
            return ",\n".join(pieces)
        pieces = []
        for metric in cls.METRICS:
            current = cls._period_sum(metric, period, "current")
            previous = cls._period_sum(metric, period, "previous")
            pieces.extend(
                [
                    f"{current} AS {metric}_Current",
                    f"{previous} AS {metric}_Previous",
                    f"({current} - {previous}) AS {metric}_Change",
                ]
            )
        return ",\n".join(pieces)

    def _generate_quarter_sql(
        self,
        period,
        region,
        market_unit,
        focus_dimension=None,
        focus_value=None,
        context_filters=None,
    ):
        where_clause = self._build_where_clause(
            period,
            region,
            market_unit,
            focus_dimension,
            focus_value,
            context_filters,
        )

        if period.get("window"):
            period_columns = ",\n".join(
                [
                    f"    '{period['current_start']}' AS Current_Start",
                    f"    '{period['current_end']}' AS Current_End",
                ]
            )
        elif period.get("mode") == "custom":
            period_columns = ",\n".join(
                [
                    f"    '{period['current_start']}' AS Current_Start",
                    f"    '{period['current_end']}' AS Current_End",
                    f"    '{period['previous_start']}' AS Previous_Start",
                    f"    '{period['previous_end']}' AS Previous_End",
                ]
            )
        else:
            period_columns = ",\n".join(
                [
                    f"    {period['current_year']} AS Current_Year",
                    f"    'Q{period['current_quarter']}' AS Current_Quarter",
                    f"    {period['previous_year']} AS Previous_Year",
                    f"    'Q{period['previous_quarter']}' AS Previous_Quarter",
                ]
            )

        sql = f"""
SELECT
{period_columns},
    {self._metric_columns(period)}
FROM finance_data
WHERE {where_clause};
"""
        return sql.strip()

    def _generate_dimension_sql(
        self,
        dimension,
        period,
        region,
        market_unit,
        focus_dimension=None,
        focus_value=None,
        context_filters=None,
    ):
        if dimension not in self.HIERARCHY:
            raise ValueError(f"Unsupported investigation dimension: {dimension}")

        where_clause = self._build_where_clause(
            period,
            region,
            market_unit,
            focus_dimension,
            focus_value,
            context_filters,
        )

        sql = f"""
SELECT
    {dimension},
    {self._metric_columns(period)},
    COUNT(*) AS Record_Count
FROM finance_data
WHERE {where_clause}
GROUP BY {dimension}
ORDER BY ABS(Technical_Result_Change) DESC;
"""
        return sql.strip()

    def _generate_window_series_sql(
        self,
        period,
        region,
        market_unit,
        focus_dimension=None,
        focus_value=None,
        context_filters=None,
    ):
        """Monthly breakdown of financial activity *within* the selected window.

        Buckets bookings by Calendar month (substr of the ISO Booking_Date).
        Used to detect within-window movements (spikes/dips/trends) without
        comparing against any other period.
        """
        where_clause = self._build_where_clause(
            period,
            region,
            market_unit,
            focus_dimension,
            focus_value,
            context_filters,
        )

        sql = f"""
SELECT
    substr(CAST(Booking_Date AS TEXT), 1, 7) AS Month,
    {self._metric_columns(period)},
    COUNT(*) AS Record_Count
FROM finance_data
WHERE {where_clause}
GROUP BY substr(CAST(Booking_Date AS TEXT), 1, 7)
ORDER BY Month;
"""
        return sql.strip()

    def generate_sql(
        self,
        question,
        region,
        market_unit,
        driver1=None,
        driver2=None,
        investigation_level=None,
        focus_dimension=None,
        focus_value=None,
        context_filters=None,
        period=None,
    ):
        # question/driver1/driver2 are accepted for compatibility and auditability.
        del question, driver1, driver2

        if period is None:
            period = self.get_analysis_period()

        if investigation_level in (None, "Initial", "Quarter"):
            return self._generate_quarter_sql(
                period,
                region,
                market_unit,
                focus_dimension,
                focus_value,
                context_filters,
            )

        if investigation_level in self.HIERARCHY:
            return self._generate_dimension_sql(
                investigation_level,
                period,
                region,
                market_unit,
                focus_dimension,
                focus_value,
                context_filters,
            )

        if investigation_level == "Movement":
            if not period.get("window"):
                raise ValueError("Movement series is only available in window mode.")
            return self._generate_window_series_sql(
                period,
                region,
                market_unit,
                focus_dimension,
                focus_value,
                context_filters,
            )

        raise ValueError(f"Unknown investigation level: {investigation_level}")