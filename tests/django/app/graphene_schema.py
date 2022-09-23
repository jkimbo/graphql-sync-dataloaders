import graphene

from . import models


class Author(graphene.ObjectType):
    name = graphene.String(required=True)


class Book(graphene.ObjectType):
    title = graphene.String(required=True)
    author = graphene.Field(Author, required=True)

    # store book instance on type
    _instance = None

    def __init__(self, _instance=None, **kwargs):
        self._instance = _instance
        super().__init__(**kwargs)

    def resolve_author(self, info):
        author_loader = info.context["author_dataloader"]

        # Note: we can't do `instance.author.id` because that would cause
        # Django fetch the author instance, so we're accessing the author_id
        # directly
        author_id = self._instance.author_id
        return author_loader.load(author_id)

    @classmethod
    def from_instance(cls, instance):
        return cls(
            _instance=instance,
            title=instance.title,
        )


class Query(graphene.ObjectType):
    all_books = graphene.List(Book)

    def resolve_all_books(self, _):
        return [Book.from_instance(book) for book in models.Book.objects.all()]
