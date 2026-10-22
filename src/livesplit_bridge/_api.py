"""High-level operations shared by the integrated and RPC clients."""

from abc import ABC, abstractmethod
from typing import TypeVar

from .models import (
    AttemptState,
    CompletedCount,
    ContextState,
    GameControlParams,
    GameSetParams,
    GameTimeOperation,
    GameTimeRequest,
    QueryMethod,
    QueryRequest,
    RpcRequest,
    RpcResult,
    RunIcons,
    RunState,
    SuccessResponse,
    TimerOperation,
    TimerParams,
    TimerRequest,
    TimerState,
)

_QueryResult = TypeVar(
    "_QueryResult", TimerState, RunState, RunIcons, AttemptState, ContextState, CompletedCount
)


class BridgeApi(ABC):
    @abstractmethod
    def request(self, request: RpcRequest) -> SuccessResponse[RpcResult]: ...

    def _query(self, method: QueryMethod, result_type: type[_QueryResult]) -> _QueryResult:
        response = self.request(QueryRequest(request_id=0, method=method))
        # The transport validates result against the requested method before returning.
        assert isinstance(response.result, result_type)
        return response.result

    def get_timer_state(self) -> TimerState:
        return self._query(QueryMethod.GET_TIMER_STATE, TimerState)

    def get_run(self) -> RunState:
        return self._query(QueryMethod.GET_RUN, RunState)

    def get_run_icons(self) -> RunIcons:
        return self._query(QueryMethod.GET_RUN_ICONS, RunIcons)

    def get_attempt(self) -> AttemptState:
        return self._query(QueryMethod.GET_ATTEMPT, AttemptState)

    def get_context_state(self) -> ContextState:
        return self._query(QueryMethod.GET_CONTEXT_STATE, ContextState)

    def get_completed_count(self) -> CompletedCount:
        return self._query(QueryMethod.GET_COMPLETED_COUNT, CompletedCount)

    def timer_operation(self, operation: TimerOperation) -> None:
        self.request(
            TimerRequest(
                request_id=0, method="timer_operation", params=TimerParams(operation=operation)
            )
        )

    def game_time_operation(
        self, operation: GameTimeOperation, *, ticks: int | None = None
    ) -> None:
        operation = GameTimeOperation(operation)
        if operation is GameTimeOperation.SET:
            if ticks is None:
                raise ValueError("set requires ticks")
            params: GameControlParams | GameSetParams = GameSetParams(operation="set", ticks=ticks)
        else:
            if ticks is not None:
                raise ValueError("ticks are only allowed for set")
            params = GameControlParams.model_validate({"operation": operation.value})
        self.request(
            GameTimeRequest.model_validate(
                {"request_id": 0, "method": "game_time_operation", "params": params}
            )
        )

    def start(self) -> None:
        self.timer_operation(TimerOperation.START)

    def split(self) -> None:
        self.timer_operation(TimerOperation.SPLIT)

    def skip(self) -> None:
        self.timer_operation(TimerOperation.SKIP)

    def undo(self) -> None:
        self.timer_operation(TimerOperation.UNDO)

    def reset(self) -> None:
        self.timer_operation(TimerOperation.RESET)

    def pause(self) -> None:
        self.timer_operation(TimerOperation.PAUSE)

    def resume(self) -> None:
        self.timer_operation(TimerOperation.RESUME)

    def initialize_game_time(self) -> None:
        self.game_time_operation(GameTimeOperation.INITIALIZE)

    def set_game_time_ticks(self, ticks: int) -> None:
        self.game_time_operation(GameTimeOperation.SET, ticks=ticks)

    def pause_game_time(self) -> None:
        self.game_time_operation(GameTimeOperation.PAUSE)

    def resume_game_time(self) -> None:
        self.game_time_operation(GameTimeOperation.RESUME)
