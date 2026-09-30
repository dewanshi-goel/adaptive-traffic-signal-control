import os
from scenarios import write_all, add_emergency
from run_sim import run, OUT

SEEDS = range(1, 11)


def main():
    paths = write_all()
    base_route = paths["lopsided"]
    emg_route = os.path.join(os.path.dirname(base_route), "lopsided_emergency.rou.xml")
    with open(base_route) as f:
        content = f.read()
    with open(emg_route, "w") as f:
        f.write(content)
    add_emergency(emg_route, rate_per_hour=4.5)

    rows = []
    for seed in SEEDS:
        rows.append(dict(run("fixed", seed=seed, route_file=emg_route,
                              save=False, verbose=False), seed=seed, mode="fixed"))
        rows.append(dict(run("adaptive", seed=seed, route_file=emg_route,
                              save=False, verbose=False, emergency_aware=True),
                          seed=seed, mode="adaptive_preempt"))

    import pandas as pd
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "emergency_raw.csv"), index=False)
    cols = ["avg_waiting_time_s", "max_wait_any_vehicle_s", "worst_approach_avg_wait_s",
            "emergency_count", "emergency_avg_wait_s", "emergency_max_wait_s",
            "preemption_count", "unfinished_veh"]
    summary = df.groupby("mode")[cols].mean().round(2)
    print(summary.to_string())
    summary.to_csv(os.path.join(OUT, "emergency_summary.csv"))


if __name__ == "__main__":
    main()