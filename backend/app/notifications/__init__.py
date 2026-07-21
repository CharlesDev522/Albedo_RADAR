"""Alert notifications (Slack)."""

__all__ = ["NotificationDispatcher"]


def __getattr__(name: str):
    if name == "NotificationDispatcher":
        from app.notifications.dispatcher import NotificationDispatcher

        return NotificationDispatcher
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
