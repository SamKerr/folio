"""Crawl queue ordering: the priority key each discovered URL is queued under."""

from __future__ import annotations

from typing import Literal, get_args

from folio.urls import url_path_depth, url_path_section

CrawlOrder = Literal["section", "discovered", "interleave"]
CRAWL_ORDERS: tuple[str, ...] = get_args(CrawlOrder)
DEFAULT_CRAWL_ORDER: CrawlOrder = "section"
DEFAULT_DATA_ONLY_CRAWL_ORDER: CrawlOrder = "interleave"

QueueKey = tuple[int, int, int, int]


class QueueOrdering:
    """Compute priority-queue keys for one crawl (smaller keys are fetched first).

    Every key ends with a discovery counter, so keys are unique and ties go to
    the URL discovered first.

    - ``section``: ``(0, section_rank, depth, order)`` - every URL of the first
      path section seen is fetched before any URL of a later section, shallower
      paths first (Folio's original order).
    - ``discovered``: ``(seed_tier, 0, 0, order)`` - plain breadth-first FIFO by
      discovery order.
    - ``interleave``: ``(seed_tier, round, 0, order)`` - round-robin across path
      sections. ``round`` is how many distinct URLs of the same section were
      queued before this one, so the queue serves the first URL of every
      section, then the second of every section, and so on. A section first
      seen late (listing pages found on results pages) starts at round 0 and is
      served ahead of the later rounds of a section that has queued many URLs.

    ``seed_tier`` is 0 for start URLs and 1 otherwise, so seeds go first.
    """

    def __init__(self, order: str = DEFAULT_CRAWL_ORDER) -> None:
        if order not in CRAWL_ORDERS:
            msg = f"Unknown crawl order {order!r}; expected one of {CRAWL_ORDERS}"
            raise ValueError(msg)
        self.order = order
        self._counter = 0
        self._section_ranks: dict[str, int] = {"": 0}
        self._section_queued: dict[str, int] = {}
        self._rounds: dict[str, int] = {}

    def key(self, url: str, *, seed: bool = False) -> QueueKey:
        """Return the queue key for ``url`` (call once per enqueue)."""
        self._counter += 1
        order = self._counter
        seed_tier = 0 if seed else 1
        if self.order == "discovered":
            return (seed_tier, 0, 0, order)
        section = url_path_section(url)
        if self.order == "section":
            rank = self._section_ranks.setdefault(section, len(self._section_ranks))
            return (0, rank, url_path_depth(url), order)
        # interleave: a URL queued again (found on another page) keeps its round.
        round_ = self._rounds.get(url)
        if round_ is None:
            round_ = self._section_queued.get(section, 0)
            self._section_queued[section] = round_ + 1
            self._rounds[url] = round_
        return (seed_tier, round_, 0, order)
