from typing import List, Callable
from graphql.pyutils import is_collection

from .sync_future import SyncFuture


class DataloaderBatchCallbacks:
    """
    Singleton that stores all the batched callbacks for all dataloaders. This is
    equivalent to the async `loop.call_soon` functionality and enables the
    batching functionality of dataloaders.
    """
    _callbacks: List[Callable]

    def __init__(self) -> None:
        self._callbacks = []

    def add_callback(self, callback: Callable):
        self._callbacks.append(callback)

    def run_all_callbacks(self):
        callbacks = self._callbacks
        while callbacks:
            callbacks.pop(0)()


dataloader_batch_callbacks = DataloaderBatchCallbacks()


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
                dataloader_batch_callbacks.add_callback(self.dispatch_queue)
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
