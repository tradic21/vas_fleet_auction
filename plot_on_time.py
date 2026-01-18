import pandas as pd
import matplotlib.pyplot as plt


nearest = pd.read_csv("results_nearest.csv")
marginal = pd.read_csv("results_marginal.csv")


n = nearest.groupby("scenario", as_index=False)["on_time_pct"].mean()
n["strategy"] = "nearest"

m = marginal.groupby("scenario", as_index=False)["on_time_pct"].mean()
m["strategy"] = "marginal"

df = pd.concat([n, m], ignore_index=True)


order = ["low", "medium", "high"]
df["scenario"] = pd.Categorical(df["scenario"], categories=order, ordered=True)
df = df.sort_values("scenario")


pivot = df.pivot(index="scenario", columns="strategy", values="on_time_pct")


ax = pivot.plot(kind="bar")
ax.set_title("On-time % by scenario: nearest vs marginal")
ax.set_xlabel("")
ax.set_ylabel("On-time [%]")
ax.legend(title="")

plt.tight_layout()


plt.savefig("on_time_by_scenario.png", dpi=300)

plt.show()

