from unittest.mock import Mock

import pytest
import graphene
from graphql_sync_dataloaders import DeferredExecutionContext, SyncDataLoader

from .app import models
from .app.graphene_schema import Query


@pytest.mark.django_db
def test_sync_dataloader(django_assert_num_queries):
    # setup data
    jane_austin = models.Author.objects.create(
        name="Jane Austin",
    )
    virginia_wolf = models.Author.objects.create(
        name="Virginia Wolf",
    )

    models.Book.objects.create(
        title="Pride and Prejudice",
        author=jane_austin,
    )
    models.Book.objects.create(
        title="Mansfield Park",
        author=jane_austin,
    )
    models.Book.objects.create(
        title="Mrs. Dalloway",
        author=virginia_wolf,
    )

    schema = graphene.Schema(query=Query)

    def load_authors(keys):
        qs = models.Author.objects.filter(id__in=keys)
        author_map = {author.id: author for author in qs}
        return [author_map.get(author_id, None) for author_id in keys]

    mock_load_fn = Mock(wraps=load_authors)
    dataloader = SyncDataLoader(mock_load_fn)

    with django_assert_num_queries(2):
        result = schema.execute(
            """
            query {
                allBooks {
                    title
                    author {
                        name
                    }
                }
            }
            """,
            execution_context_class=DeferredExecutionContext,
            context_value={
                "author_dataloader": dataloader,
            },
        )

    assert not result.errors
    assert result.data
    assert result.data == {
        "allBooks": [
            {
                "title": "Pride and Prejudice",
                "author": {
                    "name": "Jane Austin",
                },
            },
            {
                "title": "Mansfield Park",
                "author": {
                    "name": "Jane Austin",
                },
            },
            {
                "title": "Mrs. Dalloway",
                "author": {
                    "name": "Virginia Wolf",
                },
            },
        ],
    }

    assert mock_load_fn.call_count == 1
