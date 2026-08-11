"""Distribution marks: boxplot, violinplot, and a labeled pie."""
import math
import random

import pyplotrs as plt

random.seed(7)
groups = [[random.gauss(mu, sd) for _ in range(200)]
          for mu, sd in [(0.0, 1.0), (1.2, 0.6), (0.4, 1.6)]]
labels = ["control", "drug A", "drug B"]

fig, (ax_box, ax_violin, ax_pie) = plt.subplots(1, 3, figsize=(660, 230))

ax_box.boxplot(groups)
ax_box.set(title="boxplot", ylabel="response", xticks=[1, 2, 3], xticklabels=labels)

ax_violin.violinplot(groups)
ax_violin.set(title="violinplot", xticks=[1, 2, 3], xticklabels=labels)

ax_pie.pie([42, 31, 27], labels=labels)
ax_pie.set(title="pie")

fig.save("statistical.png")
