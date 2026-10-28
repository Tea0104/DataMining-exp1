"""Optional static figure, using the matplotlib dependency already required by project 2."""

import argparse
import json
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1]


def plot(input_path, output_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.patches import FancyBboxPatch

    font_path = Path(r"C:\Windows\Fonts\msyh.ttc")
    if font_path.exists():
        font_manager.fontManager.addfont(str(font_path))
        plt.rcParams["font.sans-serif"] = [font_manager.FontProperties(fname=str(font_path)).get_name()]
    plt.rcParams["axes.unicode_minus"] = False
    data = json.loads(Path(input_path).read_text(encoding="utf-8"))
    lookup = {r["route_kind"]: r for r in data["routes"]}
    kinds = ["official_recommended", "tourist_observed", "tourist_declared"]
    titles = ["官方推荐主线", "游客叙述事件", "游客报告路线"]
    colors = ["#275d83", "#40775d", "#9b642d"]
    periods = {"morning": "上午", "noon": "中午", "afternoon": "下午", "evening": "傍晚及夜间", "unknown": "时间未知"}
    rows = max(len(lookup[k]["steps"]) for k in kinds)
    fig, ax = plt.subplots(figsize=(14, 13), dpi=180)
    ax.set_xlim(0, 12)
    ax.set_ylim(-3.2, rows + 2)
    ax.axis("off")
    ax.text(6, rows+1.65, "黄山路线层级与原文顺序", ha="center", fontsize=18, weight="bold")
    ax.text(6, rows+1.1, "项目2实体 → 项目3步骤与时间；仅处理两条开发文本", ha="center", fontsize=10, color="#52616d")
    for col, (kind, title, color) in enumerate(zip(kinds, titles, colors)):
        x = 0.25 + col*4
        route = lookup[kind]
        ax.text(x+1.75, rows+0.45, title, ha="center", fontsize=13, color=color, weight="bold")
        for i, step in enumerate(route["steps"]):
            y = rows - i - 0.75
            if i:
                ax.annotate("", xy=(x+1.75, y+0.62), xytext=(x+1.75, y+0.98),
                            arrowprops={"arrowstyle": "->", "color": color, "lw": 1})
            name = step["poi"] or " / ".join(step.get("choices", [])) or step["activity_label"]
            if step.get("choices"):
                name += "（二选一）"
            time = f'第{step["day"]}天 · {periods[step["time_period"]]}'
            if step["time"]:
                time += " " + step["time"]
            label = f'{step["order"]}. {name}\n{time}'
            box = FancyBboxPatch((x, y), 3.5, 0.62, boxstyle="round,pad=0.04,rounding_size=0.07",
                                 facecolor="#f7f9fb", edgecolor=color, linewidth=1,
                                 linestyle="--" if step["visit_status"] == "reported" else "-")
            ax.add_patch(box)
            ax.text(x+1.75, y+0.31, label, ha="center", va="center", fontsize=8.7)
    notes = [
        "官方条件支线：天海 → 光明顶 → 天海（如体力可行）；远观景点不进入必经主线。",
        "游客列表中的一线天：后文明确未前往，已排除并保留冲突证据；虚线节点仅在列表报告。",
        "箭头表示文本组织顺序，不证明直接道路连通；未知时间不补造。完整证据见 hierarchy.html 与 JSON。",
        "叙述事件为规则候选，当前没有独立路线金标准；不能把此图当作已验收的完整实际轨迹。"
    ]
    for i, note in enumerate(notes):
        ax.text(0.25, -0.7-i*0.57, note, va="top", fontsize=9, color="#3f4d58")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    for extension in ("png", "svg"):
        fig.savefig(output_dir / f"hierarchy.{extension}", bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=MODULE / "outputs/routes_huangshan.json")
    parser.add_argument("--output-dir", type=Path, default=MODULE / "outputs")
    args = parser.parse_args()
    plot(args.input, args.output_dir)
