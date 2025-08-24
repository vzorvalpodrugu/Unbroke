# core/views.py
from django.views.generic import TemplateView, CreateView
from django.urls import reverse_lazy
from .models import Statement
from .forms import StatementForm
from .mistral import process_llm


class LandingView(TemplateView):
    template_name = "landing.html"


class StatementCreateView(CreateView):
    model = Statement
    form_class = StatementForm
    template_name = "statement_form.html"
    success_url = reverse_lazy("landing")

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)

        bank = form.cleaned_data["bank"]   # ✅ теперь это объект Bank
        print("✅ form_valid вызван, банк:", bank.bank_name)
        try:
            process_llm(self.object.file, bank=bank.bank_name)  # передаём название
        except Exception as e:
            print("❌ Ошибка при работе:", e)

        return response
