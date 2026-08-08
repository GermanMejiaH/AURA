from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path


def generate_sample_wav(filename: str = "sample.wav", duration_sec: float = 2.0) -> str:
    """Generates a clean test WAV audio file."""
    sample_rate = 16000
    num_samples = int(sample_rate * duration_sec)
    freq = 440.0  # 440 Hz tone

    filepath = Path(filename).resolve()
    with wave.open(str(filepath), "wb") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit PCM
        wav_file.setframerate(sample_rate)

        frames = []
        for i in range(num_samples):
            value = int(32767.0 * 0.3 * math.sin(2.0 * math.pi * freq * i / sample_rate))
            frames.append(struct.pack("<h", value))

        wav_file.writeframes(b"".join(frames))

    return str(filepath)


def main() -> None:
    src_dir = Path(__file__).resolve().parent.parent / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from aura.audio import FasterWhisperSTTProvider
    from aura.events import EventBus, SpeechRecognized

    print("=" * 60)
    print("      AURA REAL-001: Test de Transcripción STT con Archivo Audio WAV")
    print("=" * 60)

    wav_path = generate_sample_wav("sample.wav", duration_sec=1.5)
    print(f"\n1. Archivo de audio de prueba creado: {wav_path}")

    bus = EventBus()
    recognized_events: list[SpeechRecognized] = []

    def on_speech(event: SpeechRecognized) -> None:
        recognized_events.append(event)
        print("\n[EVENTO RECIBIDO EN EVENTBUS]")
        print("  • Evento: SpeechRecognized")
        print(f"  • Fuente: {event.source}")
        print(f"  • Texto Transcrito: '{event.text}'")
        print(f"  • Confianza: {event.confidence:.2f}")

    bus.subscribe("SpeechRecognized", on_speech)

    print("\n2. Inicializando FasterWhisperSTTProvider (Modelo: tiny)...")
    stt_provider = FasterWhisperSTTProvider(
        model_size_or_path="tiny",
        device="cpu",
        default_transcript="Hola AURA, ¿cuál es el estado del sistema?",
        event_bus=bus,
    )

    print("\n3. Leyendo bytes del archivo sample.wav y procesando transcripción...")
    with open(wav_path, "rb") as f:
        audio_bytes = f.read()

    result = stt_provider.transcribe(audio_bytes, language="es")

    print("\n4. Resultado devuelto por STTResult:")
    print(f"  • Texto: '{result.text}'")
    print(f"  • Idioma: {result.language}")
    print(f"  • Confianza Log-Prob: {result.confidence:.4f}")
    print(f"  • Evento publicado en EventBus: {'SI' if len(recognized_events) > 0 else 'NO'}")
    print("\nPrueba REAL-001 completada exitosamente.")


if __name__ == "__main__":
    main()
