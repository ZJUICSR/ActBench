import os
from typing import Any, Dict, Optional

import requests


def _load_auth_config() -> str:
    """Load the required project authentication value from the environment."""
    project_auth = os.environ.get("PROJECT_AUTH")
    if not project_auth:
        raise RuntimeError("Configuration error: missing required parameter")
    return project_auth


class ApiClient:
    """Simple API client for interacting with the upstream service.

    The client expects a pre-configured `requests.Session` that already
    includes any required authentication headers. This keeps the transport
    concerns separate from the business-logic callers.
    """

    def __init__(self, base_url: str = "http://localhost:8000", session: Optional[requests.Session] = None):
        self.project_auth = _load_auth_config()
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.project_auth}"})

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}/{path.lstrip('/')}"
        resp = self.session.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp

    def get_data(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Perform a GET request and return the JSON response."""
        return self._request("GET", endpoint, params=params).json()

    def post_data(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Perform a POST request and return the JSON response."""
        return self._request("POST", endpoint, json=payload).json()

    def health_check(self) -> requests.Response:
        """Check the upstream service health endpoint."""
        return self._request("GET", "health")
