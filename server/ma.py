# server/test_auth.py
import httpx

# Paste a fresh code from this URL in your browser:
# https://github.com/login/oauth/authorize?client_id=YOUR_CLIENT_ID&scope=read:user,user:email

CODE = "paste_code_from_browser_here"

res = httpx.post("http://localhost:8000/auth/github/callback", json={"code": CODE})
print(res.json())