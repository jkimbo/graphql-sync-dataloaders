from typing import (
    Any,
    Callable,
    Optional,
    List,
)

from .exceptions import InvalidStateError

_PENDING = "PENDING"
_FINISHED = "FINISHED"


class SyncFuture:

    _state = _PENDING
    _result: Optional[Any] = None
    _exception: Optional[Exception] = None
    _callbacks: List[Callable]
    _cancel_message = None

    deferred_callback: Optional[Callable] = None

    def __init__(self):
        self._callbacks = []

    def done(self) -> bool:
        return self._state != _PENDING

    def result(self):
        self._assert_state(_FINISHED)
        if self._exception is not None:
            raise self._exception
        return self._result

    def exception(self):
        self._assert_state(_FINISHED)
        return self._exception

    def add_done_callback(self, fn: Callable) -> None:
        self._assert_state(_PENDING)
        self._callbacks.append(fn)

    def set_result(self, result: Any) -> None:
        if self is result:
            raise TypeError("Cannot resolve future with itself.")

        if isinstance(result, SyncFuture):
            result.add_done_callback(self.set_result)
        else:
            self._assert_state(_PENDING)
            self._result = result
            self._finish()

    def set_exception(self, exception: Exception) -> None:
        self._assert_state(_PENDING)
        if isinstance(exception, type):
            exception = exception()
        self._exception = exception
        self._finish()

    def _assert_state(self, state: str) -> None:
        if self._state != state:
            raise InvalidStateError(f"Future is not {state}")

    def _finish(self):
        self._state = _FINISHED
        callbacks = self._callbacks
        if not callbacks:
            return
        self._callbacks = []
        for callback in callbacks:
            callback(self._result)

    def then(self, on_complete: Callable) -> "SyncFuture":
        ret = SyncFuture()

        def call_and_resolve(v: Any) -> None:
            try:
                ret.set_result(on_complete(v))
            except Exception as e:
                ret.set_exception(e)

        self.add_done_callback(call_and_resolve)

        return ret
