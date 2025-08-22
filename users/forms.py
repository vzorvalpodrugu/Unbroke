from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Email")

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            css_class = "form-control glass-input"
            if field_name in self.errors:  # если у поля есть ошибка
                css_class += " is-invalid"
            field.widget.attrs.update({
                "class": css_class,
                "placeholder": field.label,
            })
        for field in self.fields.values():
            field.help_text = None


class CustomAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            css_class = "form-control glass-input"
            if field_name in self.errors:
                css_class += " is-invalid"
            field.widget.attrs.update({
                "class": css_class,
                "placeholder": field.label,
            })
        for field in self.fields.values():
            field.help_text = None
