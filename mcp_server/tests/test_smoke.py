from server import server


def test_server_named_trip_concierge() -> None:
    assert server.name == "trip-concierge"
