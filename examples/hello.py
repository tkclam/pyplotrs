import os

import figurs

_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(_OUT, exist_ok=True)


def out(name: str) -> str:
    return os.path.join(_OUT, name)


fig, ax = figurs.subplots(figsize=(288, 216))
ax.line([0, 1, 2, 3], [0, 1, 4, 9], label="y = x^2")
ax.set(title="Hello, figurs", xlabel="x", ylabel="y")
fig.save(out("hello.pdf"))
fig.save(out("hello.svg"))
fig.save(out("hello.png"))
fig.save(out("hello.html"))  # self-contained page, figure inlined as vector SVG
print("done ->", _OUT)
