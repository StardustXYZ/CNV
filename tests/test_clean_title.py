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
        # Empty / whitespace
        ("", ""),
        ("   ", ""),
    ],
)
def test_clean_title(raw: str, expected: str):
    assert clean_title(raw) == expected

