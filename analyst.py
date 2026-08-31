from config import DATABASE_PATH
from agents.sql_agent import SQLAgent
from agents.sql_executor import SQLExecutor
from intelligence.intent_classifier import IntentClassifier


class AIAnalyst:
    """Main AI Analyst orchestrator."""

    def __init__(self):
        self.intent_classifier = IntentClassifier()
        self.sql_agent = SQLAgent(DATABASE_PATH)
        self.executor = SQLExecutor(DATABASE_PATH)

    def ask(self, question: str):

        intent = self.intent_classifier.classify(question)

        response = {
            "question": question,
            "intent": intent,
            "sql": None,
            "result": None
        }

        primary_intent = intent["primary_intent"]

        if primary_intent == IntentClassifier.RETRIEVAL:
            sql = self.sql_agent.generate_sql(question)
            response["sql"] = sql
            response["result"] = self.executor.execute(sql)

        elif primary_intent == IntentClassifier.COMPARISON:
            sql = self.sql_agent.generate_sql(question)
            response["sql"] = sql
            response["result"] = self.executor.execute(sql)

        elif primary_intent == IntentClassifier.ANALYSIS:
            sql = self.sql_agent.generate_sql(question)
            response["sql"] = sql
            response["result"] = self.executor.execute(sql)

        elif primary_intent == IntentClassifier.VISUALIZATION:
            sql = self.sql_agent.generate_sql(question)
            response["sql"] = sql
            response["result"] = self.executor.execute(sql)

        elif primary_intent == IntentClassifier.DRILLDOWN:
            sql = self.sql_agent.generate_sql(question)
            response["sql"] = sql
            response["result"] = self.executor.execute(sql)

        else:
            response["result"] = {
                "success": False,
                "message": "Unable to determine user intent."
            }

        return response