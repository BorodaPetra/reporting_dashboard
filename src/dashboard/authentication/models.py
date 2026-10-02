"""Users, roles and report mailing lists — schema app of the warehouse database.

The dashboard keeps its own data in a separate schema: the warehouse schemas
(ref, sales, ...) are only read, schema app is the only place it writes to.
"""

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from dashboard import db

SCHEMA = "app"

user_roles = db.Table(
    "user_roles",
    db.Column("user_id", db.Integer, db.ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    db.Column("role_id", db.Integer, db.ForeignKey(f"{SCHEMA}.roles.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)

report_recipients = db.Table(
    "report_recipients",
    db.Column("report_id", db.Integer, db.ForeignKey(f"{SCHEMA}.reports.id", ondelete="CASCADE"), primary_key=True),
    db.Column("user_id", db.Integer, db.ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
    schema=SCHEMA,
)


class Role(db.Model):
    __tablename__ = "roles"
    __table_args__ = {"schema": SCHEMA}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)

    def __repr__(self):
        return f"<Role {self.name}>"


class User(db.Model, UserMixin):
    __tablename__ = "users"
    __table_args__ = {"schema": SCHEMA}

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), nullable=False, unique=True)
    email = db.Column(db.String(254), nullable=False, unique=True)
    firstname = db.Column(db.String(128))
    lastname = db.Column(db.String(128))
    password_hash = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean, nullable=False, server_default=db.true())

    roles = db.relationship("Role", secondary=user_roles, lazy="selectin")

    @property
    def is_active(self) -> bool:            # Flask-Login: disabled users cannot log in
        return self.active

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)   # scrypt with salt

    def check_password(self, password: str) -> bool:
        return bool(self.password_hash) and check_password_hash(self.password_hash, password)

    def has_role(self, name: str) -> bool:
        return any(role.name == name for role in self.roles)

    def __repr__(self):
        return f"<User {self.username}>"


class Report(db.Model):
    """A report with a mailing list (replaces addresses in code / .env later)."""

    __tablename__ = "reports"
    __table_args__ = {"schema": SCHEMA}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)

    recipients = db.relationship("User", secondary=report_recipients, lazy="selectin")
