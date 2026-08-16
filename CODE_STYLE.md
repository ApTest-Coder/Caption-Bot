# Code Style

The project intentionally keeps the implementation modular and readable:

- one responsibility per module
- explicit imports instead of wildcard imports
- defensive validation at input boundaries
- Telegram/API errors handled separately from unexpected exceptions
- user-facing messages kept out of low-level helpers
- persistence isolated behind the database facade
- configuration contains settings and placeholders only
- no generated secrets or deployment-specific state in source control

This document is a style reference only; it does not add runtime features.

Credit: https://github.com/Ap-Loveris
