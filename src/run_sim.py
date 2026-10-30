import os
import sys
import pandas as pd

if "SUMO_HOME" not in os.environ:
    sys.exit("SUMO_HOME is not set")
sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))
import traci

from scenarios import SCENARIOS

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "..", "sumo", "sim.sumocfg")
OUT = os.path.join(HERE, "..", "results")
os.makedirs(OUT, exist_ok=True)

INCOMING = ["left0A0", "right0A0", "top0A0", "bottom0A0"]
DEMAND_END = 3600
MAX_STEPS = 7200

TL = "A0"
AXES = {0: ["top0A0", "bottom0A0"],
        2: ["left0A0", "right0A0"]}
MIN_GREEN = 10
MAX_GREEN = 60
MAX_RED_WAIT = 60
WAIT_WEIGHT = 0.05
DETECTION_RANGE = 150

# ---- demand-matched fixed-time baseline settings ----
CYCLE_GREEN = 84          # same total green as the default 42 + 42
MIN_TUNED_GREEN = 15      # no road gets less than this


def tuned_split(volumes):
    """Split CYCLE_GREEN between the two axes in proportion to their busiest approach."""
    ns = max(volumes["top0A0"], volumes["bottom0A0"])
    ew = max(volumes["left0A0"], volumes["right0A0"])
    total = ns + ew
    g_ns = round(CYCLE_GREEN * ns / total) if total else CYCLE_GREEN // 2
    g_ns = min(max(g_ns, MIN_TUNED_GREEN), CYCLE_GREEN - MIN_TUNED_GREEN)
    return g_ns, CYCLE_GREEN - g_ns


class TunedFixedController:
    """Fixed-time light with a demand-matched green split. No sensing, no adaptation."""
    def __init__(self, g_ns, g_ew):
        self.greens = {0: g_ns, 2: g_ew}
        self.last_phase = None
        self.elapsed = 0

    def step(self):
        phase = traci.trafficlight.getPhase(TL)
        if phase != self.last_phase:
            self.last_phase = phase
            self.elapsed = 0
            if phase in AXES:
                traci.trafficlight.setPhaseDuration(TL, 1000)
        if phase not in AXES:
            return
        self.elapsed += 1
        if self.elapsed >= self.greens[phase]:
            traci.trafficlight.setPhase(TL, phase + 1)
            traci.trafficlight.setPhaseDuration(TL, 3)


class AdaptiveController:
    def __init__(self, emergency_aware=True):
        self.last_phase = None
        self.green_elapsed = 0
        self.emergency_aware = emergency_aware
        self.preemptions = []
        self._lane_len_cache = {}

    def lane_length(self, edge):
        if edge not in self._lane_len_cache:
            self._lane_len_cache[edge] = traci.lane.getLength(edge + "_0")
        return self._lane_len_cache[edge]

    def axis_stats(self, edges):
        queue = sum(traci.edge.getLastStepHaltingNumber(e) for e in edges)
        total_wait = sum(traci.edge.getWaitingTime(e) for e in edges)
        max_wait = 0.0
        for e in edges:
            for vid in traci.edge.getLastStepVehicleIDs(e):
                max_wait = max(max_wait, traci.vehicle.getWaitingTime(vid))
        return queue, total_wait, max_wait

    def emergency_near(self, edges):
        for e in edges:
            for vid in traci.edge.getLastStepVehicleIDs(e):
                if traci.vehicle.getTypeID(vid) == "emergency":
                    dist = self.lane_length(e) - traci.vehicle.getLanePosition(vid)
                    if dist <= DETECTION_RANGE:
                        return True
        return False

    def step(self):
        phase = traci.trafficlight.getPhase(TL)
        now = traci.simulation.getTime()

        if phase != self.last_phase:
            self.last_phase = phase
            self.green_elapsed = 0
            if phase in AXES:
                traci.trafficlight.setPhaseDuration(TL, 1000)

        if phase not in AXES:
            return

        self.green_elapsed += 1
        other = 2 if phase == 0 else 0

        if self.emergency_aware:
            if self.emergency_near(AXES[phase]):
                return
            if self.green_elapsed >= 2 and self.emergency_near(AXES[other]):
                traci.trafficlight.setPhase(TL, phase + 1)
                traci.trafficlight.setPhaseDuration(TL, 3)
                self.preemptions.append((now, phase, other))
                return

        if self.green_elapsed < MIN_GREEN:
            return

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


def run(mode, seed=42, route_file=None, save=True, verbose=True,
        emergency_aware=True, volumes=None):
    """mode: 'fixed' (default 42/42), 'tuned' (demand-matched fixed), or 'adaptive'."""
    if mode == "tuned" and volumes is None:
        raise ValueError("tuned mode needs the scenario's volumes")

    cmd = ["sumo", "-c", CFG, "--seed", str(seed), "--no-step-log", "true"]
    if route_file:
        cmd += ["--route-files", route_file]
    traci.start(cmd)

    if mode == "adaptive":
        controller = AdaptiveController(emergency_aware)
    elif mode == "tuned":
        g_ns, g_ew = tuned_split(volumes)
        controller = TunedFixedController(g_ns, g_ew)
        if verbose:
            print(f"tuned fixed-time split: north-south {g_ns} s, east-west {g_ew} s")
    else:
        controller = None

    depart, waiting, origin, vtype = {}, {}, {}, {}
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
            vtype[vid] = traci.vehicle.getTypeID(vid)

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

    emg_waits = [w for v, w in waiting.items() if vtype.get(v) == "emergency"]
    reg_waits = [w for v, w in waiting.items() if vtype.get(v) != "emergency"]

    summary = {
        "avg_waiting_time_s": sum(reg_waits) / len(reg_waits) if reg_waits else 0.0,
        "avg_queue_length_veh": ts["total_queue"].mean(),
        "avg_travel_time_s": sum(travel_times) / len(travel_times),
        "throughput_veh_in_first_hour": arrived_in_window,
        "max_wait_any_vehicle_s": max(reg_waits) if reg_waits else 0.0,
        "worst_approach_avg_wait_s": max(per_approach.values()),
        "unfinished_veh": len(depart) - len(travel_times),
        "sim_end_time_s": now,
        "emergency_count": len(emg_waits),
        "emergency_avg_wait_s": sum(emg_waits) / len(emg_waits) if emg_waits else 0.0,
        "emergency_max_wait_s": max(emg_waits) if emg_waits else 0.0,
        "preemption_count": len(getattr(controller, "preemptions", [])),
    }

    if save:
        ts.to_csv(os.path.join(OUT, f"{mode}_timeseries.csv"), index=False)
        pd.Series(summary).to_csv(os.path.join(OUT, f"{mode}_summary.csv"))
    if verbose:
        print(f"--- {mode} (seed {seed}) ---")
        for k, v in summary.items():
            print(f"{k}: {v:.2f}" if isinstance(v, float) else f"{k}: {v}")
        for edge, w in per_approach.items():
            print(f"  avg wait, approach {edge}: {w:.2f}")
    return summary


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "fixed"
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 42
    if mode not in ("fixed", "tuned", "adaptive"):
        sys.exit("usage: python src/run_sim.py [fixed|tuned|adaptive] [seed]")
    # the default routes.rou.xml is the 'lopsided' scenario
    run(mode, seed=seed, volumes=SCENARIOS["lopsided"] if mode == "tuned" else None)