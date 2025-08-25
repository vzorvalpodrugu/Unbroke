# core/mistral.py
import os
import base64
import json
from mistralai import Mistral
from pdf2image import convert_from_bytes
from django.conf import settings
from promts.ONLY_CATEGOREIS import PROMT

promt = PROMT
CATEGORY_RULES = {
    "Еда": ["PEREKRESTOK", "SUPERMARKET", "MARKET", "BRISTOL", "BISTRO", "PIZZA", "SUSHI", "WOK", "ПЯТЕРОЧКА","PYATEROCHKA","Кулинария", "coffee", "Кофе", "кафэ", "Магнит", "Fixprice", "Пиццерия", "Magnit", "SIDR", "PIVO", "Сидр", "Пиво"],
    "Одежда": ["ZARA", "H&M", "UNIQLO", "MANGO", "BERSHKA", "PULL&BEAR"],
    "Транспорт": ["МЕТРО", "TAXI", "UBER", "ЯНДЕКС GO", "SAMOKAT"],
    "Платежи": ["СБП", "КОММУНАЛ", "ПЕРЕВОД"],
    "Аптека": ["АПТЕКА", "PHARMACY", "Doctor"],
    "Музыка": ["MUSIC", "SPOTIFY", "YANDEX MUSIC", "APPLE MUSIC", "CONCERT"],
    "Искусство": ["ВЫСТАВКА", "MUSEUM", "ART"],
    "Недвижимость": ["ОТЕЛЬ", "HOSTEL", "TUR", "TRAVEL", "BOOKING", "AIRBNB"],
    "АЗС": ["АЗС", "FUEL", "БЕНЗИН", "GAS", "SHELL", "ЛУКОЙЛ", "РОСНЕФТЬ"],
    "Переводы":[],
    "Другое": []
}


def get_client():
    api_key = settings.MISTRAL_API_KEY
    if not api_key:
        raise RuntimeError("Не найден MISTRAL_API_KEY в переменных окружения")
    return Mistral(api_key=api_key)


def encode_image(image):
    """Конвертирует PIL Image в base64 строку JPEG."""
    from io import BytesIO
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=70)
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def categorize(description: str) -> str:
    """Присваивает категорию транзакции по ключевым словам."""
    desc_up = description.upper()
    for category, keywords in CATEGORY_RULES.items():
        if any(kw in desc_up for kw in keywords):
            return category
    return "Другое"


def process_llm(file_field, bank: str = None):
    """
    Отправляет PDF в LLM Vision постранично.
    """
    client = get_client()

    pdf_bytes = file_field.read()
    pages = convert_from_bytes(pdf_bytes)
    print(f"📄 PDF содержит {len(pages)} страниц")

    all_responses = []
    total_income = 0
    total_expense = 0
    category_totals = {cat: 0 for cat in CATEGORY_RULES.keys()}

    for idx, page in enumerate(pages, 1):
        base64_img = encode_image(page)

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": promt + (f"\nБанк: {bank}" if bank else "")},
                    {"type": "image_url", "image_url": base64_img},
                ]
            }
        ]

        try:
            response = client.chat.complete(
                model="pixtral-large-latest",
                messages=messages
            )
            raw_content = response.choices[0].message.content
            print(f"\n📄 Ответ страницы {idx}: {raw_content}")

            try:
                parsed = json.loads(raw_content)
                income = parsed.get("доходы", 0)
                expense = parsed.get("расходы", 0)

                total_income += income
                total_expense += expense

                # категоризация транзакций
                for tx in parsed.get("транзакции", []):
                    desc = tx.get("описание", "")
                    amount = tx.get("сумма", 0)
                    cat = categorize(desc)
                    category_totals[cat] += amount

                print(f"➡️ Итог по странице {idx}: доходы={income}, расходы={expense}")
            except Exception as e:
                print(f"⚠️ Не удалось распарсить JSON на странице {idx}: {e}")
                parsed = {"raw": raw_content}

            all_responses.append(parsed)
            print(f"✅ Страница {idx} обработана")
        except Exception as e:
            print(f"❌ Ошибка при обработке страницы {idx}: {e}")
            all_responses.append({"error": str(e)})

    # Итоговый отчёт
    print("\n📊 Итог по всему документу:")
    print(f"💰 Общие доходы: {total_income}")
    print(f"💸 Общие расходы: {total_expense}")

    print("\n📂 Итог по категориям:")
    for cat, total in category_totals.items():
        if total != 0:
            print(f"   {cat}: {total}")

    return {
        "страницы": all_responses,
        "итог": {
            "доходы": total_income,
            "расходы": total_expense,
            "категории": category_totals
        }
    }
