from intelligence.intent_classifier import IntentClassifier

classifier = IntentClassifier()

questions = [
    "Show Top 10 Cedents",
    "Compare 2024 vs 2025",
    "Why did Technical Result decrease?",
    "Generate a Premium trend chart",
    "Drill down into Japan Property",
    "Give me Premium by Region",
    "Compare Premium trend for 2024 and 2025"
]

for question in questions:
    result = classifier.classify(question)

    print("-" * 80)
    print(question)
    print(result)