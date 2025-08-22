from django.shortcuts import render
from django.views.generic import TemplateView, CreateView
from django.urls import reverse_lazy
from .models import Statement
from .forms import StatementForm

class LandingView(TemplateView):
    template_name = "landing.html"

class StatementCreateView(CreateView):
    model = Statement
    form_class = StatementForm
    template_name = "statement_form.html"
    success_url = reverse_lazy("landing")  # временно можно на главную

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

