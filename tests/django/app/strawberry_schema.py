from typing import List, Type

import strawberry
from strawberry.types import Info

from . import models


@strawberry.type
class Author:
    name: str

    @classmethod
    def from_instance(cls: "Type[Author]", instance: models.Author) -> "Author":
        return cls(
            name=instance.name,
        )


@strawberry.type
class Book:
    instance: strawberry.Private[models.Book]
    title: str

    @strawberry.field
    def author(self, info: Info) -> Author:
        loader = info.context["author_dataloader"]
        return loader.load(self.instance.author_id)

    @classmethod
    def from_instance(cls: "Type[Book]", instance: models.Book) -> "Book":
        return cls(
            instance=instance,
            title=instance.title,
        )


@strawberry.type
class Query:
    @strawberry.field
    def all_books() -> List[Book]:
        return [Book.from_instance(book) for book in models.Book.objects.all()]
