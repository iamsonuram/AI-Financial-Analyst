from pprint import pprint

from analysis.analysis_engine import AnalysisEngine
from analysis.insight_engine import InsightEngine

analysis = AnalysisEngine()

dashboard = analysis.get_dashboard(

    "Asia",

    "Japan"

)

engine = InsightEngine()

result = engine.generate(dashboard)

pprint(result)