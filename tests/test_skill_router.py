"""Tests for `utils.skill_router`."""

from utils.skill_router import route_skills


class TestSkillRouter:
    def test_legacy_mode_passthrough(self):
        plan = route_skills(goal="optimize service", run_mode="legacy_mode")
        assert plan.mode == "legacy_mode"
        assert plan.skill_chain == ["plan", "execute", "test", "report"]
        assert "legacy_passthrough" in plan.router_decision
        assert plan.fallback_reason == "run_mode_not_skill_mode"

    def test_skill_mode_default_chain(self):
        plan = route_skills(
            goal="optimize architecture",
            run_mode="skill_mode",
            project_profile={"languages": ["python"]},
            failure_type="none",
        )
        assert plan.mode == "skill_mode"
        assert plan.skill_chain == ["plan", "execute", "test", "report"]
        assert plan.router_decision == "skill_router:default_chain"

    def test_doc_only_fast_path_skips_test(self):
        plan = route_skills(
            goal="update docs and comment style",
            run_mode="skill_mode",
            project_profile={"languages": ["python", "javascript"]},
            failure_type="none",
        )
        assert plan.skill_chain == ["plan", "execute", "report"]
        assert plan.jump_conditions.get("execute") == "if_doc_only_then_skip_test"
        assert plan.router_decision == "skill_router:doc_only_fast_path"

    def test_recent_failures_force_test(self):
        plan = route_skills(
            goal="update docs",
            run_mode="skill_mode",
            project_profile={"languages": ["python"]},
            failure_type="build_failed",
        )
        assert plan.skill_chain == ["plan", "execute", "test", "report"]
        assert "failure_guard" in plan.router_decision

    def test_invalid_run_mode_falls_back_to_legacy(self):
        plan = route_skills(goal="any", run_mode="invalid_mode")
        assert plan.mode == "legacy_mode"
        assert plan.fallback_reason == "run_mode_not_skill_mode"

    def test_doc_goal_with_rust_keeps_test(self):
        plan = route_skills(
            goal="update docs",
            run_mode="skill_mode",
            project_profile={"languages": ["rust"]},
            failure_type="none",
        )
        assert plan.skill_chain == ["plan", "execute", "test", "report"]
        assert plan.router_decision == "skill_router:default_chain"
