# -*- encoding: utf-8 -*-

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, widgets, SelectMultipleField, BooleanField
from wtforms.validators import Email, DataRequired, EqualTo, Optional, Length, ValidationError, StopValidation
from dashboard.authentication.models import User, Role
from werkzeug.security import check_password_hash

# validators


def v_username(message=None):
    default_message = 'Please use a different login.'

    def _v_username(form, field):
        if field.data != form.original_username:
            user = User.query.filter_by(username=field.data).first()
            if user is not None:
                raise ValidationError(message or default_message)
        
    return _v_username


def v_rolename(message=None):
    default_message = 'Please use a different Name.'

    def _v_rolename(form, field):
        if field.data != form.original_name:
            role = Role.query.filter_by(name=field.data).first()
            if role is not None:
                raise ValidationError(message or default_message)
        
    return _v_rolename


def v_email(message=None):
    default_message = 'This email already used.'

    def _v_email(form, field):
        if field.data != form.original_email:
            email = User.query.filter_by(email=field.data).first()
            if email is not None:
                raise ValidationError(message or default_message)
        
    return _v_email


def v_password(message=None):
    default_message = 'New password must be different from the current one.'
    
    def _v_password(form, field):
        if not field.data:          # '' from a browser, None if the field is missing
            raise StopValidation()

        if form.original_password and check_password_hash(form.original_password, field.data):
            raise ValidationError(message or default_message)
    
    return _v_password


def v_atleat_one(message=None):
    default_message = 'At least one option must be selected.'

    def _v_password(form, field):
        if len(field.data) == 0:
            raise ValidationError(message or default_message)
    return _v_password


# login and registration


class LoginForm(FlaskForm):
    username = StringField('Username',
                            id='username_login',
                            validators=[DataRequired()])
    password = PasswordField('Password',
                             id='pwd_login',
                             validators=[DataRequired()])


class CreateAccountForm(FlaskForm):
    username = StringField(label='Your Login',
                            id='username',
                            #name='Username',
                            render_kw={"placeholder": "Your login"},
                            validators=[DataRequired(), Length(min=4)])
    email = StringField(label='Your Email',
                            id='email',
                            #name='Email',
                            render_kw={"placeholder": "Your Email"},
                            validators=[DataRequired(), Email()])
    password = PasswordField(label='Your Password',
                             id='password',
                             #name='Password',
                             render_kw={"placeholder": "Your Password"},
                             validators=[DataRequired(), Length(min=9)])


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class EditAccountFormAdmin(FlaskForm):
    username = StringField(label='Username',
                            id='username',
                            render_kw={"placeholder": "Enter Your login"},
                            validators=[DataRequired(), Length(min=4), v_username()])
    firstname = StringField(label='Firstname',
                            id='firstname',
                            render_kw={"placeholder": "Enter Your First Name"},
                            validators=[Optional(strip_whitespace=False)])
    lastname = StringField(label='Lastname',
                            id='lastname',
                            render_kw={"placeholder": "Enter Your Last Name"},
                            validators=[Optional(strip_whitespace=False)])
    email = StringField(label='Email',
                            id='email',
                            render_kw={"placeholder": "name@company.com "},
                            validators=[DataRequired(), Email(), v_email()])
    password = PasswordField(label='New Password',
                            id='password',
                            validators = [v_password(), EqualTo('passwordconfirm', message='Passwords must match'), Length(min=9)])
    passwordconfirm = PasswordField(label='Repeat Password', 
                            id='passwordconfirm')
    
    roles = MultiCheckboxField(label='Roles', validators=[v_atleat_one()], coerce=int)

    def __init__(self, user, *args, **kwargs):
        super(EditAccountFormAdmin, self).__init__(*args, **kwargs)
        self.original_username = user.username
        self.original_email = user.email
        self.original_password = user.password_hash


class EditAccountFormNotAdmin(FlaskForm):
    username = StringField(label='Username',
                            id='username',
                            render_kw={"placeholder": "Enter Your login"},
                            validators=[DataRequired(), Length(min=4), v_username()])
    firstname = StringField(label='Firstname',
                            id='firstname',
                            render_kw={"placeholder": "Enter Your First Name"},
                            validators=[Optional(strip_whitespace=False)])
    lastname = StringField(label='Lastname',
                            id='lastname',
                            render_kw={"placeholder": "Enter Your Last Name"},
                            validators=[Optional(strip_whitespace=False)])
    email = StringField(label='Email',
                            id='email',
                            render_kw={"placeholder": "name@company.com "},
                            validators=[DataRequired(), Email(), v_email()])
    password = PasswordField(label='New Password',
                            id='password',
                            validators = [v_password(), EqualTo('passwordconfirm', message='Passwords must match'), Length(min=9)])
    passwordconfirm = PasswordField(label='Repeat Password', 
                            id='passwordconfirm')
    
    roles = MultiCheckboxField(label='Roles', coerce=int)

    def __init__(self, user, *args, **kwargs):
        super(EditAccountFormNotAdmin, self).__init__(*args, **kwargs)
        self.original_username = user.username
        self.original_email = user.email
        self.original_password = user.password_hash


class UserCreateForm(FlaskForm):
    username = StringField(label='Username',
                            id='username',
                            render_kw={"placeholder": "Enter User login"},
                            validators=[DataRequired(), Length(min=4), v_username()])
    firstname = StringField(label='Firstname',
                            id='firstname',
                            render_kw={"placeholder": "Enter First Name"},
                            validators=[Optional(strip_whitespace=False)])
    lastname = StringField(label='Lastname',
                            id='lastname',
                            render_kw={"placeholder": "Enter Last Name"},
                            validators=[Optional(strip_whitespace=False)])
    email = StringField(label='Email',
                            id='email',
                            render_kw={"placeholder": "name@company.com "},
                            validators=[DataRequired(), Email(), v_email()])
    password = PasswordField(label='New Password',
                            id='password',
                            validators = [DataRequired(), Length(min=9)])
    roles = MultiCheckboxField(label='Roles', validators=[v_atleat_one()], coerce=int)
    active = BooleanField(label='Active',
                            id='active')
    
    def __init__(self, *args, **kwargs):
        super(UserCreateForm, self).__init__(*args, **kwargs)
        self.original_username = ''
        self.original_email = ''
        self.original_password = ''


class UserEditForm(FlaskForm):
    username = StringField(label='Username',
                            id='username',
                            render_kw={"placeholder": "Enter User login"},
                            validators=[DataRequired(), Length(min=4), v_username()])
    firstname = StringField(label='Firstname',
                            id='firstname',
                            render_kw={"placeholder": "Enter First Name"},
                            validators=[Optional(strip_whitespace=False)])
    lastname = StringField(label='Lastname',
                            id='lastname',
                            render_kw={"placeholder": "Enter Last Name"},
                            validators=[Optional(strip_whitespace=False)])
    email = StringField(label='Email',
                            id='email',
                            render_kw={"placeholder": "name@company.com "},
                            validators=[DataRequired(), Email(), v_email()])
    password = PasswordField(label='New Password',
                            id='password',
                            validators = [v_password(), EqualTo('passwordconfirm', message='Passwords must match'), Length(min=9)])
    passwordconfirm = PasswordField(label='Repeat Password', 
                            id='passwordconfirm')
    roles = MultiCheckboxField(label='Roles', validators=[v_atleat_one()], coerce=int)
    active = BooleanField(label='Active',
                            id='active')

    def __init__(self, user, *args, **kwargs):
        super(UserEditForm, self).__init__(*args, **kwargs)
        self.original_username = user.username
        self.original_email = user.email
        self.original_password = user.password_hash


class RoleCreateForm(FlaskForm):
    name = StringField(label='Name',
                            id='name',
                            render_kw={"placeholder": "Enter Role Name"},
                            validators=[DataRequired(), Length(min=4), v_rolename()])
    
    def __init__(self, *args, **kwargs):
        super(RoleCreateForm, self).__init__(*args, **kwargs)
        self.original_name = ''


class RoleEditForm(FlaskForm):
    name = StringField(label='Name',
                            id='name',
                            render_kw={"placeholder": "Enter Role Name"},
                            validators=[DataRequired(), Length(min=4), v_rolename()])

    def __init__(self, role, *args, **kwargs):
        super(RoleEditForm, self).__init__(*args, **kwargs)
        self.original_name = role.name
