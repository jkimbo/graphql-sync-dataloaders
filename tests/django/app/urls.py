from django.urls import path
from django.views.decorators.csrf import csrf_exempt
import graphene
import strawberry

from graphql_sync_dataloaders.execution_context import DeferredExecutionContext
from tests.django.app import strawberry_schema

from .graphene_schema import Query as GrapheneQuery
from .strawberry_schema import Query as StrawberryQuery
from .views import GrapheneGraphQLView, StrawberryGraphQLView

graphene_schema = graphene.Schema(query=GrapheneQuery)
strawberry_schema = strawberry.Schema(
    query=StrawberryQuery, execution_context_class=DeferredExecutionContext
)

urlpatterns = [
    path(
        "graphene-graphql",
        csrf_exempt(
            GrapheneGraphQLView.as_view(
                schema=graphene_schema, execution_context_class=DeferredExecutionContext
            )
        ),
    ),
    path("strawberry-graphql", StrawberryGraphQLView.as_view(schema=strawberry_schema)),
]
