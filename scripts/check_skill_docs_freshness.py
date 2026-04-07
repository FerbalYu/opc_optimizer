"""Check whether committed generated skill docs are up to date."""

import argparse
import os
import sys
import tempfile
from typing import List, Tuple


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_project_root_on_path() -> None:
    root = _project_root()
    if root not in sys.path:
        sys.path.insert(0, root)


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _collect_md_files(directory: str) -> List[str]:
    if not os.path.isdir(directory):
        return []
    return sorted(
        f for f in os.listdir(directory) if f.endswith(".md") and os.path.isfile(os.path.join(directory, f))
    )


def check_skill_docs_freshness(target_dir: str) -> Tuple[bool, List[str]]:
    """Compare generated skill docs with freshly rendered output."""
    _ensure_project_root_on_path()
    from scripts.gen_skill_docs import generate_skill_docs

    os.makedirs(target_dir, exist_ok=True)
    problems: List[str] = []

    with tempfile.TemporaryDirectory(prefix="opc_skill_docs_") as tmpdir:
        generate_skill_docs(output_dir=tmpdir, include_disabled=False)

        actual_files = _collect_md_files(target_dir)
        expected_files = _collect_md_files(tmpdir)

        missing = sorted(set(expected_files) - set(actual_files))
        extra = sorted(set(actual_files) - set(expected_files))

        for name in missing:
            problems.append(f"Missing generated doc: {name}")
        for name in extra:
            problems.append(f"Unexpected generated doc: {name}")

        for name in sorted(set(expected_files) & set(actual_files)):
            expected_content = _read_text(os.path.join(tmpdir, name))
            actual_content = _read_text(os.path.join(target_dir, name))
            if expected_content != actual_content:
                problems.append(f"Outdated generated doc: {name}")

    return (len(problems) == 0, problems)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check freshness of generated skill docs.")
    parser.add_argument(
        "--target-dir",
        type=str,
        default="",
        help="Directory of committed generated docs (default: skills/generated).",
    )
    args = parser.parse_args()

    default_dir = os.path.join(_project_root(), "skills", "generated")
    target_dir = args.target_dir.strip() or default_dir

    ok, problems = check_skill_docs_freshness(target_dir)
    if ok:
        print(f"Skill docs are fresh: {target_dir}")
        return 0

    print(f"Skill docs are stale: {target_dir}")
    print("Run: python scripts/gen_skill_docs.py")
    for problem in problems:
        print(f"- {problem}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

