import time

from agents.analyst_orchestrator import AnalystOrchestrator


print("Starting Analyst Orchestrator...")

start = time.perf_counter()

orchestrator = AnalystOrchestrator()

print(
    "Orchestrator initialized:",
    round(time.perf_counter() - start, 2),
    "seconds"
)

print("\nStarting analysis...")

start = time.perf_counter()

response = orchestrator.analyze(
    question="Why did Technical Result decrease in 2025?",
    region="Asia",
    market_unit="Japan"
)

elapsed = time.perf_counter() - start

print("\nAnalysis completed.")

print("=" * 80)
print("TOTAL TIME")
print("=" * 80)

print(round(elapsed, 2), "seconds")

print("\nInvestigations:")
print(response.get("investigations"))

print("\nInvestigation Questions:")

for question in response.get(
    "investigation_questions",
    []
):
    print("-", question)

print("\nSQL HISTORY:")

for index, item in enumerate(
    response.get("sql_history", []),
    start=1
):
    print("\n" + "=" * 80)
    print("INVESTIGATION", index)
    print("=" * 80)

    print("Question:")
    print(item["question"])

    print("\nSQL:")
    print(item["sql"])

print("\n" + "=" * 80)
print("FINAL COMMENTARY")
print("=" * 80)

print(response["commentary"])