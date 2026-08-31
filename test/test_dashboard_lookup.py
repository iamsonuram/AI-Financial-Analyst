from pprint import pprint

from analysis.analysis_engine import AnalysisEngine

engine = AnalysisEngine()

dashboard = engine.get_dashboard(
    region="Asia",
    market_unit="Japan"
)

pprint(dashboard)

engine.close()