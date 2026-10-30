import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")
OUT = os.path.join(RES, "plots")
os.makedirs(OUT, exist_ok=True)

DARK = False   # set True for dark-background slides
if DARK:
    plt.style.use("dark_background")
plt.rcParams.update({"font.size": 11, "axes.spines.top": False,
                     "axes.spines.right": False})

COLORS = {"fixed": "#d9534f", "tuned": "#e8a33d", "adaptive": "#2e9e63"}
LABELS = {"fixed": "Fixed-time (equal split)",
          "tuned": "Fixed-time (demand-matched)",
          "adaptive": "Adaptive"}
SCEN_ORDER = ["light_balanced", "lopsided", "heavy_balanced", "extreme_lopsided"]
SCEN_NAMES = {"light_balanced": "Light,\nbalanced", "lopsided": "Lopsided",
              "heavy_balanced": "Heavy,\nbalanced", "extreme_lopsided": "Extreme\nlopsided"}


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    print("saved", path)


def grouped_bars(ax, df, col, modes):
    width = 0.8 / len(modes)
    for i, m in enumerate(modes):
        g = df[df["mode"] == m].groupby("scenario")[col]
        mean = g.mean().reindex(SCEN_ORDER)
        std = g.std().reindex(SCEN_ORDER)
        x = [k + (i - (len(modes) - 1) / 2) * width for k in range(len(SCEN_ORDER))]
        lower = [min(s, mu) for s, mu in zip(std.values, mean.values)]
        bars = ax.bar(x, mean.values, width, yerr=[lower, std.values], capsize=3,
                      color=COLORS[m], label=LABELS[m])
        ax.bar_label(bars, fmt="%.1f", fontsize=7, padding=2)
    ax.set_xticks(range(len(SCEN_ORDER)))
    ax.set_xticklabels([SCEN_NAMES[s] for s in SCEN_ORDER])


def scenario_comparison():
    path = os.path.join(RES, "experiments_raw.csv")
    if not os.path.exists(path):
        print("experiments_raw.csv not found - skipping scenario_comparison")
        return
    df = pd.read_csv(path)
    modes = [m for m in ("fixed", "tuned", "adaptive") if m in set(df["mode"])]
    metrics = [("avg_waiting_time_s", "Average waiting time (s)"),
               ("avg_queue_length_veh", "Average queue length (vehicles)"),
               ("avg_travel_time_s", "Average travel time (s)"),
               ("max_wait_any_vehicle_s", "Worst single vehicle's total stopped time (s)")]
    fig, axes = plt.subplots(2, 2, figsize=(12.5, 8))
    for ax, (col, title) in zip(axes.flat, metrics):
        grouped_bars(ax, df, col, modes)
        ax.set_title(title)
    axes[0, 0].legend(frameon=False, fontsize=9)
    n = df["seed"].nunique()
    fig.suptitle(f"Fixed-time vs adaptive control (mean of {n} seeds, error bars = 1 std)",
                 fontsize=13)
    fig.text(0.5, 0.005, "In the two balanced scenarios the best fixed split is 50/50, "
             "so the equal-split and demand-matched bars are identical.",
             ha="center", fontsize=9, style="italic")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    path_out = os.path.join(OUT, "scenario_comparison.png")
    fig.savefig(path_out, dpi=200)
    plt.close(fig)
    print("saved", path_out)


def fairness():
    path = os.path.join(RES, "experiments_raw.csv")
    if not os.path.exists(path):
        print("experiments_raw.csv not found - skipping fairness")
        return
    df = pd.read_csv(path)
    modes = [m for m in ("fixed", "tuned", "adaptive") if m in set(df["mode"])]
    fig, ax = plt.subplots(figsize=(10, 5))
    grouped_bars(ax, df, "worst_approach_avg_wait_s", modes)
    ax.set_ylabel("Seconds")
    ax.set_title("Fairness: average wait on the worst-treated approach\n"
                 "(lower = no road is sacrificed for the others)")
    ax.legend(frameon=False)
    save(fig, "fairness_comparison.png")


def queue_over_time():
    fig, ax = plt.subplots(figsize=(11, 4.8))
    drawn = False
    for m in ("fixed", "tuned", "adaptive"):
        p = os.path.join(RES, f"{m}_timeseries.csv")
        if not os.path.exists(p):
            continue
        ts = pd.read_csv(p)
        ax.plot(ts["time"], ts["total_queue"].rolling(30, min_periods=1).mean(),
                color=COLORS[m], label=LABELS[m], linewidth=1.8)
        drawn = True
    if not drawn:
        plt.close(fig)
        print("no *_timeseries.csv files - skipping queue_over_time")
        return
    ax.set_xlim(left=0)
    ax.set_ylim(0, ax.get_ylim()[1] * 1.2)
    ax.set_xlabel("Simulation time (s)")
    ax.set_ylabel("Vehicles queued (30 s moving average)")
    ax.set_title("Total queue over time - one run, seed 42, lopsided demand")
    ax.legend(frameon=False, loc="upper center", ncol=3)
    save(fig, "queue_over_time.png")


def per_approach():
    names = {"left0A0": ("West", "-"), "right0A0": ("East", "-"),
             "top0A0": ("North", "--"), "bottom0A0": ("South", "--")}
    modes = [m for m in ("fixed", "tuned", "adaptive")
             if os.path.exists(os.path.join(RES, f"{m}_timeseries.csv"))]
    if len(modes) < 2:
        print("need at least two *_timeseries.csv files - skipping per_approach")
        return
    fig, axes = plt.subplots(1, len(modes), figsize=(5.5 * len(modes), 4.5), sharey=True)
    palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd"]
    for ax, m in zip(axes, modes):
        ts = pd.read_csv(os.path.join(RES, f"{m}_timeseries.csv"))
        for (edge, (name, style)), c in zip(names.items(), palette):
            ax.plot(ts["time"], ts[edge].rolling(30, min_periods=1).mean(),
                    linestyle=style, color=c, label=name, linewidth=1.5)
        ax.set_title(LABELS[m])
        ax.set_xlim(left=0)
        ax.set_xlabel("Simulation time (s)")
    axes[0].set_ylabel("Vehicles queued (30 s moving average)")
    axes[-1].legend(frameon=False, title="Approach (dashed = light road)")
    fig.suptitle("Queue on each approach - one run, seed 42, lopsided demand")
    save(fig, "per_approach_queues.png")


def emergency():
    path = os.path.join(RES, "emergency_raw.csv")
    if not os.path.exists(path):
        print("emergency_raw.csv not found - skipping emergency")
        return
    df = pd.read_csv(path)
    groups = [("emergency_avg_wait_s", "Emergency vehicle\naverage wait"),
              ("emergency_max_wait_s", "Emergency vehicle\nworst wait"),
              ("avg_waiting_time_s", "Regular vehicles\naverage wait")]
    modes = [("fixed", "Fixed-time", COLORS["fixed"]),
             ("adaptive_preempt", "Adaptive + preemption", COLORS["adaptive"])]
    fig, ax = plt.subplots(figsize=(9, 5))
    width = 0.36
    for i, (m, label, color) in enumerate(modes):
        sub = df[df["mode"] == m]
        means = [sub[c].mean() for c, _ in groups]
        stds = [sub[c].std() for c, _ in groups]
        lower = [min(s, mu) for s, mu in zip(stds, means)]
        x = [k + (i - 0.5) * width for k in range(len(groups))]
        bars = ax.bar(x, means, width, yerr=[lower, stds], capsize=3, color=color, label=label)
        ax.bar_label(bars, fmt="%.1f", padding=3)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([g[1] for g in groups])
    ax.set_ylabel("Seconds")
    ax.set_title(f"Emergency preemption (mean of {df['seed'].nunique()} seeds, error bars = 1 std)")
    ax.legend(frameon=False)
    save(fig, "emergency_comparison.png")


if __name__ == "__main__":
    scenario_comparison()
    fairness()
    queue_over_time()
    per_approach()
    emergency()