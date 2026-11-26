import pytest

from firmvalue.reference import BOOK_SHARES, GROUPS, MARKET_SHARES, published_shares


@pytest.mark.parametrize("group", GROUPS)
def test_published_shares_sum_to_one_hundred(group):
    assert sum(BOOK_SHARES[group].values()) == pytest.approx(100.0, abs=0.05)
    assert sum(MARKET_SHARES[group].values()) == pytest.approx(100.0, abs=0.05)


def test_long_table_shape():
    table = published_shares()
    assert len(table) == 12
    assert set(table.columns) == {"group", "input", "book", "market"}
    assert table.loc[table["input"] == "labor", "book"].eq(0).all()
