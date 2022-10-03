from typing import (
    Any,
    AsyncIterable,
    Callable,
    Dict,
    Optional,
    List,
    Iterable,
    Union,
    cast,
)
from functools import partial

from graphql import (
    ExecutionContext,
    FieldNode,
    GraphQLError,
    GraphQLObjectType,
    GraphQLOutputType,
    GraphQLResolveInfo,
    GraphQLList,
    OperationDefinitionNode,
    located_error,
)
from graphql.pyutils import (
    is_iterable,
    Path,
    AwaitableOrValue,
    Undefined,
)

from graphql.execution.execute import get_field_def
from graphql.execution.values import get_argument_values

from .sync_future import SyncFuture


PENDING_FUTURE = object()


class DeferredExecutionContext(ExecutionContext):
    """Execution for working with synchronous Futures.

    This execution context can handle synchronous Futures as resolved values.
    Deferred callbacks set in these Futures are called after the operation
    is executed and before the result is returned.
    """

    _deferred_callbacks: List[Callable]

    def execute_operation(
        self, operation: OperationDefinitionNode, root_value: Any
    ) -> Optional[AwaitableOrValue[Any]]:
        self._deferred_callbacks = []
        result = super().execute_operation(operation, root_value)

        callbacks = self._deferred_callbacks
        while callbacks:
            callbacks.pop(0)()

        if isinstance(result, SyncFuture):
            if not result.done():
                raise RuntimeError("GraphQL deferred execution failed to complete.")
            return result.result()

        return result

    def execute_fields_serially(
        self,
        parent_type: GraphQLObjectType,
        source_value: Any,
        path: Optional[Path],
        fields: Dict[str, List[FieldNode]],
    ) -> Union[AwaitableOrValue[Dict[str, Any]], SyncFuture]:
        results: AwaitableOrValue[Dict[str, Any]] = {}

        unresolved = 0
        for response_name, field_nodes in fields.items():
            field_path = Path(path, response_name, parent_type.name)
            result = self.execute_field(
                parent_type, source_value, field_nodes, field_path
            )
            if isinstance(result, SyncFuture):
                if result.done():
                    result = result.result()
                    if result is not Undefined:
                        results[response_name] = result
                else:

                    # Add placeholder so that field order is preserved
                    results[response_name] = PENDING_FUTURE

                    # noinspection PyShadowingNames, PyBroadException
                    def process_result(
                        response_name: str, result: SyncFuture, _: None
                    ) -> None:
                        nonlocal unresolved
                        awaited_result = result.result()
                        if awaited_result is not Undefined:
                            results[response_name] = awaited_result
                        else:
                            del results[response_name]
                        unresolved -= 1
                        if not unresolved:
                            future.set_result(results)

                    unresolved += 1
                    result.add_done_callback(
                        partial(process_result, response_name, result)
                    )
            elif result is not Undefined:
                results[response_name] = result

        if not unresolved:
            return results

        future = SyncFuture()
        return future

    execute_fields = execute_fields_serially

    def execute_field(
        self,
        parent_type: GraphQLObjectType,
        source: Any,
        field_nodes: List[FieldNode],
        path: Path,
    ) -> AwaitableOrValue[Any]:
        field_def = get_field_def(self.schema, parent_type, field_nodes[0])
        if not field_def:
            return Undefined
        return_type = field_def.type
        resolve_fn = field_def.resolve or self.field_resolver
        if self.middleware_manager:
            resolve_fn = self.middleware_manager.get_field_resolver(resolve_fn)
        info = self.build_resolve_info(field_def, field_nodes, parent_type, path)
        try:
            args = get_argument_values(field_def, field_nodes[0], self.variable_values)
            result = resolve_fn(source, info, **args)

            if isinstance(result, SyncFuture):

                if result.done():
                    completed = self.complete_value(
                        return_type, field_nodes, info, path, result.result()
                    )

                else:

                    callback = result.deferred_callback
                    if callback:
                        self._deferred_callbacks.append(callback)

                    # noinspection PyShadowingNames
                    def process_result(_: Any):
                        try:
                            completed = self.complete_value(
                                return_type, field_nodes, info, path, result.result()
                            )
                            if isinstance(completed, SyncFuture):

                                # noinspection PyShadowingNames
                                def process_completed(_: Any):
                                    try:
                                        future.set_result(completed.result())
                                    except Exception as raw_error:
                                        error = located_error(
                                            raw_error, field_nodes, path.as_list()
                                        )
                                        self.handle_field_error(error, return_type)
                                        future.set_result(None)

                                if completed.done():
                                    process_completed(completed.result())
                                else:

                                    completed.add_done_callback(process_completed)
                            else:
                                future.set_result(completed)
                        except Exception as raw_error:
                            error = located_error(
                                raw_error, field_nodes, path.as_list()
                            )
                            self.handle_field_error(error, return_type)
                            future.set_result(None)

                    future = SyncFuture()
                    result.add_done_callback(process_result)
                    return future

            else:
                completed = self.complete_value(
                    return_type, field_nodes, info, path, result
                )

            if isinstance(completed, SyncFuture):

                # noinspection PyShadowingNames
                def process_completed(_: Any):
                    try:
                        future.set_result(completed.result())
                    except Exception as raw_error:
                        error = located_error(raw_error, field_nodes, path.as_list())
                        self.handle_field_error(error, return_type)
                        future.set_result(None)

                if completed.done():
                    return process_completed(completed.result())

                future = SyncFuture()
                completed.add_done_callback(process_completed)
                return future

            return completed
        except Exception as raw_error:
            error = located_error(raw_error, field_nodes, path.as_list())
            self.handle_field_error(error, return_type)
            return None

    def complete_list_value(
        self,
        return_type: GraphQLList[GraphQLOutputType],
        field_nodes: List[FieldNode],
        info: GraphQLResolveInfo,
        path: Path,
        result: Union[AsyncIterable[Any], Iterable[Any]],
    ) -> Union[AwaitableOrValue[List[Any]], SyncFuture]:
        if not is_iterable(result):
            if isinstance(result, SyncFuture):

                def process_result(_: Any):
                    return self.complete_list_value(
                        return_type, field_nodes, info, path, result.result()
                    )

                if result.done():
                    return process_result(result.result())
                future = SyncFuture()
                result.add_done_callback(process_result)
                return future

            raise GraphQLError(
                "Expected Iterable, but did not find one for field"
                f" '{info.parent_type.name}.{info.field_name}'."
            )
        result = cast(Iterable[Any], result)

        item_type = return_type.of_type
        results: List[Any] = [None] * len(result)

        unresolved = 0

        for index, item in enumerate(result):
            item_path = path.add_key(index, None)

            try:
                if isinstance(item, SyncFuture):

                    if item.done():
                        completed = self.complete_value(
                            item_type, field_nodes, info, item_path, item.result()
                        )
                    else:
                        callback = item.deferred_callback
                        if callback:
                            self._deferred_callbacks.append(callback)

                        # noinspection PyShadowingNames
                        def process_item(
                            index: int,
                            item: SyncFuture,
                            item_path: Path,
                            _: Any,
                        ) -> None:
                            nonlocal unresolved
                            try:
                                completed = self.complete_value(
                                    item_type,
                                    field_nodes,
                                    info,
                                    item_path,
                                    item.result(),
                                )
                                if isinstance(completed, SyncFuture):
                                    if completed.done():
                                        results[index] = completed.result()
                                    else:

                                        # noinspection PyShadowingNames
                                        def process_completed(
                                            index: int,
                                            completed: SyncFuture,
                                            item_path: Path,
                                            _: Any,
                                        ) -> None:
                                            try:
                                                results[index] = completed.result()
                                            except Exception as raw_error:
                                                error = located_error(
                                                    raw_error,
                                                    field_nodes,
                                                    item_path.as_list(),
                                                )
                                                self.handle_field_error(
                                                    error, item_type
                                                )

                                        completed.add_done_callback(
                                            partial(
                                                process_completed,
                                                index,
                                                completed,
                                                item_path,
                                            )
                                        )
                                else:
                                    results[index] = completed
                            except Exception as raw_error:
                                error = located_error(
                                    raw_error, field_nodes, item_path.as_list()
                                )
                                self.handle_field_error(error, item_type)
                            unresolved -= 1
                            if not unresolved:
                                future.set_result(results)

                        unresolved += 1
                        item.add_done_callback(
                            partial(process_item, index, item, item_path)
                        )
                        continue
                else:
                    completed = self.complete_value(
                        item_type, field_nodes, info, item_path, item
                    )

                if isinstance(completed, SyncFuture):

                    if completed.done():
                        results[index] = completed.result()
                    else:
                        callback = completed.deferred_callback
                        if callback:
                            self._deferred_callbacks.append(callback)

                        # noinspection PyShadowingNames
                        def process_completed(
                            index: int,
                            completed: SyncFuture,
                            item_path: Path,
                            _: Any,
                        ) -> None:
                            nonlocal unresolved
                            try:
                                results[index] = completed.result()
                            except Exception as raw_error:
                                error = located_error(
                                    raw_error, field_nodes, item_path.as_list()
                                )
                                self.handle_field_error(error, item_type)
                            unresolved -= 1
                            if not unresolved:
                                future.set_result(results)

                        unresolved += 1
                        completed.add_done_callback(
                            partial(process_completed, index, completed, item_path)
                        )
                else:
                    results[index] = completed
            except Exception as raw_error:
                error = located_error(raw_error, field_nodes, item_path.as_list())
                self.handle_field_error(error, item_type)

        if not unresolved:
            return results

        future = SyncFuture()
        return future
