from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    src_dir = Path(__file__).resolve().parent.parent / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from aura.audio import FasterWhisperSTTProvider, MicrophoneRecorder
    from aura.events import EventBus, SpeechRecognized

    print("=" * 60)
    print("      AURA REAL-002: Transcripción en Vivo desde Micrófono Real")
    print("=" * 60)

    bus = EventBus()
    recognized_events: list[SpeechRecognized] = []

    def on_speech(event: SpeechRecognized) -> None:
        recognized_events.append(event)
        print("\n[EVENTO CAPTURADO EN EVENTBUS]")
        print("  • Evento: SpeechRecognized")
        print(f"  • Fuente: {event.source}")
        print(f"  • Texto Transcrito de tu Voz: '{event.text}'")
        print(f"  • Idioma: {event.language}")
        print(f"  • Confianza: {event.confidence:.2f}")

    bus.subscribe("SpeechRecognized", on_speech)

    print("\n1. Cargando motor FasterWhisperSTTProvider (Modelo: tiny)...")
    stt_provider = FasterWhisperSTTProvider(model_size_or_path="tiny", device="cpu", event_bus=bus)

    recorder = MicrophoneRecorder(sample_rate=16000)
    duration = 4.0

    print(f"\n2. 🎙️ ¡HÁBLALE A AURA AHORA! Grabando micrófono durante {duration} segundos...")
    print("   (Habla claramente por tu micrófono...)")

    audio_bytes = recorder.record_bytes(duration_sec=duration)
    print(f"\n3. Audio capturado ({len(audio_bytes)} bytes WAV). Procesando con Faster Whisper...")

    result = stt_provider.transcribe(audio_bytes, language="es")

    print("\n4. Resultado Final del Motor STT:")
    print(f"  • Texto Transcrito: '{result.text}'")
    print(f"  • Confianza: {result.confidence:.4f}")

    print("\nPrueba de Micrófono Real REAL-002 completada exitosamente.")


if __name__ == "__main__":
    main()
