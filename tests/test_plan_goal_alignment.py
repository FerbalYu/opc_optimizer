from nodes.plan import (
    _align_contract_to_goal_targets,
    _find_goal_target_files,
    _goal_identifiers,
)


def test_goal_identifiers_keep_code_like_names_only():
    assert _goal_identifiers("优化 splitLiveThinkSections 的尾部处理") == [
        "splitLiveThinkSections"
    ]


def test_find_goal_target_files_by_identifier(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "markdown.js").write_text("export function renderMarkdown() {}\n", encoding="utf-8")
    (src / "main.js").write_text("splitLiveThinkSections(value);\n", encoding="utf-8")
    llm = src / "llm.js"
    llm.write_text(
        "export function splitLiveThinkSections(text) { return text; }\n",
        encoding="utf-8",
    )

    matches = _find_goal_target_files(
        str(tmp_path),
        [str(src / "markdown.js"), str(src / "main.js"), str(llm)],
        "优化 splitLiveThinkSections 的尾部处理",
    )

    assert matches[:2] == ["src/llm.js", "src/main.js"]


def test_align_contract_to_goal_targets_when_model_drifted():
    contract = {
        "round_objective": "优化 escapeHtml",
        "target_files": ["src/markdown.js"],
        "acceptance_checks": ["npm test"],
        "expected_diff": ["In src/markdown.js: change escapeHtml"],
    }

    aligned = _align_contract_to_goal_targets(
        contract,
        ["src/llm.js", "src/main.js"],
        "优化 splitLiveThinkSections 的尾部处理",
    )

    assert aligned["round_objective"] == "优化 splitLiveThinkSections 的尾部处理"
    assert aligned["target_files"] == ["src/llm.js", "src/main.js"]
    assert "src/llm.js" in aligned["expected_diff"][0]
