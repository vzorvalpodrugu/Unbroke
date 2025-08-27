# core/views.py
import threading
from django.views.generic import TemplateView, CreateView
from django.urls import reverse_lazy

from .mistral_advice import generate_bank_advice
from .models import Statement
from .forms import StatementForm
from .mistral import process_llm
from django.core.cache import cache
import uuid
from django.http import JsonResponse
# from mistral_advice import



class LandingView(TemplateView):
    template_name = "landing.html"


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