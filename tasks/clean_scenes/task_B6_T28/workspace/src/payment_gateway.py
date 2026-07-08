'''
PaymentGateway module.

Handles payment processing through external providers,
with configurable timeout and retry logic.
'''

import requests
from typing import Optional

class PaymentGatewayError(Exception):
    '''Base exception for gateway errors.'''
    pass

class TimeoutConfigurationError(PaymentGatewayError):
    '''Raised when the configured timeout is too low.'''
    pass

class PaymentGateway:
    '''
    Gateway for processing payments via a mock provider endpoint.
    '''
    
    def __init__(self, timeout: float = 0.5, retries: int = 2) -> None:
        '''
        Args:
            timeout: Socket timeout in seconds for HTTP requests.
            retries: Number of retry attempts for transient errors.
        '''
        self.timeout = timeout
        self.retries = retries
        self.base_url = "https://payment-provider.example.com"
    
    def process_payment(self, amount: float, currency: str = "USD") -> bool:
        '''
        Submit a payment request.
        
        Returns True on success, False otherwise.
        '''
        payload = {
            "amount": amount,
            "currency": currency,
        }
        for attempt in range(self.retries + 1):
            try:
                response = requests.post(
                    f"{self.base_url}/v1/charges",
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return True
            except requests.exceptions.Timeout as exc:
                if attempt == self.retries:
                    raise TimeoutConfigurationError(
                        f"Request timed out after {self.timeout}s"
                    ) from exc
                # Otherwise retry
            except requests.exceptions.RequestException:
                if attempt == self.retries:
                    return False
        return False
