"""Domain errors raised by services and translated to HTTP responses by routes."""


class UserNotFoundError(Exception):
    """The supplied user identity does not exist. Requests fail closed."""
