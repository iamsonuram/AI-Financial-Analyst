import os
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


class OpenRouterClient:
    """
    Wrapper for interacting with OpenRouter LLMs.

    Includes defensive handling for:
    - empty responses
    - missing message content
    - reasoning-only responses
    - transient provider/API errors
    - automatic retries
    """

    def __init__(self):

        api_key = os.getenv("OPENROUTER_API_KEY")
        model = os.getenv("MODEL_NAME")

        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is not set in the .env file."
            )

        if not model:
            raise ValueError(
                "MODEL_NAME is not set in the .env file."
            )

        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key
        )

        self.model = model.strip()

        print("========================================")
        print("OPENROUTER MODEL:", self.model)
        print("========================================")

    def generate(
        self,
        prompt: str,
        temperature: float = 0
    ):
        """
        Generate a text response from the configured OpenRouter model.

        Retries transient provider/API failures before raising an error.
        """

        import time

        MAX_RETRIES = 3

        for attempt in range(1, MAX_RETRIES + 1):

            print("\n========================================")
            print(
                f"OPENROUTER REQUEST "
                f"(attempt {attempt}/{MAX_RETRIES})"
            )
            print("========================================")

            try:

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=temperature
                )

            except Exception as exc:

                print("\n========================================")
                print("OPENROUTER API ERROR")
                print("========================================")
                print(type(exc).__name__)
                print(str(exc))
                print("========================================\n")

                if attempt < MAX_RETRIES:
                    print("Retrying OpenRouter request...")
                    time.sleep(2)
                    continue

                raise

            # -------------------------------------------------
            # DEBUG RESPONSE
            # -------------------------------------------------

            print("\n========================================")
            print("OPENROUTER RESPONSE DEBUG")
            print("========================================")

            try:
                print(response.model_dump())
            except Exception:
                print(response)

            print("========================================\n")

            # -------------------------------------------------
            # VALIDATE CHOICES
            # -------------------------------------------------

            choices = getattr(response, "choices", None)

            if not choices:

                print(
                    f"WARNING: OpenRouter returned no choices "
                    f"(attempt {attempt}/{MAX_RETRIES})"
                )

                if attempt < MAX_RETRIES:
                    print("Retrying...")
                    time.sleep(2)
                    continue

                raise RuntimeError(
                    "OpenRouter returned no choices after "
                    f"{MAX_RETRIES} attempts."
                )

            choice = choices[0]

            # -------------------------------------------------
            # CHECK FINISH REASON
            # -------------------------------------------------

            finish_reason = getattr(
                choice,
                "finish_reason",
                None
            )

            if finish_reason == "error":

                print(
                    "WARNING: OpenRouter/provider returned "
                    "finish_reason='error'."
                )

                if attempt < MAX_RETRIES:
                    print("Retrying...")
                    time.sleep(2)
                    continue

                raise RuntimeError(
                    "OpenRouter provider failed after "
                    f"{MAX_RETRIES} attempts."
                )

            # -------------------------------------------------
            # GET MESSAGE
            # -------------------------------------------------

            message = getattr(
                choice,
                "message",
                None
            )

            if message is None:

                print(
                    "WARNING: OpenRouter returned a choice "
                    "without a message."
                )

                if attempt < MAX_RETRIES:
                    print("Retrying...")
                    time.sleep(2)
                    continue

                raise RuntimeError(
                    "OpenRouter returned a choice without "
                    "a message."
                )

            # -------------------------------------------------
            # GET NORMAL CONTENT
            # -------------------------------------------------

            content = getattr(
                message,
                "content",
                None
            )

            if content is not None:

                content = str(content).strip()

                if content:
                    return content

            # -------------------------------------------------
            # REASONING-ONLY RESPONSE
            # -------------------------------------------------

            reasoning = getattr(
                message,
                "reasoning",
                None
            )

            if reasoning:

                print(
                    "WARNING: Model returned reasoning but "
                    "no normal message content."
                )

            # -------------------------------------------------
            # CHECK REFUSAL
            # -------------------------------------------------

            refusal = getattr(
                message,
                "refusal",
                None
            )

            if refusal:

                raise RuntimeError(
                    f"OpenRouter model refused the request: {refusal}"
                )

            # -------------------------------------------------
            # EMPTY RESPONSE
            # -------------------------------------------------

            print(
                f"WARNING: Empty model response "
                f"(attempt {attempt}/{MAX_RETRIES})."
            )

            if attempt < MAX_RETRIES:
                print("Retrying...")
                time.sleep(2)
                continue

            raise RuntimeError(
                "OpenRouter returned an empty message content "
                "after retries. "
                f"finish_reason={finish_reason}, "
                f"model={self.model}"
            )

        raise RuntimeError(
            "OpenRouter request failed unexpectedly."
        )