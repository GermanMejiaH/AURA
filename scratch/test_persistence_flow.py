from aura.config import ConfigurationManager
from aura.container import DependencyContainer
from aura.memory import MemoryModule, Fact
from aura.cognition.memory_detector import ExplicitMemoryDetector
from aura.cognition.intent import ControlIntentDetector
import os

db_path = "data/test_persistence.db"
if os.path.exists(db_path):
    os.remove(db_path)

print("=== FASE 4 — PRUEBA DE PERSISTENCIA REAL Y SURVIVAL EN REINICIO ===")

# --- STEP 1: INITIAL BOOT AND WRITE ---
print("\n1. Booting MemoryModule Instance 1...")
config1 = ConfigurationManager()
config1.set("memory.db_path", db_path)
container1 = DependencyContainer()
mem_module1 = MemoryModule(config=config1, container=container1)
mem_module1.on_initialize()

user_input_write = "Mi color favorito es azul"
print(f"User Input: '{user_input_write}'")

directive = ExplicitMemoryDetector.detect(user_input_write)
print(f"Memory Directive Detected: {directive.detected}")
print(f"Extracted: subject='{directive.subject}', predicate='{directive.predicate}', object_val='{directive.object_val}'")

if directive.detected:
    mem_module1.semantic.add_fact(
        Fact(
            subject=directive.subject,
            predicate=directive.predicate,
            object_val=directive.object_val,
            source="user",
        )
    )
    mem_module1.preferences.set_preference(directive.predicate, directive.object_val)
    print("Memory saved to Semantic and Preferences in Instance 1.")

# Close instance 1 completely (Simulating reboot)
if mem_module1.store:
    mem_module1.store.close()
del mem_module1
del container1
del config1
print("\n--> INSTANCE 1 TERMINATED (Full System Reboot Simulated)")

# --- STEP 2: SECOND BOOT AND RETRIEVAL ---
print("\n2. Booting MemoryModule Instance 2 (Cold Start from SQLite)...")
config2 = ConfigurationManager()
config2.set("memory.db_path", db_path)
container2 = DependencyContainer()
mem_module2 = MemoryModule(config=config2, container=container2)
mem_module2.on_initialize()

user_input_read = "¿Cuál es mi color favorito?"
print(f"User Input Query: '{user_input_read}'")

is_direct = ControlIntentDetector.is_direct_memory_query(user_input_read)
print(f"Direct Memory Fast-Path Query Detected: {is_direct}")

retrieval_res = mem_module2.retrieval.query(user_input_read)
print(f"Facts Retrieved ({len(retrieval_res.facts)}): {[f.predicate + '=' + f.object_val for f in retrieval_res.facts]}")
print(f"Preferences Retrieved ({len(retrieval_res.preferences)}): {[p.key + '=' + p.value for p in retrieval_res.preferences]}")

if retrieval_res.facts:
    top_fact = retrieval_res.facts[0]
    formatted_resp = f"Tu {top_fact.predicate} es {top_fact.object_val}."
    print(f"Formatted Final Answer: '{formatted_resp}'")

# Cleanup test db
if mem_module2.store:
    mem_module2.store.close()
if os.path.exists(db_path):
    os.remove(db_path)

print("\n=== VERIFICACIÓN COMPLETADA ===")
