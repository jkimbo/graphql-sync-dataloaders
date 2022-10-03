import pytest

from graphql_sync_dataloaders import SyncFuture, InvalidStateError


def test_sync_future():

    f = SyncFuture()
    assert not f.done()
    with pytest.raises(InvalidStateError):
        f.result()
    f.set_result(42)
    assert f.result() == 42
    assert f.done()


def test_chaining():
    f = SyncFuture()
    f2 = f.then(lambda x: x * 2)
    f3 = f2.then(lambda x: f"{x}")

    f.set_result(1)

    assert f.done()
    assert f2.done()
    assert f3.done()

    assert f.result() == 1
    assert f2.result() == 2
    assert f3.result() == "2"


def test_nested_chaining():
    f = SyncFuture()
    f2 = SyncFuture()
    f3 = f.then(lambda _: f2).then(lambda x: f"{x}")

    f.set_result(1)

    assert f.done()
    assert not f2.done()
    assert not f3.done()

    f2.set_result(2)

    assert f.done()
    assert f2.done()
    assert f3.done()

    assert f.result() == 1
    assert f2.result() == 2
    assert f3.result() == "2"
