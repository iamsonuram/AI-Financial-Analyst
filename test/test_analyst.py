from analyst import AIAnalyst

analyst = AIAnalyst()

question = input("Ask a question: ")

response = analyst.ask(question)

print("\n" + "=" * 80)
print("QUESTION")
print("=" * 80)
print(response["question"])

print("\n" + "=" * 80)
print("INTENT")
print("=" * 80)
print(response["intent"])

print("\n" + "=" * 80)
print("GENERATED SQL")
print("=" * 80)
print(response["sql"])

print("\n" + "=" * 80)
print("RESULT")
print("=" * 80)

if response["result"]["success"]:
    print(response["result"]["data"])
else:
    print(response["result"]["message"])