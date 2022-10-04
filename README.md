# graphql-sync-dataloaders

Use DataLoaders in your Python GraphQL servers that have to run in a sync
context (i.e. Django).

## Requirements

* Python 3.8+
* graphql-core >=3.2.0

## Installation

This package can be installed from [PyPi](https://pypi.python.org/pypi/graphql-sync-dataloaders) by running:

```bash
pip install graphql-sync-dataloaders
```

## Strawberry setup

When creating your Strawberry Schema pass `DeferredExecutionContext` as the
`execution_context_class` argument:

```python
# schema.py
import strawberry
from graphql_sync_dataloaders import DeferredExecutionContext

schema = strawberry.Schema(Query, execution_context_class=DeferredExecutionContext)
```

Then create your dataloaders using the `SyncDataLoader` class:

```python
from typing import List

from graphql_sync_dataloaders import SyncDataLoader

from .app import models  # your Django models

def load_users(keys: List[int]) -> List[User]:
    qs = models.User.objects.filter(id__in=keys)
    user_map = {user.id: user for user in qs}
    return [user_map.get(key, None) for key in keys]

user_loader = SyncDataLoader(load_users)
```

You can then use the loader in your resolvers and it will automatically be
batched to reduce the number of SQL queries:

```python
import strawberry

@strawberry.type
class Query:
    @strawberry.field
    def get_user(self, id: strawberry.ID) -> User:
        return user_loader.load(id)
```

**Note: You probably want to setup your loaders in context. See
https://strawberry.rocks/docs/guides/dataloaders#usage-with-context for more
details**

The following query will only make 1 SQL query:

```graphql
fragment UserDetails on User {
  username
}

query {
  user1: getUser(id: '1') {
    ...UserDetails
  }
  user2: getUser(id: '2') {
    ...UserDetails
  }
  user3: getUser(id: '3') {
    ...UserDetails
  }
}
```


## Graphene-Django setup

**Requires graphene-django >=3.0.0b8**

When setting up your GraphQLView pass `DeferredExecutionContext` as the
`execution_context_class` argument:

```python
# urls.py
from django.urls import path
from graphene_django.views import GraphQLView
from graphql_sync_dataloaders import DeferredExecutionContext

from .schema import schema

urlpatterns = [
    path(
        "graphql",
        csrf_exempt(
            GraphQLView.as_view(
                schema=schema, 
                execution_context_class=DeferredExecutionContext
            )
        ),
    ),
]
```

Then create your dataloaders using the `SyncDataLoader` class:

```python
from typing import List

from graphql_sync_dataloaders import SyncDataLoader

from .app import models  # your Django models

def load_users(keys: List[int]) -> List[User]:
    qs = models.User.objects.filter(id__in=keys)
    user_map = {user.id: user for user in qs}
    return [user_map.get(key, None) for key in keys]

user_loader = SyncDataLoader(load_users)
```

You can then use the loader in your resolvers and it will automatically be
batched to reduce the number of SQL queries:

```python
import graphene

class Query(graphene.ObjectType):
    get_user = graphene.Field(User, id=graphene.ID)

    def resolve_get_user(root, info, id):
        return user_loader.load(id)
```

The following query will only make 1 SQL query:

```graphql
fragment UserDetails on User {
  username
}

query {
  user1: getUser(id: '1') {
    ...UserDetails
  }
  user2: getUser(id: '2') {
    ...UserDetails
  }
  user3: getUser(id: '3') {
    ...UserDetails
  }
}
```

## Chaining dataloaders

The `SyncDataLoader.load` function returns a `SyncFuture` object which, similar to
a JavaScript Promise, allows you to chain results together using the
`then(on_success: Callable)` function.

For example:

```python
def get_user_name(userId: str) -> str:
    return user_loader.load(userId).then(lambda user: user["name"])
```

You can also chain together multiple DataLoader calls:

```python
def get_best_friend_name(userId: str) -> str:
    return (
        user_loader.load(userId)
        .then(lambda user: user_loader.load(user["best_friend"]))
        .then(lambda best_friend: best_friend["name"])
      )
```


## How it works

This library implements a custom version of the graphql-core
[ExecutionContext class](https://github.com/graphql-python/graphql-core/blob/5f6a1944cf6923f6249d1575f5b3aad87e629c66/src/graphql/execution/execute.py#L171)
that is aware of the `SyncFuture` objects defined in this library. A
`SyncFuture` represents a value that hasn't been resolved to a value yet
(similiar to asycnio Futures or JavaScript Promises) and that is what the
`SyncDataLoader` returns when you call the `.load` function.

When the custom `ExecutionContext` encounters a `SyncFuture` that gets returned
from a resolver and it keeps track of them. Then after the first pass of the
exection it triggers the `SyncFuture` callbacks until there are none left. Once
there are none left the data is fully resolved and can be returned to the
caller synchronously. This allows us to implement a `DataLoader` pattern that
batches calls to a loader function, and it allows us to do this in a fully
synchronously way.

## Credits

[@Cito](https://github.com/Cito) for graphql-core and for implementing the first version of this in https://github.com/graphql-python/graphql-core/pull/155
