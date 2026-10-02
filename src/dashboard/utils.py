from urllib.parse import urlsplit
from flask import request, url_for


def redirect_url(default: str = "home_blueprint.index") -> str:
    """Where to go after login: ?next=... only if it is a path on this site."""
    target = request.args.get("next", "")
    parts = urlsplit(target)
    if (
        target.startswith("/")
        and not target.startswith("//")
        and not parts.scheme
        and not parts.netloc
    ):
        return target
    return url_for(default)
