import heapq

import pytest

from folio.ordering import CRAWL_ORDERS, QueueKey, QueueOrdering

BASE = "https://www.example.com"
SEED = f"{BASE}/for-sale/leeds"
PAGE_2 = f"{BASE}/for-sale/leeds/page-2"
PAGE_3 = f"{BASE}/for-sale/leeds/page-3"


def _details(n: int) -> str:
    return f"{BASE}/details/{n}"


# A scripted portal: results pages discover listing links and more results pages.
SITE: dict[str, list[str]] = {
    SEED: [_details(1), _details(2), _details(3), _details(4), PAGE_2],
    PAGE_2: [_details(5), _details(6), PAGE_3, _details(1)],
    PAGE_3: [_details(7)],
}


def _simulate(order: str) -> list[str]:
    """Run the crawler's dequeue / visit / enqueue loop on SITE, one worker."""
    ordering = QueueOrdering(order)
    heap: list[tuple[QueueKey, str]] = []
    heapq.heappush(heap, (ordering.key(SEED, seed=True), SEED))
    visited: list[str] = []
    while heap:
        _, url = heapq.heappop(heap)
        if url in visited:
            continue
        visited.append(url)
        for link in SITE.get(url, []):
            if link not in visited:
                heapq.heappush(heap, (ordering.key(link), link))
    return visited


def test_section_order_fetches_every_results_page_first() -> None:
    assert _simulate("section") == [
        SEED,
        PAGE_2,
        PAGE_3,
        *(_details(n) for n in range(1, 8)),
    ]


def test_discovered_order_is_plain_fifo() -> None:
    assert _simulate("discovered") == [
        SEED,
        _details(1),
        _details(2),
        _details(3),
        _details(4),
        PAGE_2,
        _details(5),
        _details(6),
        PAGE_3,
        _details(7),
    ]


def test_interleave_order_round_robins_sections() -> None:
    assert _simulate("interleave") == [
        SEED,
        _details(1),
        _details(2),
        PAGE_2,
        _details(3),
        PAGE_3,
        _details(4),
        _details(5),
        _details(6),
        _details(7),
    ]


def test_interleave_rounds_count_distinct_urls_per_section() -> None:
    ordering = QueueOrdering("interleave")
    assert ordering.key(_details(1))[1] == 0
    assert ordering.key(_details(2))[1] == 1
    assert ordering.key(SEED)[1] == 0
    # Found again on another page: same round, later discovery counter.
    again = ordering.key(_details(1))
    assert again[1] == 0
    assert ordering.key(_details(3))[1] == 2


@pytest.mark.parametrize("order", CRAWL_ORDERS)
def test_seeds_go_first(order: str) -> None:
    ordering = QueueOrdering(order)
    link = ordering.key(f"{BASE}/a")
    seed = ordering.key(f"{BASE}/b", seed=True)
    if order == "section":
        # Section order ranks seeds by section like any URL (original behaviour);
        # the root URL's section ("") always ranks first.
        assert ordering.key(f"{BASE}/", seed=True) < link
    else:
        assert seed < link


def test_unknown_order_raises() -> None:
    with pytest.raises(ValueError, match="Unknown crawl order"):
        QueueOrdering("random")
