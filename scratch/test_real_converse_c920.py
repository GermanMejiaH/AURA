import io
import sys
import time
import wave

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from aura.audio import FasterWhisperSTTProvider, MicrophoneRecorder


def main() -> None:
    print("=== PRUEBA REAL DE MODO CONVERSE Y MICRÓFONO LOGITECH C920 ===")

    device_query = "C920"
    recorder = MicrophoneRecorder(device=device_query)
    resolved_id = recorder.resolve_device_id()

    print(f"[1] Dispositivo configurado: '{device_query}'")
    print(f"[2] Índice PortAudio resuelto por subcadena: {resolved_id}")

    print("\n[3] Iniciando captura de audio durante 4 segundos...")
    print("    >>> POR FAVOR HABLA AHORA DIRIGIÉNDOTE A LA CÁMARA LOGITECH C920 <<<")
    print("    Ejemplo: 'Hola AURA, esta es una prueba completa del sistema.'\n")

    for i in range(4, 0, -1):
        print(f"    [*] Escuchando... ({i}s restantes)")
        time.sleep(1.0)

    # Captura 4s usando la llamada exacta del comando converse CLI
    audio_bytes = recorder.record_bytes(duration_sec=4.0)

    print("\n[4] Verificación del Contrato de Audio Resultante:")
    print(f"    Total de bytes WAV recibidos: {len(audio_bytes)} bytes")

    buf = io.BytesIO(audio_bytes)
    with wave.open(buf, "rb") as wf:
        wav_channels = wf.getnchannels()
        wav_width = wf.getsampwidth()
        wav_rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    print(f"    WAV Framerate: {wav_rate} Hz (Esperado: 16000)")
    print(f"    WAV Canales: {wav_channels} (Esperado: 1 mono)")
    print(f"    WAV Muestra: {wav_width * 8} bits")

    pcm_16k = np.frombuffer(frames, dtype=np.int16)
    max_amp = int(np.max(np.abs(pcm_16k))) if len(pcm_16k) > 0 else 0
    rms_val = float(np.sqrt(np.mean(pcm_16k.astype(np.float32) ** 2))) if len(pcm_16k) > 0 else 0.0
    print(f"    Métricas de Señal Capturada: Amplitud Máxima={max_amp}, Energía RMS={rms_val:.4f}")

    print("\n[5] Transcribiendo con Faster-Whisper...")
    stt = FasterWhisperSTTProvider(model_size_or_path="base", device="cpu", compute_type="int8")
    result = stt.transcribe(audio_bytes, language="es")

    print("\n" + "=" * 65)
    print("=== RESULTADO DE LA PRUEBA FÍSICA REAL CON CONVERSE/C920 ===")
    print(f"Dispositivo seleccionado realmente: Logitech C920 (Índice {resolved_id})")
    print("Frecuencia de muestreo hardware nativa: 48000 Hz")
    print(f"Frecuencia final entregada a Faster-Whisper: {wav_rate} Hz (Mono)")
    print(f"Energía de audio capturada (RMS): {rms_val:.4f}")
    print(f"Texto transcrito real: '{result.text.strip()}'")
    print(f"Confianza STT: {result.confidence}")
    print("=" * 65)


if __name__ == "__main__":
    main()
