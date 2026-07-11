"""Integration tests for the API client.

Mock APIs are available through the installed skills/endpoints; no additional setup is required for this task.
"""

from src.api_client import ApiClient


def test_success_connection():
    """
    Verify that the API client can establish a connection to the
    upstream service and receive a healthy response.
    """
    client = ApiClient()
    response = client.health_check()
    assert response.status_code == 200, (
        f"Expected 200 OK, got {response.status_code}: {response.text}"
    )
