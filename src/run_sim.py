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
DEMAND_END = 3600
MAX_STEPS = 7200

# ---- adaptive controller settings ----
TL = "A0"
AXES = {0: ["top0A0", "bottom0A0"],    # green phase 0 serves north-south
        2: ["left0A0", "right0A0"]}    # green phase 2 serves east-west
MIN_GREEN = 10
MAX_GREEN = 60
MAX_RED_WAIT = 60
WAIT_WEIGHT = 0.05


class AdaptiveController:
    def __init__(self):
        self.last_phase = None
        self.green_elapsed = 0

    def axis_stats(self, edges):
        queue = sum(traci.edge.getLastStepHaltingNumber(e) for e in edges)
        total_wait = sum(traci.edge.getWaitingTime(e) for e in edges)
        max_wait = 0.0
        for e in edges:
            for vid in traci.edge.getLastStepVehicleIDs(e):
                max_wait = max(max_wait, traci.vehicle.getWaitingTime(vid))
        return queue, total_wait, max_wait

    def step(self):
        phase = traci.trafficlight.getPhase(TL)

        if phase != self.last_phase:
            self.last_phase = phase
            self.green_elapsed = 0
            if phase in AXES:
                traci.trafficlight.setPhaseDuration(TL, 1000)

        if phase not in AXES:
            return

        self.green_elapsed += 1
        if self.green_elapsed < MIN_GREEN:
            return

        other = 2 if phase == 0 else 0
        g_queue, g_wait, _ = self.axis_stats(AXES[phase])
        r_queue, r_wait, r_max = self.axis_stats(AXES[other])
        g_score = g_queue + WAIT_WEIGHT * g_wait
        r_score = r_queue + WAIT_WEIGHT * r_wait

        starving = r_max >= MAX_RED_WAIT
        overrun = self.green_elapsed >= MAX_GREEN and r_queue > 0
        red_needs_it_more = r_score > 1.5 * g_score + 1

        if starving or overrun or red_needs_it_more:
            traci.trafficlight.setPhase(TL, phase + 1)
            traci.trafficlight.setPhaseDuration(TL, 3)


def run(mode, seed=42, route_file=None, save=True, verbose=True):
    cmd = ["sumo", "-c", CFG, "--seed", str(seed), "--no-step-log", "true"]
    if route_file:
        cmd += ["--route-files", route_file]
    traci.start(cmd)
    controller = AdaptiveController() if mode == "adaptive" else None

    depart, waiting, origin = {}, {}, {}
    travel_times, rows = [], []
    arrived_in_window = 0
    step = 0
    now = 0

    while traci.simulation.getMinExpectedNumber() > 0 and step < MAX_STEPS:
        traci.simulationStep()
        step += 1
        now = traci.simulation.getTime()

        for vid in traci.simulation.getDepartedIDList():
            depart[vid] = now
            waiting[vid] = 0.0
            origin[vid] = traci.vehicle.getRoadID(vid)

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

        if controller:
            controller.step()

    traci.close()

    ts = pd.DataFrame(rows)
    ts["total_queue"] = ts[INCOMING].sum(axis=1)

    per_approach = {}
    for edge in INCOMING:
        vals = [w for v, w in waiting.items() if origin[v] == edge]
        per_approach[edge] = sum(vals) / len(vals) if vals else 0.0

    summary = {
        "avg_waiting_time_s": sum(waiting.values()) / len(waiting),
        "avg_queue_length_veh": ts["total_queue"].mean(),
        "avg_travel_time_s": sum(travel_times) / len(travel_times),
        "throughput_veh_in_first_hour": arrived_in_window,
        "max_wait_any_vehicle_s": max(waiting.values()),
        "worst_approach_avg_wait_s": max(per_approach.values()),
        "unfinished_veh": len(depart) - len(travel_times),
        "sim_end_time_s": now,
    }

    if save:
        ts.to_csv(os.path.join(OUT, f"{mode}_timeseries.csv"), index=False)
        pd.Series(summary).to_csv(os.path.join(OUT, f"{mode}_summary.csv"))
    if verbose:
        print(f"--- {mode} (seed {seed}) ---")
        for k, v in summary.items():
            print(f"{k}: {v:.2f}")
        for edge, w in per_approach.items():
            print(f"  avg wait, approach {edge}: {w:.2f}")
    return summary


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "fixed"
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 42
    if mode not in ("fixed", "adaptive"):
        sys.exit("usage: python src/run_sim.py [fixed|adaptive] [seed]")
    run(mode, seed=seed)