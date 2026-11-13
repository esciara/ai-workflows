import pytest

from ghfake import RecordingGh


@pytest.fixture
def gh():
    """A recording gh runner that answers `{}` to everything (subclass RecordingGh in a test module for more)."""
    return RecordingGh()
