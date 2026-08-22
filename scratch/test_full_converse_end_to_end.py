import io
import os
import sys
import time
import wave

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from aura.audio import EdgeTTSProvider, FasterWhisperSTTProvider, MicrophoneRecorder
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
    print("=== PRUEBA COMPLETA DEL SISTEMA: C920 → STT → GROQ COMPOUND → TTS ===")

    # 1. Verify Groq API Key
    groq_key = os.environ.get("GROQ_API_KEY", "")
    print(f"[1] GROQ_API_KEY presente: {bool(groq_key)}")

    # 2. Instantiate LLM Provider (Groq Compound)
    llm = OpenAILLMProvider()
    print(f"[2] Motor LLM: OpenAILLMProvider -> base_url={llm.base_url}, model={llm.model_name}")

    # 3. Instantiate MicrophoneRecorder with C920
    recorder = MicrophoneRecorder(device="C920")
    resolved_id = recorder.resolve_device_id()
    print(f"[3] Micrófono: Logitech C920 (Índice PortAudio: {resolved_id})")

    # 4. Instantiate STT & TTS
    print("[4] Inicializando STT (FasterWhisper CPU int8) y TTS (EdgeTTS)...")
    stt = FasterWhisperSTTProvider(model_size_or_path="base", device="cpu", compute_type="int8")
    tts = EdgeTTSProvider(voice="es-aura")

    # 5. Vocal Greeting from AURA
    greeting = "Hola, soy AURA. Iniciando prueba del sistema."
    print(f"\n[AURA]: {greeting}")
    tts.speak(greeting)

    # 6. Real Mic Capture from C920
    print("\n[5] Escuchando micrófono C920 durante 4 segundos...")
    print("    >>> POR FAVOR HABLA AHORA DIRIGIÉNDOTE A LA CÁMARA LOGITECH C920 <<<")
    print("    Di: 'Hola AURA, esta es una prueba completa del sistema.'\n")

    for i in range(4, 0, -1):
        print(f"    [*] Escuchando... ({i}s restantes)")
        time.sleep(1.0)

    audio_bytes = recorder.record_bytes(duration_sec=4.0)
    print(f"\n[6] Audio capturado: {len(audio_bytes)} bytes WAV")

    # Metrics
    buf = io.BytesIO(audio_bytes)
    with wave.open(buf, "rb") as wf:
        wav_rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    pcm = np.frombuffer(frames, dtype=np.int16)
    rms_val = float(np.sqrt(np.mean(pcm.astype(np.float32) ** 2))) if len(pcm) > 0 else 0.0
    print(f"    Frecuencia audio: {wav_rate} Hz Mono | Energía RMS: {rms_val:.4f}")

    # 7. STT Transcription
    print("\n[7] Procesando voz a texto con Faster-Whisper...")
    stt_result = stt.transcribe(audio_bytes, language="es")
    user_text = stt_result.text.strip()

    print(f"\n[Tú (C920)]: '{user_text}'")

    if not user_text:
        print("  ⚠  No escuché nada.")
        return

    # 8. Cognition / LLM Generation via Groq
    print(f"\n[8] Enviando a Groq Cloud ({llm.model_name})...")
    llm_resp = llm.generate_response(
        prompt=user_text,
        system_instruction=(
            "Eres AURA, una asistente virtual inteligente, concisa y empática en español. "
            "Responde en 1 o 2 oraciones."
        ),
    )
    aura_response = llm_resp.content.strip()
    print(f"\n[AURA (Groq Compound)]: {aura_response}")

    # 9. TTS Audio Reproduction
    print("\n[9] Reproduciendo respuesta mediante altavoces con EdgeTTS...")
    tts_success = False
    try:
        tts.speak(aura_response)
        tts_success = True
        print("    ✅ TTS audio reproducido correctamente por los altavoces.")
    except Exception as exc:
        print(f"    ❌ Error en reproducción TTS: {exc}")

    print("\n" + "=" * 65)
    print("=== RESUMEN DE LA PRUEBA END-TO-END CONVERSE ===")
    print(f"Micrófono hardware: Logitech C920 (Índice {resolved_id})")
    print(f"Frecuencia de captura/resampling: {wav_rate} Hz Mono")
    print(f"Texto reconocido por STT: '{user_text}'")
    print(f"Modelo LLM activo: Groq Cloud ({llm.model_name})")
    print(f"Respuesta de AURA: '{aura_response}'")
    print(f"Reproducción de audio TTS: {'ÉXITO' if tts_success else 'FALLO'}")
    print("=" * 65)


if __name__ == "__main__":
    main()
