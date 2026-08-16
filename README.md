[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-compatible-blue.svg?style=for-the-badge&logo=home-assistant)](https://www.home-assistant.io/)
[![Blueprint](https://img.shields.io/badge/Type-Blueprint-15A9CE.svg?style=for-the-badge)](https://www.home-assistant.io/docs/automation/using_blueprints/)

# 🏠 Home Assistant Blueprints by BrainDeLook

Личная коллекция автоматизаций и скриптов для Home Assistant.

---

## 📺 Media / Телевидение и медиаплееры

| Файл | Описание | Установка |
| :--- | :--- | :---: |
| [**tv_content_action.yaml**](https://github.com/BrainDeLook/home-assistant-blueprints/blob/main/tv_content_action.yaml) | **[RU]** Выполняет выбранное действие, когда телевизор включён и текущий канал или передача совпадает с заданным названием. Поддерживает временной интервал, проверку состояния или атрибута сущности и защиту от повторов. | [![Import Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2FBrainDeLook%2Fhome-assistant-blueprints%2Fmain%2Ftv_content_action.yaml) |

---

## 🚀 Как установить

Нажмите кнопку **Import Blueprint** напротив нужного файла.

Для ручной установки скопируйте YAML-файл в каталог Home Assistant:

```text
/config/blueprints/automation/personal/tv_content_action.yaml
```

Затем перезагрузите автоматизации или Home Assistant.

## ⚠️ Приватный доступ

Репозиторий сейчас приватный. Кнопка быстрого импорта уже сформирована, но
Home Assistant не сможет скачать Raw URL без авторизации GitHub. Она заработает,
если репозиторий или отдельная копия YAML-файла станут публичными.
