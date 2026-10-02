from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def roles_required(*names: str):
    """Allow the view only to logged-in users who have ALL the given roles."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not all(current_user.has_role(n) for n in names):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
