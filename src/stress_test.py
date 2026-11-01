import os
import pandas as pd
import run_sim
from scenarios import TURNS, write_all

SEEDS = [1, 2, 3, 4, 5]
EMG_EDGES = ["top0A0", "bottom0A0"]      # emergencies only on the north-south road
CONDITIONS = [                            # name, ambulances/hour, cap (s), cooldown (s)
    ("none",          0,   20,     10),
    ("capped_120",  120,   20,     10),
    ("uncapped_120", 120, 10**6,    0),
    ("capped_360",  360,   20,     10),
    ("uncapped_360", 360, 10**6,    0),
]


def emergency_route(base_route, rate):
    out = os.path.join(os.path.dirname(base_route), f"stress_{rate}.rou.xml")
    with open(base_route) as f:
        content = f.read()
    if rate > 0:
        per_edge = rate / len(EMG_EDGES) / 3600.0
        lines = ['    <vType id="emergency" vClass="emergency" length="6" accel="3.0" '
                 'decel="5.0" sigma="0.2" maxSpeed="20.0" guiShape="emergency" color="1,0,0"/>']
        for edge in EMG_EDGES:
            dest = TURNS[edge]["straight"]
            lines.append(f'    <flow id="EMG_{edge}" type="emergency" from="{edge}" to="{dest}" '
                         f'begin="0" end="3600" probability="{per_edge:.6f}" '
                         f'departLane="best" departSpeed="max"/>')
        content = content.replace("</routes>", "\n".join(lines) + "\n</routes>")
    with open(out, "w") as f:
        f.write(content)
    return out


def main():
    base = write_all()["lopsided"]
    routes = {rate: emergency_route(base, rate) for rate in {c[1] for c in CONDITIONS}}
    rows = []
    for name, rate, cap, cool in CONDITIONS:
        run_sim.EMERGENCY_CAP = cap
        run_sim.EMERGENCY_COOLDOWN = cool
        for seed in SEEDS:
            r = run_sim.run("adaptive", seed=seed, route_file=routes[rate], save=False,
                            verbose=False, emergency_aware=True)
            rows.append(dict(r, condition=name, seed=seed))
        print(f"done {name}", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(run_sim.OUT, "stress_raw.csv"), index=False)
    out = df.groupby("condition", sort=False).agg(
        avg_wait=("avg_waiting_time_s", "mean"),
        worst_approach=("worst_approach_avg_wait_s", "mean"),
        stop_mean=("max_continuous_stop_s", "mean"),
        stop_worst=("max_continuous_stop_s", "max"),
        emg_count=("emergency_count", "mean"),
        emg_avg_wait=("emergency_avg_wait_s", "mean"),
        emg_worst_wait=("emergency_max_wait_s", "max"),
        override_max=("override_max_s", "max"),
        unfinished=("unfinished_veh", "mean"),
    ).round(2)
    out.to_csv(os.path.join(run_sim.OUT, "stress_summary.csv"))
    print(out.to_string())


if __name__ == "__main__":
    main()