# core/mistral.py
import base64
import json
import re
from typing import Dict, Any

from mistralai import Mistral
from pdf2image import convert_from_bytes
from django.conf import settings
from promts.ONLY_CATEGOREIS import PROMT


# === Константы и справочники ===

PROMPT = PROMT  # используем то, что ты передаёшь
CATEGORIES = [
    "Еда",
    "Одежда",
    "Транспорт",
    "Платежи",
    "Аптека",
    "Музыка",
    "Искусство",
    "Недвижимость",
    "АЗС",
    "Переводы",
    "Другое",
]


# === Вспомогательные функции ===

def get_client():
    api_key = settings.MISTRAL_API_KEY
    if not api_key:
        raise RuntimeError("Не найден MISTRAL_API_KEY в переменных окружения / настройках Django")
    return Mistral(api_key=api_key)


def encode_image(image):
    """Конвертирует PIL.Image в base64-строку JPEG (для Vision)."""
    from io import BytesIO
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=70)
    encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def extract_first_json(text: str) -> str:
    """
    Достаёт первый корректно сбалансированный JSON-объект из произвольной строки.
    Поддерживает варианты: обычный текст + {…}, либо блоки ```json … ```.
    Бросает ValueError, если извлечь не удалось.
    """
    if not text:
        raise ValueError("Пустой ответ модели")

    # 1) fenced code block ```json ... ```
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        candidate = fence_match.group(1)
        candidate = _json_minimal_cleanup(candidate)
        return candidate

    # 2) По первой сбалансированной паре фигурных скобок
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    candidate = text[start:i+1]
                    candidate = _json_minimal_cleanup(candidate)
                    return candidate

    raise ValueError("В ответе не найден корректный JSON-объект")


def _json_minimal_cleanup(s: str) -> str:
    """
    Минимальная подчистка на случай лишних запятых перед закрывающей скобкой.
    Не превращает не-JSON в JSON магическим образом — только безопасные правки.
    """
    # запятая перед } или ]
    s = re.sub(r",\s*([}\]])", r"\1", s)
    return s.strip()


def coerce_number(val: Any) -> float:
    """
    Приведение значений к числу:
    - 123,45 -> 123.45
    - " 1 234,50 " -> 1234.50
    - 1_234.50 -> 1234.50
    - Если не получается — 0.0
    """
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        s = val.strip()
        # убираем пробелы-разделители и подчёркивания
        s = s.replace("\xa0", "").replace(" ", "").replace("_", "")
        # заменяем запятую на точку
        s = s.replace(",", ".")
        # оставляем только цифры, точку и минус
        s = re.sub(r"[^0-9\.\-]", "", s)
        try:
            return float(s) if s not in ("", ".", "-", "-.", ".-") else 0.0
        except ValueError:
            return 0.0
    return 0.0


def canonize_category(name: str) -> str:
    """
    Приводит имя категории от модели к каноническому из списка CATEGORIES.
    Сначала точное совпадение, затем case-insensitive. Если не нашли — возвращаем исходное,
    но дальше мы такие ключи игнорируем, чтобы не раздувать итоговый JSON.
    """
    if not isinstance(name, str):
        return str(name)

    raw = name.strip()
    # точное совпадение
    for cat in CATEGORIES:
        if raw == cat:
            return cat
    # без учёта регистра
    for cat in CATEGORIES:
        if raw.lower() == cat.lower():
            return cat
    return raw


class CategoryAggregator:
    """Надёжный аккумулятор сумм по категориям из ответов Мистраля."""
    def __init__(self, categories):
        self._cats = list(categories)
        self._totals: Dict[str, float] = {c: 0.0 for c in self._cats}

    def add_page_totals(self, page_obj: Dict[str, Any]):
        if not isinstance(page_obj, dict):
            return
        for k, v in page_obj.items():
            canon = canonize_category(k)
            amount = coerce_number(v)
            if canon in self._totals:
                self._totals[canon] += amount
            else:
                # неизвестная категория — тихо игнорируем, но можно логировать:
                print(f"ℹ️ Пропущена неизвестная категория из ответа: {k} -> {canon} (значение: {v})")

    def result(self) -> Dict[str, float]:
        # округление до копеек
        return {c: round(self._totals[c], 2) for c in self._cats}

    def total_expense(self) -> float:
        return round(sum(self._totals.values()), 2)


# === Основной пайплайн ===

def process_llm(file_field, bank: str = None):
    """
    Обрабатывает PDF постранично с помощью Mistral Vision.
    Ожидается ОДИН JSON от модели на страницу — только СУММЫ РАСХОДОВ по категориям.
    В конце печатает общий JSON по всем категориям за документ + сумму расходов.
    """
    client = get_client()

    pdf_bytes = file_field.read()
    pages = convert_from_bytes(pdf_bytes)
    print(f"📄 PDF содержит {len(pages)} страниц")

    all_responses = []
    agg = CategoryAggregator(CATEGORIES)

    for idx, page in enumerate(pages, 1):
        base64_img = encode_image(page)

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT + (f"\nБанк: {bank}" if bank else "")},
                    {"type": "image_url", "image_url": base64_img},
                ]
            }
        ]

        try:
            resp = client.chat.complete(
                model="pixtral-large-latest",
                messages=messages
            )
            raw = resp.choices[0].message.content
            print(f"\n📄 Ответ страницы {idx}: {raw}")

            try:
                json_text = extract_first_json(raw)
                page_obj = json.loads(json_text)

                # аккумулируем итог по этой странице
                agg.add_page_totals(page_obj)

                all_responses.append({
                    "page": idx,
                    "categories": page_obj
                })
                print(f"✅ Страница {idx} обработана")

            except Exception as e:
                print(f"⚠️ Ошибка парсинга JSON на странице {idx}: {e}")
                all_responses.append({
                    "page": idx,
                    "raw": raw,
                    "parse_error": str(e)
                })

        except Exception as e:
            print(f"❌ Ошибка запроса к Mistral на странице {idx}: {e}")
            all_responses.append({
                "page": idx,
                "error": str(e)
            })

    # ===== Итог по документу =====
    final_categories = agg.result()
    final_expense = agg.total_expense()

    print("\n💸 Общая сумма расходов по всем категориям:")
    print(json.dumps({"расходы_всего": final_expense}, ensure_ascii=False, indent=2))

    print("\n📊 Итог по всему документу (суммы по категориям):")
    print(json.dumps(final_categories, ensure_ascii=False, indent=2))

    return {
        "страницы": all_responses,
        "итог": final_categories
    }
