from graphql_sync_dataloaders import SyncDataLoader

from . import models


def load_authors(keys):
    qs = models.Author.objects.filter(id__in=keys)
    author_map = {author.id: author for author in qs}
    return [author_map.get(author_id, None) for author_id in keys]
