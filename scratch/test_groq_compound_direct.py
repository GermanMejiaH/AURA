import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from aura.audio import EdgeTTSProvider
from aura.cognition import OpenAILLMProvider


def load_dotenv_simple() -> None:
    if os.path.exists(".env"):
        with open(".env", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()


def main() -> None:
    load_dotenv_simple()
    print("=== TEST REAL DE LLM GROQ COMPOUND Y REPRODUCCIÓN TTS ===")

    llm = OpenAILLMProvider()
    print(f"Provider: OpenAILLMProvider | Base URL: {llm.base_url} | Model: {llm.model_name}")

    user_prompt = "Hola AURA, esta es una prueba completa del sistema."
    print(f"\n[Usuario]: {user_prompt}")

    print("\nGenerando respuesta con Groq Cloud (groq/compound)...")
    response = llm.generate_response(
        prompt=user_prompt,
        system_instruction=(
            "Eres AURA, una asistente virtual inteligente en español. "
            "Responde con entusiasmo en 1 oración corta."
        ),
    )

    print(f"\n[AURA (Groq Compound)]: {response.content}")

    print("\nReproduciendo respuesta vocalmente mediante EdgeTTS...")
    tts = EdgeTTSProvider(voice="es-aura")
    tts.speak(response.content)
    print("✅ Reproducción TTS completada en altavoces.")


if __name__ == "__main__":
    main()
