import re
from collections import Counter

log_path = "pilot_day1.log"

with open(log_path, "r", encoding="utf-16le", errors="ignore") as f:
    lines = f.readlines()

print(f"Total lines in pilot_day1.log: {len(lines)}")

# Metrics counters
vad_detections = 0
vad_empty = 0
stt_rejected = 0
stt_accepted = 0
http_413_count = 0
http_429_count = 0
llm_success = 0
simulated_tools = []
real_tool_calls = []
rejected_logprobs = []
rejected_transcripts = []

for line in lines:
    if "[AUTO VAD] Speech detected!" in line:
        vad_detections += 1
    elif "[AUTO VAD] Capture returned EMPTY AUDIO" in line:
        vad_empty += 1
    elif "🛑 [STT GUARD] Rejected low-confidence transcript" in line:
        stt_rejected += 1
        # Extract no_speech_prob and avg_logprob if present
        m = re.search(r"avg_logprob=(-?\d+\.\d+)", line)
        if m:
            rejected_logprobs.append(float(m.group(1)))
    elif "[Voz Detectada]:" in line:
        stt_accepted += 1
    elif "413" in line or "Request Entity Too Large" in line or "payload_too_large" in line:
        http_413_count += 1
    elif "429" in line or "RateLimit" in line:
        http_429_count += 1
    elif "LLM" in line and "generate" in line and "success" in line:
        llm_success += 1

    if "<tool" in line or "sonido_test" in line or "esonia_test" in line or "donilla_test" in line:
        simulated_tools.append(line.strip())
    if "Executing tool" in line or "Tool call:" in line:
        real_tool_calls.append(line.strip())

print(f"\n--- STT & VAD METRICS ---")
print(f"VAD Speech Detections: {vad_detections}")
print(f"VAD Empty Audio: {vad_empty}")
print(f"STT Accepted: {stt_accepted}")
print(f"STT Rejected: {stt_rejected}")
if (stt_accepted + stt_rejected) > 0:
    print(f"STT Rejection Rate: {stt_rejected / (stt_accepted + stt_rejected) * 100:.2f}%")

print(f"\n--- REJECTED LOGPROBS SUMMARY ---")
print(f"Total rejected logprob entries parsed: {len(rejected_logprobs)}")
if rejected_logprobs:
    print(f"Min avg_logprob: {min(rejected_logprobs)}")
    print(f"Max avg_logprob: {max(rejected_logprobs)}")
    print(f"Avg avg_logprob: {sum(rejected_logprobs)/len(rejected_logprobs):.2f}")

print(f"\n--- HTTP & LLM METRICS ---")
print(f"HTTP 413 Errors: {http_413_count}")
print(f"HTTP 429 Errors: {http_429_count}")

print(f"\n--- SIMULATED / FAKE TOOLS OBSERVED ---")
print(f"Count of simulated/hallucinated tool lines: {len(simulated_tools)}")
for t in simulated_tools[:10]:
    print("  ", t)

print(f"\n--- REAL TOOL CALLS OBSERVED ---")
print(f"Count of real tool call lines: {len(real_tool_calls)}")
for r in real_tool_calls[:10]:
    print("  ", r)
