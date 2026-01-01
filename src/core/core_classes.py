from dataclasses import dataclass
from typing import List, Dict, Any, TypedDict


@dataclass
class PaginatedReleaseRequest:
    """
    Paginated release request class.
    """

    page: int = 0
    page_size: int = 10
    sort_by: str = "artist"
    desc: bool = True
    search_query: str = ""
    artist_ids: list[int] | None = None
    genre_ids: list[int] | None = None
    style_ids: list[int] | None = None
    label_ids: list[int] | None = None
    formats: list[str] | None = None
    custom_field_filters: dict[int, list[str]] | None = None


class PaginatedTableData(TypedDict):
    """Paginated table data class."""

    rows: List[Dict[str, Any]]
    pagination: Dict[str, Any]
