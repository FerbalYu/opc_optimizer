from typing import TypedDict, List, Any, Optional
from pydantic import BaseModel, Field, field_validator

# --- configuration definitions ---


class OptimizerConfig(BaseModel):
    """Configuration for the local optimizer."""

    project_path: str = Field(
        description="The absolute path to the target project directory"
    )
    optimization_goal: str = Field(
        default="All dimensions (Performance, Quality, Architecture, Security, Tests)",
        description="The primary goal or dimension for optimization",
    )
    max_rounds: int = Field(
        default=5, description="Maximum number of optimization rounds before stopping"
    )
    archive_every_n_rounds: int = Field(
        default=3, description="Archive historical data every N rounds"
    )
    round_timeout: int = Field(
        default=600, description="Max seconds per optimization round, 0=disabled"
    )


class OptimizerStateModel(BaseModel):
    """Pydantic模型用于状态验证（v2.x 渐进式迁移）。

    注意：LangGraph仍使用TypedDict定义，此模型提供运行时验证。
    后续将逐步迁移所有节点使用此模型。
    """

    project_path: str = ""
    optimization_goal: str = ""
    current_round: int = 1
    max_rounds: int = 5
    consecutive_no_improvements: int = 0
    suggestions: str = ""
    current_plan: str = ""
    round_contract: dict = Field(default_factory=dict)
    round_evaluation: dict = Field(default_factory=dict)
    active_tasks: List[dict] = Field(default_factory=list)
    code_diff: str = ""
    test_results: str = ""
    build_result: dict = Field(default_factory=dict)
    archive_every_n_rounds: int = 3
    round_reports: List[str] = Field(default_factory=list)
    execution_errors: List[str] = Field(default_factory=list)
    modified_files: List[str] = Field(default_factory=list)
    round_history: List[dict] = Field(default_factory=list)
    condensed_history: str = ""
    should_stop: bool = False
    auto_mode: bool = False
    dry_run: bool = False
    task_complexity: str = "medium"
    fast_path: bool = False
    consecutive_rejections: int = 0
    circuit_breaker_triggered: bool = False
    opc_workspace_dir: str = ""
    llm_config: dict = Field(default_factory=dict)
    ui_preferences: dict = Field(default_factory=dict)
    node_timings: dict = Field(default_factory=dict)
    round_metrics: dict = Field(default_factory=dict)
    round_start_time: float = 0.0
    round_timeout: int = 0

    @field_validator("task_complexity")
    @classmethod
    def validate_complexity(cls, v: str) -> str:
        if v not in ("low", "medium", "high"):
            return "medium"
        return v

    @field_validator(
        "current_round",
        "max_rounds",
        "consecutive_no_improvements",
        "archive_every_n_rounds",
        "round_timeout",
        "consecutive_rejections",
    )
    @classmethod
    def validate_positive_int(cls, v: int) -> int:
        if v < 0:
            return 0
        return v

    def to_dict(self) -> dict:
        """转换为普通字典（兼容现有代码）。"""
        return self.model_dump()

    def __getitem__(self, key: str) -> Any:
        """支持字典式访问。"""
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        """支持字典式赋值。"""
        setattr(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        """支持dict.get()接口。"""
        return getattr(self, key, default)


def _validate_state(state: dict) -> OptimizerStateModel:
    """验证状态字典，添加默认值（可选使用）。"""
    return OptimizerStateModel(
        **{k: v for k, v in state.items() if hasattr(OptimizerStateModel, k)}
    )


# --- state definitions (LangGraph) ---
# 保留TypedDict以确保LangGraph兼容性


class OptimizerState(TypedDict):
    """The core state object passed between LangGraph nodes.

    注意：字段定义应与OptimizerStateModel保持一致。
    后续将逐步迁移到使用Pydantic模型。
    """

    # Context
    project_path: str
    optimization_goal: str

    # Loop Counters
    current_round: int
    max_rounds: int
    consecutive_no_improvements: int

    # Data passed between stages
    suggestions: str
    current_plan: str
    round_contract: dict
    round_evaluation: dict
    active_tasks: List[dict]
    code_diff: str
    test_results: str
    build_result: dict

    # Archive & Reporting
    archive_every_n_rounds: int
    round_reports: List[str]
    execution_errors: List[str]
    modified_files: List[str]

    # Multi-round Memory (v2.2.0)
    round_history: List[dict]
    condensed_history: str

    # Control Flags
    should_stop: bool
    auto_mode: bool
    dry_run: bool

    # Task Router (Opt-1)
    task_complexity: str
    fast_path: bool

    # Circuit Breaker (Opt-5)
    consecutive_rejections: int
    circuit_breaker_triggered: bool

    # External Workspace (Opt-6)
    opc_workspace_dir: str

    # LLM Configuration (dependency injection)
    llm_config: dict
    ui_preferences: dict

    # Performance Metrics
    node_timings: dict
    round_metrics: dict
    round_start_time: float
    round_timeout: int
