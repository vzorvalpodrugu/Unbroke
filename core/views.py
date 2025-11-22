# core/views.py
import threading

from django.shortcuts import render
from django.views.generic import TemplateView, CreateView, ListView, \
    DetailView, DeleteView
from django.urls import reverse_lazy
from django.core.paginator import Paginator
from .mistral_advice import generate_bank_advice
from .models import Statement
from .forms import StatementForm
from .mistral import process_llm
from django.core.cache import cache
import uuid
from django.http import JsonResponse
# from mistral_advice import
from django.contrib.auth.mixins import LoginRequiredMixin


class LandingView(TemplateView):
    template_name = "landing.html"

class UserProfileView(LoginRequiredMixin, ListView):
    model = Statement
    template_name = 'profile.html'
    context_object_name = 'statements'
    paginate_by = 5  # Показывать только 5 последних выписок

    def get_queryset(self):
        # Только выписки текущего пользователя, отсортированные по дате создания (новые сверху)
        return Statement.objects.filter(user=self.request.user).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Общее количество выписок (без пагинации)
        context['total_statements'] = Statement.objects.filter(user=self.request.user).count()
        return context

# def profile(request):
#     statements = Statement.objects.filter(user=request.user).order_by('-uploaded_at')[:5]
#     total_statements = Statement.objects.filter(user=request.user).count()
#     return render(request, 'profile.html', {
#         'statements': statements,
#         'total_statements': total_statements
#     })

class StatementCreateView(CreateView):
    model = Statement
    form_class = StatementForm
    template_name = "statement_form.html"
    success_url = reverse_lazy("statement_upload")

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)

        bank = form.cleaned_data["bank"]
        task_id = str(uuid.uuid4())

        # ⚡ сразу кладём "стартовый прогресс"
        cache.set(f"progress:{task_id}", {
            "current": 0,
            "total": 0,
            "logs": ["Запуск анализа..."],
            "done": False,
        }, timeout=3600)

        # ⚡ запускаем анализ в отдельном потоке
        def run_analysis(file, bank_name, task_id):
            try:
                process_llm(file, bank=bank_name, task_id=task_id)
            except Exception as e:
                cache.set(f"progress:{task_id}", {
                    "logs": [f"❌ Ошибка: {e}"],
                    "done": True
                }, timeout=3600)

        t = threading.Thread(target=run_analysis, args=(self.object.file, bank.bank_name, task_id))
        t.start()

        # ⚡ сразу возвращаем task_id
        return JsonResponse({"task_id": task_id})

class StatementDetailView(LoginRequiredMixin, DetailView):
    model = Statement
    template_name = 'statement_detail.html'
    context_object_name = 'statement'

    def get_queryset(self):
        # Пользователь может видеть только свои выписки
        return Statement.objects.filter(user=self.request.user)

class StatementDeleteView(LoginRequiredMixin, DeleteView):
    model = Statement
    template_name = 'statement_confirm_delete.html'
    success_url = reverse_lazy('profile')

    def get_queryset(self):
        # Пользователь может удалять только свои выписки
        return Statement.objects.filter(user=self.request.user)

# эндпоинт для фронта
def get_progress(request, task_id):
    progress = cache.get(f"progress:{task_id}", {})

    # Добавляем проверку на завершение и наличие рекомендаций
    if progress.get('done') and 'advice_result' in progress:
        return JsonResponse({
            **progress,
            'has_advice': True,
            'advice': progress['advice_result'].get('advice', ''),
            'top_bank': progress['advice_result'].get('top_bank', ''),
            'top_cashback': progress['advice_result'].get('top_cashback', 0)
        })
    return JsonResponse(progress)


def generate_advice(request, task_id):
    """Отдельный endpoint для генерации рекомендаций"""
    try:
        progress = cache.get(f"progress:{task_id}", {})
        categories = progress.get("final_categories", {})

        if not categories:
            return JsonResponse({"error": "Данные анализа не найдены"})

        # Генерируем рекомендации
        advice_result = generate_bank_advice(categories, task_id)

        # Обновляем прогресс с результатами
        progress["advice_result"] = advice_result
        cache.set(f"progress:{task_id}", progress, timeout=3600)

        return JsonResponse(advice_result)

    except Exception as e:
        return JsonResponse({"error": str(e)})