# make_plots.py
import pandas as pd
import matplotlib.pyplot as plt

def load_with_strategy(path, strategy):
    df = pd.read_csv(path)
    df["strategy"] = strategy
    return df

df = pd.concat([
    load_with_strategy("results_nearest.csv", "nearest"),
    load_with_strategy("results_marginal.csv", "marginal"),
], ignore_index=True)

# prosjeci po scenariju i strategiji
g = df.groupby(["scenario", "strategy"], as_index=False).agg(
    on_time_pct=("on_time_pct", "mean"),
    avg_lateness_sec=("avg_lateness_sec", "mean"),
)

# ---- plot 1: on_time_pct ----
pivot1 = g.pivot(index="scenario", columns="strategy", values="on_time_pct").reindex(["low","medium","high"])
pivot1.plot(kind="bar")
plt.ylabel("On-time (%)")
plt.title("On-time po scenariju i strategiji (prosjek)")
plt.xticks(rotation=0)
plt.tight_layout()
plt.savefig("plot_on_time_pct.png", dpi=200)
plt.close()

# ---- plot 2: avg_lateness_sec ----
pivot2 = g.pivot(index="scenario", columns="strategy", values="avg_lateness_sec").reindex(["low","medium","high"])
pivot2.plot(kind="bar")
plt.ylabel("Avg lateness (s)")
plt.title("Prosječno kašnjenje po scenariju i strategiji (prosjek)")
plt.xticks(rotation=0)
plt.tight_layout()
plt.savefig("plot_avg_lateness.png", dpi=200)
plt.close()

print("Saved: plot_on_time_pct.png, plot_avg_lateness.png")
