# core/mistral.py
import base64
import json
import re
from typing import Dict, Any
from django.core.cache import cache
from mistralai import Mistral
from pdf2image import convert_from_bytes
from django.conf import settings
from promts.ONLY_CATEGOREIS import PROMT
from core.mistral_advice import generate_bank_advice

PROMPT = PROMT
CATEGORIES = [
    "Еда", "Одежда", "Транспорт", "Платежи", "Аптека",
    "Музыка", "Искусство", "Недвижимость", "АЗС", "Переводы", "Другое",
]

def get_client():
    api_key = settings.MISTRAL_API_KEY
    if not api_key:
        raise RuntimeError("Не найден MISTRAL_API_KEY")
    return Mistral(api_key=api_key)

def encode_image(image):
    from io import BytesIO
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=70)
    encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"

def extract_first_json(text: str) -> str:
    if not text:
        raise ValueError("Пустой ответ модели")
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        candidate = fence_match.group(1)
        return _json_minimal_cleanup(candidate)
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0: start = i
            depth += 1
        elif ch == '}':
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    candidate = text[start:i+1]
                    return _json_minimal_cleanup(candidate)
    raise ValueError("В ответе не найден корректный JSON-объект")

def _json_minimal_cleanup(s: str) -> str:
    s = re.sub(r",\s*([}\]])", r"\1", s)
    return s.strip()

def coerce_number(val: Any) -> float:
    if isinstance(val, (int, float)): return float(val)
    if isinstance(val, str):
        s = val.strip().replace("\xa0", "").replace(" ", "").replace("_", "").replace(",", ".")
        s = re.sub(r"[^0-9\.\-]", "", s)
        try: return float(s) if s not in ("", ".", "-", "-.", ".-") else 0.0
        except ValueError: return 0.0
    return 0.0

def canonize_category(name: str) -> str:
    if not isinstance(name, str): return str(name)
    raw = name.strip()
    for cat in CATEGORIES:
        if raw == cat: return cat
    for cat in CATEGORIES:
        if raw.lower() == cat.lower(): return cat
    return raw

class CategoryAggregator:
    def __init__(self, categories):
        self._cats = list(categories)
        self._totals: Dict[str, float] = {c: 0.0 for c in self._cats}

    def add_page_totals(self, page_obj: Dict[str, Any]):
        if not isinstance(page_obj, dict): return
        for k, v in page_obj.items():
            canon = canonize_category(k)
            amount = coerce_number(v)
            if canon in self._totals:
                self._totals[canon] += amount
            else:
                print(f"ℹ️ Пропущена неизвестная категория: {k} -> {canon} (значение: {v})")

    def result(self) -> Dict[str, float]:
        return {c: round(self._totals[c], 2) for c in self._cats}

    def total_expense(self) -> float:
        return round(sum(self._totals.values()), 2)


# === Основной пайплайн с прогрессом постранично ===

def process_llm(file_field, bank: str = None, task_id: str = "default"):
    client = get_client()
    pdf_bytes = file_field.read()
    pages = convert_from_bytes(pdf_bytes)
    total_pages = len(pages)
    print(f"📄 PDF содержит {total_pages} страниц")

    all_responses = []
    agg = CategoryAggregator(CATEGORIES)
    done_pages = []

    # Инициализируем прогресс
    cache.set(f"progress:{task_id}", {
        "current": 0,
        "total": total_pages,
        "pages_done": [],
        "logs": ["Запуск анализа..."],
        "done": False
    }, timeout=3600)

    for idx, page in enumerate(pages, 1):
        # Добавляем лог текущей страницы
        progress = cache.get(f"progress:{task_id}")
        progress["logs"].append(f"Анализ страницы {idx}...")
        progress["current"] = idx
        cache.set(f"progress:{task_id}", progress, timeout=3600)

        base64_img = encode_image(page)
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT + (f"\nБанк: {bank}" if bank else "")},
                {"type": "image_url", "image_url": base64_img},
            ]
        }]
        # Models
        # Pixtral 12B (pixtral-12b-latest)
        # Pixtral Large (pixtral-large-latest) - пока лучшая
        # Mistral Medium 2505(mistral-medium-latest)
        # Mistral Small 2503(mistral-small-latest)
        try:
            resp = client.chat.complete(model="mistral-small-latest",
                                        messages=messages)
            raw = resp.choices[0].message.content
            print(f"📄 Ответ страницы {idx}: {raw}")

            try:
                json_text = extract_first_json(raw)
                page_obj = json.loads(json_text)
                agg.add_page_totals(page_obj)
                all_responses.append({"page": idx, "categories": page_obj})

                progress = cache.get(f"progress:{task_id}")
                progress["logs"].append(f"✅ Страница {idx} обработана")

            except Exception as e:
                all_responses.append(
                    {"page": idx, "raw": raw, "parse_error": str(e)})
                progress = cache.get(f"progress:{task_id}")
                progress["logs"].append(f"⚠️ Ошибка парсинга страницы {idx}")

        except Exception as e:
            all_responses.append({"page": idx, "error": str(e)})
            progress = cache.get(f"progress:{task_id}")
            progress["logs"].append(f"❌ Ошибка анализа страницы {idx}")

        # Добавляем страницу в любом случае
        done_pages.append(idx)
        progress["pages_done"] = done_pages.copy()
        cache.set(f"progress:{task_id}", progress, timeout=3600)

    # Финальный прогресс
    final_categories = agg.result()

    # Генерация рекомендации
    progress = cache.get(f"progress:{task_id}")
    progress["logs"].append("🎯 Анализируем лучший банк для ваших трат...")
    cache.set(f"progress:{task_id}", progress, timeout=3600)

    # Запускаем генерацию рекомендаций
    advice_result = generate_bank_advice(final_categories, task_id)

    progress = cache.get(f"progress:{task_id}")
    progress["logs"].append("Формируем финальный JSON...")
    progress["logs"].append("✅ Анализ завершен!")
    progress["done"] = True
    progress["pages_done"] = done_pages
    progress["final_categories"] = final_categories
    progress["advice_result"] = advice_result

    cache.set(f"progress:{task_id}", progress, timeout=3600)
    print(final_categories)
    return {
        "страницы": all_responses,
        "итог": final_categories,
        "рекомендации": advice_result
    }
