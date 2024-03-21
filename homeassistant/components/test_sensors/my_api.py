"""My API."""

import random


class DataResult:
    """Data result."""

    def __init__(self, value) -> None:
        """Initialize the data result."""
        self.value = value


class MyApi:
    """Test API."""

    async def async_get_data(self):
        """Get data."""
        value = random.randint(19, 23)
        result = DataResult(value)
        return result
