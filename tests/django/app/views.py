from graphene_django.views import GraphQLView
from strawberry.django.views import GraphQLView as SGraphQLView
from graphql_sync_dataloaders import SyncDataLoader

from .dataloaders import load_authors


class GrapheneGraphQLView(GraphQLView):
    def get_context(self, request):
        author_dataloader = SyncDataLoader(load_authors)
        return {
            "author_dataloader": author_dataloader,
        }


class StrawberryGraphQLView(SGraphQLView):
    def get_context(self, request, response):
        author_dataloader = SyncDataLoader(load_authors)
        return {
            "author_dataloader": author_dataloader,
        }
