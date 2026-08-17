"""Vertical bar chart."""
import pyplotrs as pp

x = [0, 1, 2, 3, 4]
heights = [5.1, 7.3, 3.8, 6.4, 4.2]
fig, ax = pp.subplots()
ax.bar(x, heights, width=0.7, color="C2")
ax.set(title="Bar chart", xlabel="category", ylabel="value")
fig.save("bar.png")
