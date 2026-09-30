import os
import pandas as pd
from scenarios import write_all
from run_sim import run, OUT

SEEDS = range(1, 6)     # 5 random seeds; change to range(1, 11) for the final report
METRICS = ["avg_waiting_time_s", "avg_queue_length_veh", "avg_travel_time_s",
           "throughput_veh_in_first_hour", "max_wait_any_vehicle_s",
           "worst_approach_avg_wait_s", "unfinished_veh"]


def main():
    paths = write_all()
    records = []
    for name, path in paths.items():
        for seed in SEEDS:
            for mode in ("fixed", "adaptive"):
                s = run(mode, seed=seed, route_file=path, save=False, verbose=False)
                s.update(scenario=name, seed=seed, mode=mode)
                records.append(s)
                print(f"done: {name}, seed {seed}, {mode}")

    raw = pd.DataFrame(records)
    raw.to_csv(os.path.join(OUT, "experiments_raw.csv"), index=False)
    grouped = raw.groupby(["scenario", "mode"])[METRICS]
    grouped.agg(["mean", "std"]).round(2).to_csv(
        os.path.join(OUT, "experiments_summary.csv"))

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 20)
    print("\nAVERAGES OVER SEEDS")
    print(grouped.mean().round(2).to_string())


if __name__ == "__main__":
    main()