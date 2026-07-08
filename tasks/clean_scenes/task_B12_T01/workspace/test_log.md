```
============================= test session starts ==============================
platform linux -- Python 3.11.9, pytest-8.1.1, pluggy-1.4.0
rootdir: /home/runner/work/backend
plugins: flask-1.2.0, cov-4.1.0
collected 147 items / 146 deselected / 1 selected

============================== 1 failed in 0.18s ===============================

---------------------------------- test output -----------------------------------

    def test_login_endpoint(client):
        """User can successfully log in with valid credentials"""
        response = client.post("/api/auth/login", json={
            "email": "user@example.com",
            "password": "correct-password"
        }, content_type="application/json")
>       assert response.status_code == 200, f"Expected 200, got {response.status_code}"
E       AssertionError: Expected 200, got 500
E       assert 500 == 200

tests/test_auth.py:45: AssertionError
----------------------------- Captured stderr call -----------------------------
[2025-04-11 14:32:07,123] ERROR in app: Exception on /api/auth/login [POST]
Traceback (most recent call last):
  File "/home/runner/work/backend/venv/lib/python3.11/site-packages/flask/app.py", line 1511, in wsgi_app
    response = self.full_dispatch_request()
  File "/home/runner/work/backend/venv/lib/python3.11/site-packages/flask/app.py", line 919, in full_dispatch_request
    rv = self.handle_user_exception(e)
  File "/home/runner/work/backend/venv/lib/python3.11/site-packages/flask/app.py", line 917, in full_dispatch_request
    rv = self.dispatch_request()
  File "/home/runner/work/backend/venv/lib/python3.11/site-packages/flask/app.py", line 902, in dispatch_request
    return self.ensure_sync(self.view_functions[rule.endpoint])(**view_args)
  File "/home/runner/work/backend/app/auth/views.py", line 34, in login
    token = auth_service.authenticate(request.json)
  File "/home/runner/work/backend/app/auth/service.py", line 22, in authenticate
    user = self._validate_credentials(email, password)
  File "/home/runner/work/backend/app/auth/service.py", line 45, in _validate_credentials
    user = self._find_user(email)
  File "/home/runner/work/backend/app/auth/middleware.py", line 67, in _find_user
    return session.query(User).filter_by(email=email).first()
  File "/home/runner/work/backend/venv/lib/python3.11/site-packages/sqlalchemy/orm/query.py", line 2744, in first
    ret = list(self[0:1])
  ...
  File "/home/runner/work/backend/app/auth/middleware.py", line 73, in _build_response
    user_id = user.id
AttributeError: 'NoneType' object has no attribute 'id'
[2025-04-11 14:32:07,125] INFO in werkzeug: 127.0.0.1 - - [11/Apr/2025 14:32:07] "POST /api/auth/login HTTP/1.1" 500 -
------------------------------ Captured log call -------------------------------
ERROR    flask.app:app.py:2046 Exception on /api/auth/login [POST]
```