"""AWS Lambda handlers: ``api`` (HTTP requests) and ``worker`` (one shard per queue message).

They are deliberately thin: parse the input, call the pure engine in ``qmc``, read and write AWS. All
DynamoDB access lives in ``store``; logs, metrics and settings in ``common``.
"""
