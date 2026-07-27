"""Application-specific exceptions."""


class MailerError(Exception):
    """Base exception for expected application errors."""


class ConfigurationError(MailerError):
    """Raised when configuration is missing or invalid."""


class ValidationError(MailerError):
    """Raised when campaign or recipient data is invalid."""


class SendGridError(MailerError):
    """Raised when SendGrid communication fails."""
