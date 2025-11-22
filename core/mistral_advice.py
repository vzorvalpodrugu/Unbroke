import os
import json
import time
from mistralai import Mistral
from django.conf import settings
from django.core.cache import cache
from .models import Bank


class MistralBankAdvisor:
    def __init__(self):
        self.api_key = settings.MISTRAL_API_KEY
        if not self.api_key:
            raise ValueError(
                "MISTRAL_API_KEY not found in environment variables")

        self.client = Mistral(api_key=self.api_key)
        self.model = "mistral-large-latest"
        self.max_retries = 10  # Максимальное количество попыток
        self.retry_delay = 15  # Задержка между попытками в секундах

    def get_all_banks_data(self):
        """Получает данные всех банков из БД"""
        banks = Bank.objects.all()
        banks_data = []

        for bank in banks:
            banks_data.append({
                'bank_name': bank.bank_name,
                'food_cashback': bank.food_cashback,
                'transport_cashback': bank.transport_cashback,
                'clothes_cashback': bank.clothes_cashback,
                'transaction_cashback': bank.transaction_cashback,
                'pharmacy_cashback': bank.pharmacy_cashback,
                'music_cashback': bank.music_cashback,
                'art_cashback': bank.art_cashback,
                'hotel_cashback': bank.hotel_cashback,
                'gas_station_cashback': bank.gas_station_cashback,
            })

        return banks_data

    def calculate_bank_profits(self, banks_data, categories_spending):
        """
        Рассчитывает потенциальный кешбэк для каждого банка
        """
        bank_profits = {}

        # Маппинг категорий (из вашего mistral.py в поля модели Bank)
        category_mapping = {
            "Еда": "food_cashback",
            "Транспорт": "transport_cashback",
            "Одежда": "clothes_cashback",
            "Платежи": "transaction_cashback",
            "Аптека": "pharmacy_cashback",
            "Музыка": "music_cashback",
            "Искусство": "art_cashback",
            "Недвижимость": "hotel_cashback",
            "АЗС": "gas_station_cashback",
            "Переводы": "transaction_cashback",
            "Другое": "transaction_cashback",
        }

        for bank in banks_data:
            bank_name = bank['bank_name']
            total_cashback = 0.0
            details = {}

            # Суммируем кешбэк по всем категориям
            for category, amount in categories_spending.items():
                db_field = category_mapping.get(category,
                                                "transaction_cashback")
                cashback_percent = bank.get(db_field, 0.0)
                cashback_amount = (amount * cashback_percent) / 100
                total_cashback += cashback_amount
                details[category] = round(cashback_amount, 2)

            bank_profits[bank_name] = {
                'total_cashback': round(total_cashback, 2),
                'details': details
            }

        return bank_profits

    def generate_advice_with_retry(self, categories_spending, task_id):
        """
        Генерирует рекомендации с повторными попытками при ошибке 429
        """
        for attempt in range(self.max_retries):
            try:
                print(
                    f"🔍 Попытка {attempt + 1}/{self.max_retries} генерации рекомендаций...")
                print("📊 Категории:", categories_spending)

                # Получаем данные всех банков
                banks_data = self.get_all_banks_data()
                print("🏦 Банки:", len(banks_data))

                # Рассчитываем прибыль для каждого банка
                bank_profits = self.calculate_bank_profits(banks_data,
                                                           categories_spending)

                # Сортируем банки по убыванию кешбэка
                sorted_banks = sorted(bank_profits.items(),
                                      key=lambda x: x[1]['total_cashback'],
                                      reverse=True)

                # Формируем промт для Mistral
                prompt = self._build_prompt(banks_data, categories_spending,
                                            bank_profits, sorted_banks)

                # Обновляем прогресс - начинаем генерацию совета
                progress = cache.get(f"progress:{task_id}", {})
                if attempt == 0:
                    progress["logs"] = progress.get("logs", []) + [
                        "🤖 Генерируем персонализированные рекомендации..."]
                else:
                    progress["logs"] = progress.get("logs", []) + [
                        f"🔄 Повторная попытка {attempt + 1}..."]
                cache.set(f"progress:{task_id}", progress, timeout=3600)

                # Отправляем запрос к Mistral
                print("📨 Отправляем запрос к Mistral AI...")
                chat_response = self.client.chat.complete(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "Ты финансовый консультант-эксперт по банковским продуктам. Ты даешь четкие, обоснованные рекомендации на основе математических расчетов. Отвечай на русском языке структурированно, с цифрами и выводами."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.3
                )

                advice_text = chat_response.choices[0].message.content
                print("✅ Ответ от Mistral получен")

                # Сохраняем результаты
                result = {
                    "advice": advice_text,
                    "calculations": bank_profits,
                    "top_bank": sorted_banks[0][0] if sorted_banks else None,
                    "top_cashback": sorted_banks[0][1][
                        'total_cashback'] if sorted_banks else 0
                }

                # Финальное обновление прогресса
                progress = cache.get(f"progress:{task_id}", {})
                progress["logs"] = progress.get("logs", []) + [
                    "✅ Рекомендации готовы!"]
                progress["advice_result"] = result
                cache.set(f"progress:{task_id}", progress, timeout=3600)

                return result

            except Exception as e:
                error_str = str(e)
                print(
                    f"❌ Ошибка при генерации рекомендаций (попытка {attempt + 1}):",
                    error_str)

                # Проверяем, это ли ошибка 429 с превышением capacity
                if '"message":"Service tier capacity exceeded for this model."' in error_str or 'service_tier_capacity_exceeded' in error_str:
                    if attempt < self.max_retries - 1:
                        print(
                            f"⏳ Превышена квота модели. Ждем {self.retry_delay} секунд перед повторной попыткой...")

                        # Обновляем прогресс
                        progress = cache.get(f"progress:{task_id}", {})
                        progress["logs"] = progress.get("logs", []) + [
                            f"⏳ Превышена квота модели. Повторная попытка через {self.retry_delay} сек..."]
                        cache.set(f"progress:{task_id}", progress,
                                  timeout=3600)

                        time.sleep(self.retry_delay)
                        continue
                    else:
                        error_msg = f"Превышена квота модели после {self.max_retries} попыток"
                else:
                    error_msg = f"Ошибка при генерации рекомендаций: {error_str}"

                progress = cache.get(f"progress:{task_id}", {})
                progress["logs"] = progress.get("logs", []) + [
                    f"❌ {error_msg}"]
                cache.set(f"progress:{task_id}", progress, timeout=3600)
                return {"error": error_msg}

        return {"error": "Неизвестная ошибка после всех попыток"}

    def _build_prompt(self, banks_data, categories_spending, bank_profits,
                      sorted_banks):
        """
        Строит детальный промт для Mistral
        """
        # Форматируем информацию о тратах
        spending_text = "\n".join(
            [f"- {category}: {amount} руб." for category, amount in
             categories_spending.items()])

        # Форматируем информацию о банках и расчетах
        banks_text = ""
        for bank_name, profit_data in sorted_banks:
            banks_text += f"\n\n**{bank_name}**:"
            banks_text += f"\nОбщий кешбэк: {profit_data['total_cashback']} руб."
            for category, cashback in profit_data['details'].items():
                if cashback > 0:
                    banks_text += f"\n- {category}: {cashback} руб."

        prompt = f"""Проанализируй мои траты за период и рассчитай, в каком банке я получу максимальный кешбэк.

Мои траты по категориям:
{spending_text}


Информация о кешбэках банков:
{banks_text}

Используй следующий вид ответа как строгий пример:
Sberbank даёт максимальный кешбэк (310.52 ₽) — на 118% больше, чем у ближайшего конкурента (AlphaBank). Приоритет: переводы (6.6% кешбэка).

Без лишних деталей!!! СТРОГО КАК НА ПРИМЕРЕ!!!
Отвечай четко и по делу. Ограничься 200 символами. Используй маркдаун для форматирования.
"""
        # Проанализируй и дай рекомендацию:
        # 1. Какой банк будет наиболее выгодным исходя из моих трат?
        # 2. На сколько рублей больше я получу в самом выгодном банке по сравнению с другими?
        # 3. Дайте разбивку по категориям: где каждый банк силен и слаб
        # 4. Учитывай не только общую сумму, но и распределение кешбэка по категориям
        # 5.
        # Дайте
        # конкретную
        # рекомендацию
        # с
        # цифрами

        return prompt


# Функция для использования в основном пайплайне
def generate_bank_advice(categories_spending, task_id):
    """
    Основная функция для генерации рекомендаций
    """
    try:
        advisor = MistralBankAdvisor()
        result = advisor.generate_advice_with_retry(categories_spending,
                                                    task_id)
        print("Результат рекомендаций:", result)
        return result
    except Exception as e:
        print("Ошибка в generate_bank_advice:", str(e))
        return {"error": str(e)}