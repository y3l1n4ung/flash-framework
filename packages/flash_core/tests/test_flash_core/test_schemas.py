from flash_core import PaginationParams, flash_settings


def test_default_construction():
    params = PaginationParams.model_validate({})

    assert params.limit == flash_settings.DEFAULT_LIST_PER_PAGE
    assert params.page is None
    assert params.offset == 0
    assert params.ordering is None


def test_construction_with_limit_only():
    params = PaginationParams.model_validate({"limit": 20})

    assert params.limit == 20
    assert params.page is None
    assert params.offset == 0
    assert params.ordering is None


def test_construction_with_all_fields():
    params = PaginationParams.model_validate(
        {
            "limit": 10,
            "page": 2,
            "offset": 50,
            "ordering": "-name",
        }
    )

    assert params.limit == 10
    assert params.page == 2
    assert params.offset == 50
    assert params.ordering == "-name"


def test_extra_fields_are_ignored():
    params = PaginationParams.model_validate(
        {
            "limit": 10,
            "unknown": "value",
        }
    )

    assert params.limit == 10
    assert not hasattr(params, "unknown")


def test_limit_clamped_to_max():
    params = PaginationParams.model_validate(
        {"limit": flash_settings.MAX_API_LIMIT + 100}
    )

    assert params.limit == flash_settings.MAX_API_LIMIT


def test_limit_minimum_is_one():
    params = PaginationParams.model_validate({"limit": 0})

    assert params.limit == 1


def test_offset_never_negative():
    params = PaginationParams.model_validate({"offset": -500})

    assert params.offset == 0


def test_offset_when_page_is_none():
    params = PaginationParams.model_validate({"limit": 10, "offset": 30})

    assert params.get_offset() == 30


def test_page_based_offset_calculation():
    params = PaginationParams.model_validate({"limit": 10, "page": 3})

    assert params.get_offset() == 20


def test_page_takes_precedence_over_offset():
    params = PaginationParams.model_validate({"limit": 10, "page": 2, "offset": 999})

    assert params.get_offset() == 10


def test_page_zero_or_negative_falls_back_to_offset():
    params = PaginationParams.model_validate({"limit": 10, "page": 0, "offset": 15})

    assert params.get_offset() == 15


def test_no_ordering_returns_empty_list():
    params = PaginationParams.model_validate({})

    assert params.get_ordering() == []


def test_empty_ordering_string_returns_empty_list():
    params = PaginationParams.model_validate({"ordering": ""})

    assert params.get_ordering() == []


def test_single_ascending_ordering():
    params = PaginationParams.model_validate({"ordering": "created_at"})

    assert params.get_ordering() == [("created_at", "asc")]


def test_single_descending_ordering():
    params = PaginationParams.model_validate({"ordering": "-name"})

    assert params.get_ordering() == [("name", "desc")]


def test_multi_field_ordering():
    params = PaginationParams.model_validate({"ordering": "-priority,created_at"})

    assert params.get_ordering() == [
        ("priority", "desc"),
        ("created_at", "asc"),
    ]


def test_ordering_ignores_empty_parts():
    params = PaginationParams.model_validate({"ordering": ",,-name, ,created_at,"})

    assert params.get_ordering() == [
        ("name", "desc"),
        ("created_at", "asc"),
    ]
