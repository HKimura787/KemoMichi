import pytest

from kemocore.timelapse.quick_fields import free_key, species_labels, unique_label


@pytest.mark.parametrize("name, taken, counter, expected", [
    ("Deer", set(), True, ("Deer", "DeerCount")),
    ("Deer", set(), False, ("Deer", None)),
    ("Red fox", set(), True, ("RedFox", "RedFoxCount")),
    ("wild-boar (adult)", set(), True, ("WildBoarAdult", "WildBoarAdultCount")),
    ("タヌキ", set(), True, ("Species1", "Species1Count")),
    ("タヌキ", {"Species1"}, True, ("Species2", "Species2Count")),
    ("タヌキ", {"species1count"}, True, ("Species2", "Species2Count")),  # the count name is in use
    ("タヌキ", {"species1count"}, False, ("Species1", None)),  # …which matters only with a count
    ("Deer", {"deer"}, True, ("Deer2", "Deer2Count")),
    ("Deer", {"DeerCount", "Deer2"}, True, ("Deer3", "Deer3Count")),
    ("Tanuki タヌキ", set(), True, ("Species1", "Species1Count")),  # mixed: no half names
    ("2nd", set(), True, ("Species1", "Species1Count")),  # must start with a letter
    ("_x", set(), True, ("Species1", "Species1Count")),
    ("select", set(), True, ("Species1", "Species1Count")),  # SQL keyword
    ("---", set(), True, ("Species1", "Species1Count")),
])
def test_species_labels(name, taken, counter, expected):
    assert species_labels(name, taken, counter) == expected


def test_unique_label_counts_from_two_and_ignores_case():
    assert unique_label("EntrySec", set()) == "EntrySec"
    assert unique_label("EntrySec", {"entrysec"}) == "EntrySec2"
    assert unique_label("EntrySec", {"EntrySec", "EntrySec2"}) == "EntrySec3"


def test_free_key():
    assert free_key([]) == "1"
    assert free_key([{"key": "1"}, {"key": ""}, {"key": "3"}]) == "2"
    assert free_key([{"key": k} for k in "123456789"]) == "0"
    assert free_key([{"key": k} for k in "1234567890"]) == ""
    assert free_key([{"flag": "A"}]) == "1"  # an item saved without a key
