import os
import sys
import pandas as pd

if "SUMO_HOME" not in os.environ:
    sys.exit("SUMO_HOME is not set")
sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))
import traci

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "..", "sumo", "sim.sumocfg")
OUT = os.path.join(HERE, "..", "results")
os.makedirs(OUT, exist_ok=True)

INCOMING = ["left0A0", "right0A0", "top0A0", "bottom0A0"]
DEMAND_END = 3600   # throughput is counted inside this window
MAX_STEPS = 7200    # safety limit so a jam can't run forever


def run():
    traci.start(["sumo", "-c", CFG, "--seed", "42", "--no-step-log", "true"])

    depart = {}          # vehicle id -> departure time
    waiting = {}         # vehicle id -> seconds spent stopped
    travel_times = []    # one entry per completed trip
    arrived_in_window = 0
    rows = []            # per-step queue lengths
    step = 0
    now = 0

    while traci.simulation.getMinExpectedNumber() > 0 and step < MAX_STEPS:
        traci.simulationStep()
        step += 1
        now = traci.simulation.getTime()

        for vid in traci.simulation.getDepartedIDList():
            depart[vid] = now
            waiting[vid] = 0.0

        for vid in traci.vehicle.getIDList():
            if traci.vehicle.getSpeed(vid) < 0.1:
                waiting[vid] += 1.0

        for vid in traci.simulation.getArrivedIDList():
            travel_times.append(now - depart[vid])
            if now <= DEMAND_END:
                arrived_in_window += 1

        row = {"time": now}
        for edge in INCOMING:
            row[edge] = traci.edge.getLastStepHaltingNumber(edge)
        rows.append(row)

    traci.close()

    ts = pd.DataFrame(rows)
    ts["total_queue"] = ts[INCOMING].sum(axis=1)
    ts.to_csv(os.path.join(OUT, "baseline_timeseries.csv"), index=False)

    summary = {
        "avg_waiting_time_s": sum(waiting.values()) / len(waiting),
        "avg_queue_length_veh": ts["total_queue"].mean(),
        "avg_travel_time_s": sum(travel_times) / len(travel_times),
        "throughput_veh_in_first_hour": arrived_in_window,
        "sim_end_time_s": now,
    }
    pd.Series(summary).to_csv(os.path.join(OUT, "baseline_summary.csv"))
    for k, v in summary.items():
        print(f"{k}: {v:.2f}")


if __name__ == "__main__":
    run()