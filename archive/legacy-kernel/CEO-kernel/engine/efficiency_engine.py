import json, os, statistics, psutil
from core.governance.recommendation_engine import analyze_recommendations
from core.diagnostics.network_context import can_use_api
from core.modules.public_api_connector import fetch_api_list

PROFILE_LOG = "audit/performance_profile.json"
CONFIG_FILE = "../.env"
SUMMARY_FILE = "audit/efficiency_summary.json"

def read_profiles():
    if not os.path.exists(PROFILE_LOG):
        print("[EFF] No performance data available.")
        return []
    with open(PROFILE_LOG) as f:
        return [json.loads(l) for l in f if l.strip()]

def analyze_efficiency():
    data = read_profiles()
    if not data:
        return
    avg = statistics.mean(d["elapsed"] for d in data)
    slow = [d for d in data if d["elapsed"] > avg * 1.5]

    print("\n🧠 Efficiency Report:")
    print(f"Average function time: {avg:.6f}s across {len(data)} calls.")
    if slow:
        print(f"{len(slow)} functions above threshold:")
        for s in slow:
            print(f" - {s['func']} → {s['elapsed']:.4f}s")
    else:
        print("All functions within optimal performance range.")

    auto_tune_system()
    export_summary(avg, slow)

def auto_tune_system():
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory().percent

    print(f"\n⚙️  System Load: CPU {cpu}% | MEM {mem}%")
    if cpu > 85 or mem > 85:
        update_env("AUDIT_INTERVAL", "30")
        print("[EFF] High load detected → reducing audit frequency.")
    elif cpu < 30 and mem < 50:
        update_env("AUDIT_INTERVAL", "5")
        print("[EFF] Low load detected → increasing refresh rate.")
    else:
        print("[EFF] Load stable → no tuning required.")

def update_env(key, value):
    if not os.path.exists(CONFIG_FILE):
        print(f"[EFF] Missing config: {CONFIG_FILE}")
        return
    lines, found = [], False
    with open(CONFIG_FILE) as f:
        for line in f:
            if line.startswith(key + "="):
                line = f"{key}={value}\n"
                found = True
            lines.append(line)
    if not found:
        lines.append(f"{key}={value}\n")
    with open(CONFIG_FILE, "w") as f:
        f.writelines(lines)

def export_summary(avg, slow):
    os.makedirs(os.path.dirname(SUMMARY_FILE), exist_ok=True)
    report = {
        "avg_exec_time": avg,
        "slow_functions": slow,
        "last_tune": os.path.basename(CONFIG_FILE)
    }
    with open(SUMMARY_FILE, "w") as f:
        json.dump(report, f, indent=2)
    print("\n📦 Efficiency summary saved.\n")

if __name__ == "__main__":
    analyze_efficiency()
