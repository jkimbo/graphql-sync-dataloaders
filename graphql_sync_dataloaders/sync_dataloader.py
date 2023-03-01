import contextvars
from typing import Callable, List, Optional

from graphql.pyutils import is_collection

from .sync_future import SyncFuture

_dataloader_batch_callbacks: contextvars.ContextVar[
    Optional["DataloaderBatchCallbacks"]
] = contextvars.ContextVar("dataloader_batch_callbacks", default=None)


class DataloaderBatchCallbacks:
    """
    Singleton that stores all the batched callbacks for all dataloaders. This is
    equivalent to the async `loop.call_soon` functionality and enables the
    batching functionality of dataloaders.
    """

    _callbacks: List[Callable]

    def __init__(self) -> None:
        self._token: Optional[contextvars.Token] = None
        self._callbacks = []

    def __enter__(self) -> "DataloaderBatchCallbacks":
        self._token = _dataloader_batch_callbacks.set(self)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.run_all_callbacks()
        assert self._token is not None
        _dataloader_batch_callbacks.reset(self._token)

    def add_callback(self, callback: Callable):
        self._callbacks.append(callback)

    def run_all_callbacks(self):
        callbacks = self._callbacks
        while callbacks:
            callbacks.pop(0)()


class SyncDataLoader:
    def __init__(self, batch_load_fn):
        self._batch_load_fn = batch_load_fn
        self._cache = {}
        self._queue = []

    def load(self, key):
        try:
            return self._cache[key]
        except KeyError:
            future = SyncFuture()
            needs_dispatch = not self._queue
            self._queue.append((key, future))
            if needs_dispatch:
                batch_callbacks = _dataloader_batch_callbacks.get()
                if batch_callbacks is None:
                    raise RuntimeError(
                        "DeferredExecutionContext not properly configured"
                    )
                batch_callbacks.add_callback(self.dispatch_queue)
            self._cache[key] = future
            return future

    def clear(self, key):
        self._cache.pop(key, None)

    def dispatch_queue(self):
        queue = self._queue
        if not queue:
            return
        self._queue = []

        keys = [item[0] for item in queue]
        values = self._batch_load_fn(keys)
        if not is_collection(values) or len(keys) != len(values):
            raise ValueError("The batch loader does not return an expected result")

        try:
            for (key, future), value in zip(queue, values):
                if isinstance(value, Exception):
                    future.set_exception(value)
                else:
                    future.set_result(value)
        except Exception as error:
            for key, future in queue:
                self.clear(key)
                if not future.done():
                    future.set_exception(error)
