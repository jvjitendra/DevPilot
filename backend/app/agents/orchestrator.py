from dataclasses import dataclass
from enum import Enum

class RunStage(str, Enum):
    ISSUE = "issue"
    RETRIEVE = "retrieve"
    ANALYZE = "analyze"
    PLAN = "plan"
    PATCH = "patch"
    TEST = "test"
    APPROVAL = "approval"
    PR = "pr"

@dataclass
class AgentRun:
    run_id: str
    stage: RunStage
    retry_count: int = 0
    stopped: bool = False

MAX_TEST_RETRIES = 3
