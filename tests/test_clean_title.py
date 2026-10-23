"""Unit tests for the clean_title function."""

from __future__ import annotations

import pytest

from app.scrapers.eighteen_tickets import clean_title


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # User specified requirements
        ("PRIMETIME (1H50')", "PRIMETIME"),
        ("14+ MAMMINA", "MAMMINA"),
        ("EVENTO 8 TRAINSPOTTING 30° ANNIVERSARIO", "TRAINSPOTTING 30° ANNIVERSARIO"),
        ("#ANTEPRIMA DUNE – PARTE TRE", "DUNE – PARTE TRE"),
        # Durations in various formats
        ("SE AMI QUALCUNO DILLO (1H40')", "SE AMI QUALCUNO DILLO"),
        ("STREET FIGHTER (2H05')", "STREET FIGHTER"),
        ("FRANKIE E LE CREATURE DIMENTICATE (1H30')", "FRANKIE E LE CREATURE DIMENTICATE"),
        ("MAMMINA (1H32')", "MAMMINA"),
        ("CLAYFACE (1h45m)", "CLAYFACE"),
        ("DIO RIDE (114 min)", "DIO RIDE"),
        ("FILM DI TEST (95 minuti)", "FILM DI TEST"),
        # Age ratings
        ("14+ MAMMINA", "MAMMINA"),
        ("18+ SAW X", "SAW X"),
        ("6+ IL ROBOT SELVAGGIO", "IL ROBOT SELVAGGIO"),
        ("VM14 JOKER", "JOKER"),
        ("VM 18 TERRFIER", "TERRFIER"),
        # Event prefixes
        ("EVENTO 10 CARLO ACUTIS. IL GIOVANE SANTO", "CARLO ACUTIS. IL GIOVANE SANTO"),
        ("EVENTO € 8.00 L'ESTRANEA", "L'ESTRANEA"),
        ("EVENTO: CINEFORUM", "CINEFORUM"),
        ("EVENTO - NOTTE BIANCA", "NOTTE BIANCA"),
        # Hashtags and preview prefixes
        ("#ANTEPRIMA DUNE", "DUNE"),
        ("#ANTEPRIMA: GLADIATOR II", "GLADIATOR II"),
        ("ANTEPRIMA MEGALOPOLIS", "MEGALOPOLIS"),
        ("PRIMA VISIONE STREET FIGHTER", "STREET FIGHTER"),
        ("#EVENTO SPECIALE ANIME", "SPECIALE ANIME"),
        # Multiple stacked prefixes
        ("14+ EVENTO 8 TRAINSPOTTING 30° ANNIVERSARIO", "TRAINSPOTTING 30° ANNIVERSARIO"),
        ("14+ #ANTEPRIMA MAMMINA (1H32')", "MAMMINA"),
        ("EVENTO 10 14+ FILM SPECIALE (2H00')", "FILM SPECIALE"),
        # Preserving legitimate movie titles
        ("AVENGERS: DOOMSDAY", "AVENGERS: DOOMSDAY"),
        ("TRAINSPOTTING (RIED.)", "TRAINSPOTTING (RIED.)"),
        ("JE SO' PAZZO", "JE SO' PAZZO"),
        ("L'ESTRANEA", "L'ESTRANEA"),
        # Date suffixes (- DAL <data>)
        ("AVENGERS: DOOMSDAY - DAL 16 DICEMBRE", "AVENGERS: DOOMSDAY"),
        ("AVENGERS: DOOMSDAY - DAL 16/12", "AVENGERS: DOOMSDAY"),
        ("AVENGERS: DOOMSDAY - DAL 16/12/2026", "AVENGERS: DOOMSDAY"),
        ("AVENGERS: DOOMSDAY - DAL 16-12-2026", "AVENGERS: DOOMSDAY"),
        ("AVENGERS: DOOMSDAY – DAL 16 DICEMBRE", "AVENGERS: DOOMSDAY"),
        ("AVENGERS: DOOMSDAY - DALL'8 DICEMBRE", "AVENGERS: DOOMSDAY"),
        ("AVENGERS: DOOMSDAY - DAL 1° DICEMBRE", "AVENGERS: DOOMSDAY"),
        ("AVENGERS: DOOMSDAY - IN SALA DAL 16 DICEMBRE", "AVENGERS: DOOMSDAY"),
        ("AVENGERS: DOOMSDAY (DAL 16 DICEMBRE)", "AVENGERS: DOOMSDAY"),
        ("AVENGERS: DOOMSDAY - DAL 16", "AVENGERS: DOOMSDAY"),
        ("AVENGERS: DOOMSDAY - DAL DICEMBRE", "AVENGERS: DOOMSDAY"),
        ("mammina (other mommy)", "mammina (other mommy)"),
        ("mammina (other mommy) - DAL 15 OTTOBRE", "mammina (other mommy)"),
        ("14+ AVENGERS: DOOMSDAY - DAL 16 DICEMBRE (2H30')", "AVENGERS: DOOMSDAY"),
        # Empty / whitespace
        ("", ""),
        ("   ", ""),
    ],
)
def test_clean_title(raw: str, expected: str):
    assert clean_title(raw) == expected


def test_clean_title_release_from_extraction():
    from datetime import date

    # AVENGERS: DOOMSDAY - DAL 16 DICEMBRE
    res1 = clean_title("AVENGERS: DOOMSDAY - DAL 16 DICEMBRE", reference_date=date(2026, 10, 18))
    assert res1 == "AVENGERS: DOOMSDAY"
    assert res1.release_from == date(2026, 12, 16)

    # With numeric slash: DAL 16/12/2026
    res2 = clean_title("AVENGERS: DOOMSDAY - DAL 16/12/2026", reference_date=date(2026, 10, 18))
    assert res2 == "AVENGERS: DOOMSDAY"
    assert res2.release_from == date(2026, 12, 16)

    # In parentheses: (DAL 16 DICEMBRE)
    res3 = clean_title("AVENGERS: DOOMSDAY (DAL 16 DICEMBRE)", reference_date=date(2026, 10, 18))
    assert res3 == "AVENGERS: DOOMSDAY"
    assert res3.release_from == date(2026, 12, 16)

    # DALL'8 DICEMBRE
    res4 = clean_title("AVENGERS: DOOMSDAY - DALL'8 DICEMBRE", reference_date=date(2026, 10, 18))
    assert res4.release_from == date(2026, 12, 8)

    # No date suffix
    res5 = clean_title("MAMMINA (1H32')", reference_date=date(2026, 10, 18))
    assert res5 == "MAMMINA"
    assert res5.release_from is None


@pytest.mark.parametrize(
    "raw",
    [
        "LONTANO DAL MARE",
        "DAL SETTIMO CIELO",
        "UNA DONNA DA 10",
        "DA 5 BLOODS",
        "PRADA 2",
        "TRAINSPOTTING DAL 1996",
        "SANDAL 5",
    ],
)
def test_clean_title_no_release_from_inside_title(raw: str):
    """'DA'/'DAL' words inside the title must not be read as a release date."""
    from datetime import date

    res = clean_title(raw, reference_date=date(2026, 10, 23))
    assert res == raw
    assert res.release_from is None


def test_clean_title_release_from_before_duration():
    from datetime import date

    res = clean_title("AVENGERS: DOOMSDAY - DAL 16 DICEMBRE (2H30')", reference_date=date(2026, 10, 18))
    assert res == "AVENGERS: DOOMSDAY"
    assert res.release_from == date(2026, 12, 16)


def test_clean_title_release_from_two_digit_year():
    from datetime import date

    res = clean_title("AVENGERS: DOOMSDAY - DAL 16 DICEMBRE 27", reference_date=date(2026, 10, 18))
    assert res == "AVENGERS: DOOMSDAY"
    assert res.release_from == date(2027, 12, 16)
