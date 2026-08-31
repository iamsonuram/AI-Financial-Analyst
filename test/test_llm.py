from llm.openrouter_client import OpenRouterClient

llm = OpenRouterClient()

response = llm.generate(
    "Testing... Reply using exactly three words."
)

print(response)