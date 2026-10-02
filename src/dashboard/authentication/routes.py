from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func

from dashboard import db
from dashboard.authentication import blueprint
from dashboard.authentication.decorators import roles_required
from dashboard.authentication.forms import (CreateAccountForm, EditAccountFormAdmin, EditAccountFormNotAdmin,
                                            LoginForm, RoleCreateForm, RoleEditForm, UserCreateForm, UserEditForm)
from dashboard.authentication.models import Role, User, user_roles
from dashboard.utils import redirect_url

BASE_ROLES = ("Admin", "User")    # cannot be deleted (by name, not by id)


def selected_roles(role_ids) -> list[Role]:
    return list(db.session.scalars(db.select(Role).where(Role.id.in_(role_ids or []))))


# Login & registration

@blueprint.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home_blueprint.index"))

    form = LoginForm(request.form)
    if form.validate_on_submit():
        user = db.session.scalar(db.select(User).filter_by(username=form.username.data))
        if user and user.active and user.check_password(form.password.data):
            login_user(user)
            return redirect(redirect_url())
        return render_template("accounts/login.html", msg="Wrong user or password or account is disabled",
                               title="Sign In", form=form)
    return render_template("accounts/login.html", title="Sign In", form=form)


@blueprint.route("/register", methods=["GET", "POST"])
def register():
    form = CreateAccountForm(request.form)
    if form.validate_on_submit():
        if db.session.scalar(db.select(User).filter_by(username=form.username.data)):
            return render_template("accounts/register.html", msg="Login already registered",
                                   title="Request access", success=False, form=form)
        if db.session.scalar(db.select(User).filter_by(email=form.email.data)):
            return render_template("accounts/register.html", msg="Email already registered",
                                   title="Request access", success=False, form=form)
        user = User(username=form.username.data, email=form.email.data, active=False)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        logout_user()
        return render_template("accounts/register.html",
                               msg="Request sent. An administrator will activate your account.",
                               title="Request access", success=True, form=form)
    return render_template("accounts/register.html", title="Request access", form=form)


@blueprint.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("authentication_blueprint.login"))


@blueprint.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    is_admin = current_user.has_role("Admin")
    form = (EditAccountFormAdmin if is_admin else EditAccountFormNotAdmin)(current_user, request.form)
    roles = db.session.scalars(db.select(Role)).all() if is_admin else current_user.roles
    form.roles.choices = [(r.id, r.name) for r in roles]

    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.firstname = form.firstname.data
        current_user.lastname = form.lastname.data
        current_user.email = form.email.data
        if form.password.data:
            current_user.set_password(form.password.data)
        if is_admin:
            roles = selected_roles(form.roles.data)
            if not any(r.name == "Admin" for r in roles):
                flash("You cannot remove the Admin role from yourself.", "danger")
                return redirect(url_for("authentication_blueprint.profile"))
            current_user.roles = roles
        db.session.commit()
        flash("Your profile updated successfully.", "success")
        return redirect(url_for("authentication_blueprint.profile"))

    if request.method == "GET":
        form.username.data = current_user.username
        form.firstname.data = current_user.firstname
        form.lastname.data = current_user.lastname
        form.email.data = current_user.email
        form.roles.data = [r.id for r in current_user.roles]
    return render_template("accounts/profile.html", title="Edit Profile", form=form,
                           user=current_user, segment=request.path)


# Administration: users

def user_status(user: User) -> str:
    return "active" if user.active else "pending" if not user.roles else "disabled"


@blueprint.route("/users")
@roles_required("Admin")
def admin_users():
    # every user in the report table (ReusableDataTable pages and searches in the browser);
    # Actions: the edit link and, but for the admin himself, the delete form
    users = db.session.scalars(db.select(User).order_by(User.username))
    table = {"columns": ["Id", "Username", "Email", "Name", "Roles", "Status", "Actions"],
             "data": [[u.id, u.username, u.email, " ".join(filter(None, (u.firstname, u.lastname))),
                       ", ".join(r.name for r in u.roles), user_status(u),
                       {"edit": url_for("authentication_blueprint.admin_user_edit", id=u.id),
                        "delete": None if u.id == current_user.id
                        else url_for("authentication_blueprint.admin_user_delete", id=u.id)}]
                      for u in users]}
    return render_template("accounts/users.html", title="Users Management", table=table,
                           user=current_user, segment=request.path)


@blueprint.route("/user-create", methods=["GET", "POST"])
@roles_required("Admin")
def admin_user_create():
    form = UserCreateForm(request.form)
    form.roles.choices = [(r.id, r.name) for r in db.session.scalars(db.select(Role))]

    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data,
                    firstname=form.firstname.data, lastname=form.lastname.data, active=form.active.data)
        user.set_password(form.password.data)
        user.roles = selected_roles(form.roles.data)
        db.session.add(user)
        db.session.commit()
        flash("User account created successfully.", "success")
        return redirect(url_for("authentication_blueprint.admin_user_edit", id=user.id))

    if request.method == "GET":
        form.active.data = True
    return render_template("accounts/user-create.html", title="Create User", form=form,
                           user=current_user, segment=request.path)


@blueprint.route("/user-edit/<int:id>", methods=["GET", "POST"])
@roles_required("Admin")
def admin_user_edit(id):
    edited = db.get_or_404(User, id)
    form = UserEditForm(edited, request.form)
    form.roles.choices = [(r.id, r.name) for r in db.session.scalars(db.select(Role))]

    if form.validate_on_submit():
        edited.username = form.username.data
        edited.firstname = form.firstname.data
        edited.lastname = form.lastname.data
        edited.email = form.email.data
        if form.password.data:
            edited.set_password(form.password.data)
        roles = selected_roles(form.roles.data)
        if edited.id == current_user.id and (not form.active.data or not any(r.name == "Admin" for r in roles)):
            flash("You cannot disable yourself or remove your own Admin role.", "danger")
            return redirect(url_for("authentication_blueprint.admin_user_edit", id=edited.id))
        edited.roles = roles
        edited.active = form.active.data
        db.session.commit()
        flash("User profile updated successfully.", "success")
        return redirect(url_for("authentication_blueprint.admin_user_edit", id=edited.id))

    if request.method == "GET":
        form.username.data = edited.username
        form.firstname.data = edited.firstname
        form.lastname.data = edited.lastname
        form.email.data = edited.email
        form.roles.data = [r.id for r in edited.roles]
        form.active.data = edited.active
    return render_template("accounts/user-edit.html", title="Edit User", form=form,
                           user=current_user, segment=request.path)


@blueprint.route("/user-delete/<int:id>", methods=["POST"])   # POST + CSRF token, never a link
@roles_required("Admin")
def admin_user_delete(id):
    if id == current_user.id:
        abort(403)                              # an administrator cannot delete himself
    db.session.delete(db.get_or_404(User, id))
    db.session.commit()
    flash(f"User (id={id}) deleted.", "success")
    return redirect(url_for("authentication_blueprint.admin_users"))


# Administration: roles

@blueprint.route("/roles")
@roles_required("Admin")
def admin_roles():
    counts = (db.select(user_roles.c.role_id, func.count().label("count"))
              .group_by(user_roles.c.role_id).subquery())
    query = (db.select(Role.id, Role.name, func.coalesce(counts.c.count, 0))
             .join_from(Role, counts, Role.id == counts.c.role_id, isouter=True)
             .order_by(Role.name))
    # every role in the report table; the base roles cannot be deleted (admin_role_delete)
    table = {"columns": ["Id", "Name", "Users with role", "Actions"],
             "data": [[role_id, name, count,
                       {"edit": url_for("authentication_blueprint.admin_role_edit", id=role_id),
                        "delete": None if name in BASE_ROLES
                        else url_for("authentication_blueprint.admin_role_delete", id=role_id)}]
                      for role_id, name, count in db.session.execute(query)]}
    return render_template("accounts/roles.html", title="Roles Management", table=table,
                           user=current_user, segment=request.path)


@blueprint.route("/role-create", methods=["GET", "POST"])
@roles_required("Admin")
def admin_role_create():
    form = RoleCreateForm(request.form)
    if form.validate_on_submit():
        role = Role(name=form.name.data)
        db.session.add(role)
        db.session.commit()
        flash("Role created successfully.", "success")
        return redirect(url_for("authentication_blueprint.admin_role_edit", id=role.id))
    return render_template("accounts/role-edit.html", title="Create Role", form=form,
                           user=current_user, segment=request.path)


@blueprint.route("/role-edit/<int:id>", methods=["GET", "POST"])
@roles_required("Admin")
def admin_role_edit(id):
    role = db.get_or_404(Role, id)
    form = RoleEditForm(role, request.form)
    if form.validate_on_submit():
        role.name = form.name.data
        db.session.commit()
        flash("Role updated successfully.", "success")
        return redirect(url_for("authentication_blueprint.admin_role_edit", id=role.id))
    if request.method == "GET":
        form.name.data = role.name
    return render_template("accounts/role-edit.html", title="Edit Role", form=form,
                           user=current_user, segment=request.path)


@blueprint.route("/role-delete/<int:id>", methods=["POST"])
@roles_required("Admin")
def admin_role_delete(id):
    role = db.get_or_404(Role, id)
    if role.name in BASE_ROLES:
        abort(403)
    db.session.delete(role)
    db.session.commit()
    flash(f"Role (id={id}) deleted.", "success")
    return redirect(url_for("authentication_blueprint.admin_roles"))
