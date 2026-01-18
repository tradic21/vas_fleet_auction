import pandas as pd
import matplotlib.pyplot as plt

nearest_path = "results_nearest.csv"
marginal_path = "results_marginal.csv"

nearest_df = pd.read_csv(nearest_path)
marginal_df = pd.read_csv(marginal_path)

metric = "avg_lateness_all_sec"
group_col = "scenario"


nearest_g = nearest_df.groupby(group_col, as_index=False)[metric].mean()
marginal_g = marginal_df.groupby(group_col, as_index=False)[metric].mean()

merged = pd.merge(
    nearest_g, marginal_g,
    on=group_col,
    how="outer",
    suffixes=("_nearest", "_marginal")
)


order = ["low", "medium", "high"]
merged[group_col] = merged[group_col].astype(str).str.strip()
merged[group_col] = pd.Categorical(merged[group_col], categories=order, ordered=True)
merged = merged.sort_values(group_col)


scenarios = merged[group_col].astype(str).tolist()
x = list(range(len(scenarios)))
w = 0.4

plt.figure(figsize=(8, 5))
plt.bar([i - w/2 for i in x], merged[f"{metric}_nearest"], width=w, label="nearest")
plt.bar([i + w/2 for i in x], merged[f"{metric}_marginal"], width=w, label="marginal")

plt.xticks(x, scenarios)
plt.ylabel("Avg lateness (all) [sec]")
plt.title("Avg lateness (all) by scenario: nearest vs marginal")
plt.legend()
plt.tight_layout()

plt.savefig("avg_lateness_all_by_scenario.png", dpi=200)
plt.show()

