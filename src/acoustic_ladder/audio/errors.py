"""Typed failures for read-only audio inventory and preflight operations."""


class AudioInventoryError(RuntimeError):
    """Base failure for audio inventory operations."""


class AudioBackendUnavailable(AudioInventoryError):
    """The configured read-only audio backend cannot be loaded."""


class AudioBackendQueryError(AudioInventoryError):
    """The audio backend failed while enumerating host APIs or devices."""


class AudioFormatCheckError(AudioInventoryError):
    """A format capability check failed unexpectedly."""


class AudioPersistenceError(AudioInventoryError):
    """An inventory artifact could not be persisted or verified."""
