"""The guesses the quick-add box makes about one line of text.

These are pure — no database, no client — because the parser is where capture
either feels instant or feels like a form. Every rule here is allowed to be
wrong on an odd input; none of them is allowed to lose `raw`.
"""

from app.captures import name_from_profile_url, parse_capture


def test_a_bare_name_is_the_name() -> None:
    assert parse_capture("Jane Doe") == ("Jane Doe", None)


def test_surrounding_whitespace_is_ignored() -> None:
    # What pasting from a phone actually hands over.
    assert parse_capture("  Jane Doe\n") == ("Jane Doe", None)


def test_an_empty_line_parses_to_nothing() -> None:
    # The schema refuses this before the router ever calls the parser, but the
    # parser must not raise on it either.
    assert parse_capture("") == (None, None)
    assert parse_capture("   \n ") == (None, None)


def test_a_bare_url_is_the_url() -> None:
    name, url = parse_capture("https://example.com/team/someone")
    assert url == "https://example.com/team/someone"
    # No name guessed from an arbitrary host: an empty field a human fills in
    # beats a confident wrong guess at a person's name.
    assert name is None


def test_a_name_and_a_link_yield_both() -> None:
    assert parse_capture("Jane Doe https://linkedin.com/in/janedoe") == (
        "Jane Doe",
        "https://linkedin.com/in/janedoe",
    )


def test_the_order_does_not_matter() -> None:
    assert parse_capture("https://linkedin.com/in/janedoe Jane Doe") == (
        "Jane Doe",
        "https://linkedin.com/in/janedoe",
    )


def test_separators_between_the_two_are_dropped() -> None:
    for line in (
        "Jane Doe - https://example.com/x",
        "Jane Doe — https://example.com/x",
        "Jane Doe | https://example.com/x",
        "Jane Doe, https://example.com/x",
    ):
        assert parse_capture(line) == ("Jane Doe", "https://example.com/x"), line


def test_text_on_both_sides_of_the_link_is_kept_as_one_name() -> None:
    name, url = parse_capture("Jane https://example.com/x Doe")
    assert name == "Jane Doe"
    assert url == "https://example.com/x"


def test_trailing_punctuation_is_not_part_of_the_url() -> None:
    # "see https://example.com/x, then call" must not file a url ending in a
    # comma — a link that 404s is worse than no link.
    assert parse_capture("Jane https://example.com/x, call her") == (
        "Jane call her",
        "https://example.com/x",
    )


def test_a_linkedin_slug_becomes_a_suggested_name() -> None:
    assert parse_capture("https://www.linkedin.com/in/jane-doe") == (
        "Jane Doe",
        "https://www.linkedin.com/in/jane-doe",
    )


def test_a_trailing_id_is_dropped_from_the_slug() -> None:
    assert name_from_profile_url("https://www.linkedin.com/in/jane-doe-4b21") == "Jane Doe"
    assert name_from_profile_url("https://www.linkedin.com/in/jane-doe-2") == "Jane Doe"


def test_a_trailing_slash_does_not_confuse_the_slug() -> None:
    assert name_from_profile_url("https://linkedin.com/in/jane-doe/") == "Jane Doe"


def test_query_parameters_are_not_part_of_the_name() -> None:
    assert name_from_profile_url("https://linkedin.com/in/jane-doe?originalSubdomain=at") == (
        "Jane Doe"
    )


def test_xing_profiles_parse_too() -> None:
    assert name_from_profile_url("https://www.xing.com/profile/Jane_Doe") == "Jane Doe"


def test_a_non_profile_linkedin_url_yields_no_name() -> None:
    # A company page or a job posting is not a person.
    assert name_from_profile_url("https://www.linkedin.com/company/acme") is None
    assert name_from_profile_url("https://www.linkedin.com/jobs/view/12345") is None


def test_an_unknown_host_yields_no_name() -> None:
    assert name_from_profile_url("https://example.com/in/jane-doe") is None


def test_a_slug_that_is_only_an_id_yields_no_name() -> None:
    assert name_from_profile_url("https://linkedin.com/in/12345678") is None


def test_an_explicit_name_beats_the_slug_guess() -> None:
    # The leftover text wins: the operator typed it on purpose.
    assert parse_capture("Jane from the meetup https://linkedin.com/in/someone-else") == (
        "Jane from the meetup",
        "https://linkedin.com/in/someone-else",
    )


def test_a_malformed_url_never_raises() -> None:
    # A capture is never worth a 500, and `raw` still holds whatever this was.
    assert name_from_profile_url("https://[oops/in/jane") is None
