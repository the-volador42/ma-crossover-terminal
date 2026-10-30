# Security notes

- Never commit `.env`, broker tokens, cookies, or account identifiers.
- Keep the HTTP/WebSocket servers bound to localhost unless you add authentication and network hardening.
- This terminal displays market data and generates signals; it does not send trading orders.
