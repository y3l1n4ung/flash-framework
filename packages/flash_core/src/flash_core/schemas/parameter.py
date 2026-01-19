from typing import Annotated, List, Literal, Self, Tuple, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from flash_core.config import flash_settings

SortDirection: TypeAlias = Literal["asc", "desc"]
OrderingInstruction: TypeAlias = Tuple[str, SortDirection]


class PaginationParams(BaseModel):
    """
    Pagination and ordering schema for API requests.

    Examples
    --------
    Default initialization::

        >>> params = PaginationParams(limit=20)
        >>> params.get_offset()
        0

    Page-based offset calculation::

        >>> params = PaginationParams(page=3, limit=10)
        >>> params.get_offset()
        20

    Multi-field ordering parsing::

        >>> params = PaginationParams(ordering="-priority,created_at")
        >>> params.get_ordering()
        [('priority', 'desc'), ('created_at', 'asc')]
    """

    model_config = ConfigDict(
        populate_by_name=True,
        # Set to 'ignore' so extra query params don't cause validation errors
        extra="ignore",
    )
    limit: Annotated[
        int,
        Field(
            default=flash_settings.DEFAULT_LIST_PER_PAGE, description="Items per page"
        ),
    ]

    page: Annotated[
        int | None, Field(default=None, description="1-indexed page number")
    ]

    offset: Annotated[int, Field(default=0, description="Raw skip count")]

    ordering: Annotated[
        str | None, Field(default=None, description="Format: 'field1,-field2'")
    ]

    @model_validator(mode="after")
    def _validate_bounds(self) -> Self:
        """
        Clamps values to system limits.
        >>> params = PaginationParams(limit=9999) # if max is 500
        >>> params.limit
        500
        """
        self.limit = max(1, min(self.limit, flash_settings.MAX_API_LIMIT))
        self.offset = max(0, self.offset)
        return self

    def get_offset(self) -> int:
        """
        Calculates effective database offset. Page takes precedence over offset.

        >>> PaginationParams(page=2, limit=20).get_offset()
        20
        """
        if self.page is not None and self.page > 0:
            return (self.page - 1) * self.limit
        return self.offset

    def get_ordering(self) -> List[OrderingInstruction]:
        """
        Parses the ordering string into typed instructions.

        >>> PaginationParams(ordering="-name").get_ordering()
        [('name', 'desc')]
        """
        if not self.ordering:
            return []

        instructions: List[OrderingInstruction] = []
        for part in self.ordering.split(","):
            field = part.strip()
            if not field:
                continue
            if field.startswith("-"):
                instructions.append((field[1:], "desc"))
            else:
                instructions.append((field, "asc"))
        return instructions
