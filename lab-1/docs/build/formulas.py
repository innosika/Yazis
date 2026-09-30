import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["mathtext.fontset"] = "cm"
F = {
 "f15": r"$B_i = \log\left(\frac{N}{P_i}\right)$",
 "f16": r"$A_i^{\,j} = Q_i^{\,j} \cdot B_i$",
 "f31": r"$w_{dk} = \frac{N_{dk}\,\log\frac{N}{N_k}}{\sqrt{\sum_j \left(N_{dj}\,\log\frac{N}{N_j}\right)^{2}}}$",
 "f32": r"$r(D,Q) = \frac{(D,Q)}{\|D\| \cdot \|Q\|}$",
 "f33": r"$\vec{q}\,' = \alpha\,\vec{q} + \frac{\beta}{|D_r|}\sum_{d \in D_r}\vec{d} - \frac{\gamma}{|D_{nr}|}\sum_{d \in D_{nr}}\vec{d}$",
}
for name, tex in F.items():
    fig = plt.figure(figsize=(0.1, 0.1))
    t = fig.text(0, 0, tex, fontsize=15)
    fig.savefig(f"eq_{name}.png", dpi=300, bbox_inches="tight", pad_inches=0.04, transparent=False, facecolor="white")
    plt.close(fig)
print("formulas done")
