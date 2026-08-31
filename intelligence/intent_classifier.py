class IntentClassifier:
    """Classifies the user's intent."""

    RETRIEVAL = "retrieval"
    ANALYSIS = "analysis"
    COMPARISON = "comparison"
    VISUALIZATION = "visualization"
    DRILLDOWN = "drilldown"
    UNKNOWN = "unknown"

    def classify(self, question: str) -> dict:
        question = question.lower()
        intent_scores = {
            self.RETRIEVAL: 0,
            self.ANALYSIS: 0,
            self.COMPARISON: 0,
            self.VISUALIZATION: 0,
            self.DRILLDOWN: 0
        }

        visualization_keywords = [
            "chart", "graph", "plot", "visual", "visualize",
            "dashboard", "pie", "bar", "line", "scatter",
            "trend", "histogram"
        ]

        comparison_keywords = [
            "compare", "comparison", "versus",
            "vs", "variance"
        ]

        analysis_keywords = [
            "why", "reason", "analyse", "analyze",
            "explain", "performance", "summary",
            "executive", "insight", "increase", "decrease"
        ]

        drilldown_keywords = [
            "drill", "breakdown", "driver",
            "root cause", "deep dive",
            "contributor"
        ]

        retrieval_keywords = [
            "show", "list", "display", "find",
            "top", "bottom", "highest",
            "lowest", "give", "fetch"
        ]

        for word in visualization_keywords:
            if word in question:
                intent_scores[self.VISUALIZATION] += 1

        for word in comparison_keywords:
            if word in question:
                intent_scores[self.COMPARISON] += 1

        for word in analysis_keywords:
            if word in question:
                intent_scores[self.ANALYSIS] += 1

        for word in drilldown_keywords:
            if word in question:
                intent_scores[self.DRILLDOWN] += 1

        for word in retrieval_keywords:
            if word in question:
                intent_scores[self.RETRIEVAL] += 1

        primary_intent = max(intent_scores, key=intent_scores.get)

        if intent_scores[primary_intent] == 0:
            primary_intent = self.UNKNOWN

        return {
            "primary_intent": primary_intent,
            "requires_visualization": intent_scores[self.VISUALIZATION] > 0,
            "scores": intent_scores
        }