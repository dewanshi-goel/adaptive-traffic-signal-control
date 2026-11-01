import os
import itertools
import pandas as pd
import run_sim
from scenarios import SCENARIOS, write_all

SEEDS = [1, 2, 3]
WEIGHTS = [0.02, 0.05, 0.1]
MARGINS = [1.2, 1.5, 2.0]


def main():
    paths = write_all()
    rows = []
    for w, m in itertools.product(WEIGHTS, MARGINS):
        run_sim.WAIT_WEIGHT = w
        run_sim.SWITCH_MARGIN = m
        for scen in SCENARIOS:
            for seed in SEEDS:
                r = run_sim.run("adaptive", seed=seed, route_file=paths[scen],
                                save=False, verbose=False, emergency_aware=False)
                rows.append(dict(r, weight=w, margin=m, scenario=scen, seed=seed))
        print(f"done weight={w} margin={m}", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(run_sim.OUT, "sensitivity_raw.csv"), index=False)
    cols = ["avg_waiting_time_s", "worst_approach_avg_wait_s", "max_wait_any_vehicle_s"]
    out = df.groupby(["scenario", "weight", "margin"])[cols].mean().round(2)
    out.to_csv(os.path.join(run_sim.OUT, "sensitivity_summary.csv"))
    print(out.to_string())


if __name__ == "__main__":
    main()