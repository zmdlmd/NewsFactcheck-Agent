from __future__ import annotations

from pathlib import Path
import sys


STRUCTURE = {
        "app": {
            "__init__.py": None,
            "main.py": None,
            "api.py": None,
            "core": {
                "config.py": None,
                "logging.py": None,
            },
            "storage": {
                "sessions.py": None,
            },
            "agent": {
                "__init__.py": None,
                "graph.py": None,
                "nodes.py": None,
                "models.py": None,
                "state.py": None,
                "render.py": None,
            },
            "tools": {
                "__init__.py": None,
                "search.py": None,
                "fetch.py": None,
            },
        },
        "eval": {
            "dataset.jsonl": None,
            "run_eval.py": None,
        },
        "data": {
            "sessions": {},  # 目录（先创建出来也无妨）
        },
        ".env.example": None,
        "requirements.txt": None,
        "README.md": None,
}


def _create_tree(base: Path, node: dict) -> None:
    """
    node 是一个 dict：
      - key 是目录名或文件名
      - value 为 dict => 目录
      - value 为 None => 空文件
    """
    for name, child in node.items():
        path = base / name
        if isinstance(child, dict):
            path.mkdir(parents=True, exist_ok=True)
            _create_tree(path, child)
        elif child is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
        else:
            raise TypeError(f"Unsupported node type for {path}: {type(child)}")


def main() -> None:
    root = Path.cwd()
    project_dir = root / "factcheck-ma"

    if project_dir.exists():
        print(f"Error: {project_dir} already exists. Remove/move it and try again.", file=sys.stderr)
        sys.exit(1)

    _create_tree(root, STRUCTURE)

    print(f"✅ Created project skeleton at: {project_dir}")
    print("Tip: you can now fill files with code as needed.")


if __name__ == "__main__":
    main()
