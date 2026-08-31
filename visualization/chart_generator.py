import pandas as pd
import plotly.express as px


class ChartGenerator:

    def generate(self, dataframe, recommendation):

        if recommendation is None:
            return None

        chart_type = recommendation["type"]

        # -------------------------------------------------
        # KPI Comparison
        # -------------------------------------------------

        if chart_type == "kpi_comparison":

            metrics = recommendation["metrics"]

            values = dataframe.iloc[0][metrics]

            chart_df = pd.DataFrame({
                "Metric": metrics,
                "Value": values.values
            })

            fig = px.bar(
                chart_df,
                x="Metric",
                y="Value",
                text="Value"
            )

            fig.update_traces(
                texttemplate="%{text:,.0f}",
                textposition="outside"
            )

            fig.update_layout(
                title="KPI Comparison",
                xaxis_title="",
                yaxis_title="Value",
                showlegend=False,
                height=450
            )

            return fig

        # -------------------------------------------------
        # Category Comparison
        # -------------------------------------------------

        if chart_type == "category_comparison":

            fig = px.bar(
                dataframe,
                x=recommendation["x"],
                y=recommendation["y"],
                text=recommendation["y"]
            )

            fig.update_traces(textposition="outside")

            fig.update_layout(
                height=500
            )

            return fig

        # -------------------------------------------------
        # Time Series
        # -------------------------------------------------

        if chart_type == "time_series":

            fig = px.line(
                dataframe,
                x=recommendation["x"],
                y=recommendation["y"],
                markers=True
            )

            fig.update_layout(
                height=500
            )

            return fig

        # -------------------------------------------------
        # Distribution
        # -------------------------------------------------

        if chart_type == "distribution":

            fig = px.pie(
                dataframe,
                names=recommendation["names"],
                values=recommendation["values"],
                hole=0.45
            )

            return fig

        # -------------------------------------------------
        # Correlation
        # -------------------------------------------------

        if chart_type == "correlation":

            fig = px.scatter(
                dataframe,
                x=recommendation["x"],
                y=recommendation["y"]
            )

            return fig

        return None