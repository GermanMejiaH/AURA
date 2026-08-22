from __future__ import annotations

import io
import os
import sys
import wave

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from aura import AURA, AURABootOptions
from aura.audio import EdgeTTSProvider, FasterWhisperSTTProvider, MicrophoneRecorder
from aura.cognition import CognitionModule
from aura.config import ConfigurationManager
from aura.memory import MemoryModule


def load_dotenv_simple() -> None:
    if os.path.exists(".env"):
        with open(".env", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()


def run_single_turn(
    turn_num: int,
    prompt_instruction: str,
    recorder: MicrophoneRecorder,
    stt: FasterWhisperSTTProvider,
    aura: AURA,
    tts: EdgeTTSProvider,
) -> dict[str, str]:
    print(f"\n{'=' * 70}")
    print(f"--- PRUEBA {turn_num}: {prompt_instruction} ---")
    print(f"{'=' * 70}")
    print(f"Por favor di vocalmente hacia el micrófono C920: '{prompt_instruction}'")
    print("[1/4] Capturando audio hasta silencio (silence=1.2s, max=10.0s, energy_thresh=120.0)...")

    audio_bytes = recorder.record_until_silence(
        max_duration_sec=10.0, silence_sec=1.2, energy_threshold=120.0
    )

    if not audio_bytes or len(audio_bytes) <= 44:
        print("      ⚠ Audio no capturado o vacío.")
        return {"turn": str(turn_num), "user": "", "response": "No escuché nada.", "facts_retrieved": "0"}

    # Audio metrics
    buf = io.BytesIO(audio_bytes)
    with wave.open(buf, "rb") as wf:
        wav_rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    pcm = np.frombuffer(frames, dtype=np.int16)
    duration_sec = len(pcm) / wav_rate if wav_rate > 0 else 0.0
    rms_val = float(np.sqrt(np.mean(pcm.astype(np.float32) ** 2))) if len(pcm) > 0 else 0.0
    peak_val = int(np.max(np.abs(pcm))) if len(pcm) > 0 else 0

    print(
        f"      [Audio Stats] Frecuencia={wav_rate}Hz | Duración={duration_sec:.2f}s | RMS={rms_val:.1f} | Peak={peak_val}"
    )

    if rms_val < 50.0:
        print("      ⚠ Audio con silencio ambiental insignificante.")
        return {
            "turn": str(turn_num),
            "user": "",
            "response": "No escuché nada.",
            "facts_retrieved": "0",
        }

    # STT Transcription
    print("[2/4] Transcribiendo con Faster-Whisper (ES)...")
    stt_res = stt.transcribe(audio_bytes, language="es")
    user_text = stt_res.text.strip()
    print(f"      [Transcripción STT]: '{user_text}'")

    if not user_text:
        print("      ⚠ No se transcribió texto.")
        return {
            "turn": str(turn_num),
            "user": "",
            "response": "No escuché nada.",
            "facts_retrieved": "0",
        }

    # Memory Retrieval check
    mem = aura.container.resolve(MemoryModule)
    retrieval_res = mem.retrieval.query(user_text)
    num_facts = len(retrieval_res.facts)
    num_prefs = len(retrieval_res.preferences)
    print(
        f"      [Memory Retrieval]: Found {num_facts} relevant facts, {num_prefs} preferences for query '{user_text}'"
    )
    for f in retrieval_res.facts:
        print(
            f"         -> Fact: {f.subject} {f.predicate} = {f.object_val} (score={f.confidence})"
        )

    # Cognition LLM cycle (Groq Compound)
    print("[3/4] Procesando ciclo cognitivo con Groq Compound...")
    cog = aura.container.resolve(CognitionModule)
    cycle_res = cog.process_cognitive_cycle(user_text)
    aura_response = cycle_res.summary.strip()
    print(f"      [Respuesta AURA]: '{aura_response}'")

    # TTS audio response
    print("[4/4] Reproduciendo respuesta mediante EdgeTTS por los altavoces...")
    try:
        tts.speak(aura_response)
        print("      ✅ Audio TTS reproducido correctamente.")
    except Exception as exc:
        print(f"      ❌ Error en reproducción TTS: {exc}")

    return {
        "turn": str(turn_num),
        "user": user_text,
        "response": aura_response,
        "facts_retrieved": str(num_facts),
    }


def main() -> None:
    load_dotenv_simple()
    print("=== AURA REAL CONVERSE VALIDATION SCRIPT (PASO 6) ===")

    # Config & Boot AURA
    cfg = ConfigurationManager()
    cfg.set("llm.provider", "groq")
    cfg.set("audio.input_device", "C920")

    aura = AURA(config=cfg, options=AURABootOptions())
    aura.boot()

    recorder = MicrophoneRecorder(device="C920")
    dev_id = recorder.resolve_device_id()
    print(f"Micrófono configurado: Logitech C920 (PortAudio Index: {dev_id})")

    stt = FasterWhisperSTTProvider(model_size_or_path="base", device="cpu", compute_type="int8")
    tts = EdgeTTSProvider(voice="es-aura")
    llm = aura.container.resolve(CognitionModule).llm_provider
    print(
        f"LLM Provider: {llm.__class__.__name__} | Base URL: {getattr(llm, 'base_url', 'N/A')} | Model: {getattr(llm, 'model_name', 'N/A')}"
    )

    test_prompts = [
        "Hola AURA, esta es una prueba del micrófono.",
        "¿Cómo estás?",
        "¿Cuál es mi color favorito?",
        "Recuérdame que mañana debo estudiar.",
        "Hola AURA, esta es una frase larga de más de cuatro segundos para verificar que la captura por silencio y el normalizador de ganancia no truncan el audio.",
    ]

    results = []
    for idx, prompt_inst in enumerate(test_prompts, start=1):
        res = run_single_turn(idx, prompt_inst, recorder, stt, aura, tts)
        results.append(res)

    aura.shutdown(wait=True)

    print(f"\n\n{'=' * 70}")
    print("=== RESUMEN DE RESULTADOS DE VALIDACIÓN MANUAL REAL (PASO 6) ===")
    print(f"{'=' * 70}")
    for r in results:
        print(f"Prueba {r['turn']}:")
        print(f"  - Texto Transcrito (STT): '{r['user']}'")
        print(f"  - Datos Memoria Inyectados: {r['facts_retrieved']}")
        print(f"  - Respuesta AURA (Groq):  '{r['response']}'")
        print("-" * 50)


if __name__ == "__main__":
    main()
