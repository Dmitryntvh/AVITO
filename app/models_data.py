"""
Данные каталога моделей.

Этот модуль содержит простую структуру данных `MODELS`, которая
используется телеграм‑ботом для отображения каталога. Каждая модель
представлена кодом (ключ словаря) и словарём с полями:

```
{
    "name": str,            # название модели
    "short": str,           # краткое описание
    "prices": {
        "drawings": int,    # стоимость чертежей
        "kits": [
            {"material": str, "price": int},
            ...
        ],
    },
    "images": list | str,   # ссылки на изображения
    "drawings_url": str,    # ссылка на папку или файл чертежей
}
```

В дальнейшем эти данные могут быть перенесены в базу данных; текущий
формат удобен для разработки и демонстрации.
"""

MODELS = {
    "polar-6": {
        "name": "Банный чан Полярный 6",
        "short": "Каталог модели. Цены и комплектации.",
        "prices": {
            "drawings": 1500,
            "kits": [
                {"material": "Ст3", "price": 35000},
                {"material": "AISI 430 + печь Ст3 4 мм", "price": 65000},
            ],
        },
        "images": "https://assets.smolkirpich.ru/thumbnails/c4/c47f6062f5853540aedbb4af7e06533b.jpg",
        # ссылка на папку/файл чертежей
        "drawings_url": "https://cloud.mail.ru/public/BU46/cMydSMN2M",
    },
    "polar-8": {
        "name": "Банный чан Полярный 8",
        "short": "Каталог модели. Цены и комплектации.",
        "prices": {"drawings": 0, "kits": []},
        "images": [],
        "drawings_url": "",
    },
    "model-3": {
        "name": "Модель 3",
        "short": "",
        "prices": {"drawings": 0, "kits": []},
        "images": [],
        "drawings_url": "",
    },
    "model-4": {
        "name": "Модель 4",
        "short": "",
        "prices": {"drawings": 0, "kits": []},
        "images": [],
        "drawings_url": "",
    },
    "model-5": {
        "name": "Модель 5",
        "short": "",
        "prices": {"drawings": 0, "kits": []},
        "images": [],
        "drawings_url": "",
    },
}