import pytest

from graphql_sync_dataloaders import SyncFuture, InvalidStateError


def test_sync_future():  # TODO: Future should be fully tested later

    f = SyncFuture()
    assert not f.done()
    with pytest.raises(InvalidStateError):
        f.result()
    f.set_result(42)
    assert f.result() == 42
    assert f.done()
