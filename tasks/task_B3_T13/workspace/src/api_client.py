import requests
from typing import Optional, Dict, Any
import os


Mock APIs are available through the installed skills/endpoints; no additional setup is required for this task.


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

    def health_check(self) -> Dict[str, Any]:
        """Check the upstream service health endpoint."""
        return self.get_data("health")