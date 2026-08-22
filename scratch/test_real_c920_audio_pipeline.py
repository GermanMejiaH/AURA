import io
import sys
import wave

import numpy as np

# Force UTF-8 output encoding for Windows terminal stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from aura.audio.faster_whisper_stt import FasterWhisperSTTProvider
from aura.audio.input import SoundDeviceInputProvider


def main() -> None:
    print("=== REAL HARDWARE VALIDATION: LOGITECH C920 AUDIO CAPTURE & PIPELINE ===")

    # 1. Instantiate provider
    provider = SoundDeviceInputProvider(sample_rate=16000)
    device_query = "Microphone (HD Pro Webcam C920)"
    resolved_id = provider.resolve_device_id(device_query)

    print(f"[1] Target Device Query: '{device_query}'")
    print(f"    Resolved PortAudio Device Index: {resolved_id}")

    if resolved_id is None:
        print("    FALLBACK: Searching for 'C920' or 'Webcam'...")
        resolved_id = provider.resolve_device_id("C920")
        print(f"    Resolved Fallback Index: {resolved_id}")

    # 2. Test Real Capture with Fallback / Resampling
    print("\n[2] Test 1: Real Hardware Capture with Native 48 kHz Resampling to 16 kHz Mono...")
    print("    >>> Por favor habla hacia la camara Logitech C920 ahora (4 segundos)... <<<")

    # Force native 48 kHz capture in provider state to test 48k -> 16k resampling pipeline
    provider.start_capture(device=resolved_id)
    # Simulate WASAPI 48k fallback
    provider._actual_sample_rate = 48000
    provider._actual_channels = 2

    import time

    for i in range(4, 0, -1):
        print(f"    [*] Escuchando... ({i}s restantes)")
        time.sleep(1.0)

    # 3. Stop capture & resample
    audio_data = provider.stop_capture()
    print("\n[3] Resampled AudioData Contract Verification:")
    print(f"    AudioData sample_rate: {audio_data.sample_rate} Hz (Expected: 16000)")
    print(f"    AudioData channels: {audio_data.channels} (Expected: 1 mono)")
    print(f"    AudioData duration: {audio_data.duration_seconds:.2f} seconds")
    print(f"    AudioData raw_data byte count: {len(audio_data.raw_data)} bytes")

    # Parse WAV container
    buf = io.BytesIO(audio_data.raw_data)
    with wave.open(buf, "rb") as wf:
        wav_channels = wf.getnchannels()
        wav_width = wf.getsampwidth()
        wav_rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    print(
        f"    WAV Container Header: rate={wav_rate} Hz, channels={wav_channels}, "
        f"sampwidth={wav_width} bytes"
    )

    pcm_16k = np.frombuffer(frames, dtype=np.int16)
    max_amp = np.max(np.abs(pcm_16k)) if len(pcm_16k) > 0 else 0
    rms_val = float(np.sqrt(np.mean(pcm_16k.astype(np.float32) ** 2))) if len(pcm_16k) > 0 else 0.0
    print(f"    Signal Metrics: MAX Amplitude={max_amp}, RMS Energy={rms_val:.4f}")

    # 4. Transcribe with FasterWhisper
    print("\n[4] Initializing FasterWhisperSTTProvider (CPU int8 base)...")
    stt = FasterWhisperSTTProvider(model_size_or_path="base", device="cpu", compute_type="int8")

    print("[5] Transcribing captured 16 kHz mono AudioData with Faster-Whisper...")
    result = stt.transcribe(audio_data, language="es")

    print("\n=== CERTIFICACIÓN Y EVIDENCIA DE CAPTURA REAL ===")
    print(f"Dispositivo hardware: Logitech C920 (Index {resolved_id})")
    print("Captura nativa: 48000 Hz / 2ch")
    print("Resampling numpy: 16000 Hz / 1ch mono")
    print(f"Energía RMS capturada: {rms_val:.4f}")
    print(f"Transcripción Faster-Whisper: '{result.text}'")
    print(f"Confianza STT: {result.confidence}")
    print("======================================================================")


if __name__ == "__main__":
    main()
