import pandas as pd


class ChartRecommender:
    """
    Recommends the best visualization based on:
    1. User Question
    2. Intent
    3. Returned DataFrame
    """

    KPI_COMPARISON = "kpi_comparison"
    CATEGORY_COMPARISON = "category_comparison"
    TIME_SERIES = "time_series"
    DISTRIBUTION = "distribution"
    CORRELATION = "correlation"
    TABLE = "table"

    def recommend(self, dataframe, question, intent):

        if dataframe is None or dataframe.empty:
            return None

        if not intent["requires_visualization"]:
            return None

        question = question.lower()

        numeric = dataframe.select_dtypes(include="number").columns.tolist()
        categorical = dataframe.select_dtypes(exclude="number").columns.tolist()

        # -------------------------------------------------
        # KPI Comparison
        # -------------------------------------------------

        if len(dataframe) == 1 and len(numeric) >= 2:

            return {
                "type": self.KPI_COMPARISON,
                "metrics": numeric
            }

        # -------------------------------------------------
        # Time Series
        # -------------------------------------------------

        for col in dataframe.columns:

            name = col.lower()

            if any(x in name for x in [
                "year",
                "quarter",
                "month",
                "period",
                "date"
            ]):

                return {
                    "type": self.TIME_SERIES,
                    "x": col,
                    "y": numeric[0]
                }

        # -------------------------------------------------
        # Distribution
        # -------------------------------------------------

        if any(word in question for word in [
            "share",
            "distribution",
            "split",
            "composition"
        ]):

            if categorical and numeric:

                return {
                    "type": self.DISTRIBUTION,
                    "names": categorical[0],
                    "values": numeric[0]
                }

        # -------------------------------------------------
        # Category Comparison
        # -------------------------------------------------

        if categorical and numeric:

            return {
                "type": self.CATEGORY_COMPARISON,
                "x": categorical[0],
                "y": numeric[0]
            }

        # -------------------------------------------------
        # Correlation
        # -------------------------------------------------

        if len(numeric) >= 2:

            return {
                "type": self.CORRELATION,
                "x": numeric[0],
                "y": numeric[1]
            }

        return None