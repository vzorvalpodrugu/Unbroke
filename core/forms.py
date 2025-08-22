from django import forms
from .models import Statement, Bank


class StatementForm(forms.ModelForm):
    class Meta:
        model = Statement
        fields = ["bank", "file"]
        widgets = {
            "bank": forms.Select(attrs={
                "class": "form-select mb-3"
            }),
            "file": forms.ClearableFileInput(attrs={
                "class": "form-control mb-3"
            }),
        }
