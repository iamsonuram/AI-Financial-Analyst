from config import DATABASE_PATH
from analysis.analysis_engine import AnalysisEngine

engine = AnalysisEngine(DATABASE_PATH)

dashboard = engine.get_dashboard_data(
    region="Asia",
    market_unit="Japan"
)

print(dashboard)