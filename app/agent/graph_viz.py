from pathlib import Path

from app.agent.graph import build_graph


def main():
    graph = build_graph()
    png = graph.get_graph().draw_mermaid_png()

    output_path = Path("docs") / "assets" / "graph.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as f:
        f.write(png)

    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
