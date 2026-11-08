from collector.textparse import (
    parse_bedrooms,
    parse_energy_class,
    parse_features,
    parse_land_surface,
    parse_number,
    parse_rooms,
    parse_surface,
)


def test_parse_number_french_formats():
    assert parse_number("699 000 €") == 699000
    assert parse_number("50,62 m²") == 50.62
    assert parse_number("1.250.000") == 1250000
    assert parse_number("1 250,50") == 1250.5
    assert parse_number(12) == 12.0
    assert parse_number("prix sur demande") is None
    assert parse_number(True) is None


def test_rooms_surface_bedrooms():
    title = "Maison 7 pièces 130 m² - 5 chambres"
    assert parse_rooms(title) == 7
    assert parse_surface(title) == 130
    assert parse_bedrooms(title) == 5
    assert parse_bedrooms("4 chbres") == 4
    assert parse_rooms("Appartement") is None


def test_land_surface():
    assert parse_land_surface("Surf. terrain : 350 m²") == 350
    assert parse_land_surface("édifiée sur un terrain de 1 200 m2") == 1200
    assert parse_land_surface("Maison de 120 m²") is None


def test_features_positive_mentions_only():
    found = parse_features("Beau jardin, terrasse plein sud, sans ascenseur, pas de piscine. Cave.")
    assert found == {"garden": True, "terrace": True, "cellar": True}
    assert parse_features(None) == {}


def test_energy_class():
    assert parse_energy_class("DPE : B. Proche plages.") == "B"
    assert parse_energy_class("Classe énergie D") == "D"
    assert parse_energy_class("GES : E", "ges") == "E"
    assert parse_energy_class("Bel appartement") is None
