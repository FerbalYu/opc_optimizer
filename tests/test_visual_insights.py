from utils.visual_insights import build_round_insight, classify_file


def test_classify_file_for_file_wall():
    assert classify_file("tests/test_app.py")["category"] == "test"
    assert classify_file("ui/web/index.html")["category"] == "ui"
    assert classify_file("docs/PROGRESS.md")["category"] == "docs"
    assert classify_file("pyproject.toml")["category"] == "config"
    assert classify_file("nodes/report.py")["category"] == "source"


def test_build_round_insight_contains_selected_visual_features():
    state = {
        "current_round": 2,
        "modified_files": ["nodes/report.py", "ui/web/index.html"],
        "round_contract": {"target_files": ["nodes/report.py"]},
        "round_evaluation": {
            "value_score": 7,
            "low_value_round": False,
        },
        "build_result": {
            "test_passed": True,
            "build_passed": True,
            "validation_mode": "real",
            "real_tests_ran": True,
        },
    }
    metrics = {
        "value_score": 7,
        "files_changed_count": 2,
        "test_passed": True,
        "build_passed": True,
        "real_tests_ran": True,
    }

    insight = build_round_insight(state, metrics)

    assert insight["round"] == 2
    assert insight["health_score"] >= 7
    assert insight["value_curve_point"]["label"] in {"明显提升", "小幅提升"}
    assert insight["file_wall"]["distribution"]["source"] == 1
    assert insight["file_wall"]["distribution"]["ui"] == 1
    assert any(item["name"] == "中文可见输出" for item in insight["prompt_microscope"])
    assert insight["next_actions"]


def test_build_round_insight_penalizes_static_fallback_and_low_value():
    state = {
        "current_round": 1,
        "modified_files": [],
        "round_contract": {},
        "round_evaluation": {"value_score": 2, "low_value_round": True},
        "build_result": {
            "test_passed": True,
            "build_passed": True,
            "validation_mode": "static_fallback",
            "real_tests_ran": False,
        },
    }

    insight = build_round_insight(state, {})

    assert insight["health_score"] <= 2
    assert insight["value_label"] == "原地打转"
    assert any(action["kind"] == "verify" for action in insight["next_actions"])
