[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-compatible-blue.svg?style=for-the-badge&logo=home-assistant)](https://www.home-assistant.io/)
[![Blueprint](https://img.shields.io/badge/Type-Blueprint-15A9CE.svg?style=for-the-badge)](https://www.home-assistant.io/docs/automation/using_blueprints/)

# 🏠 Home Assistant Blueprints by BrainDeLook

Личная коллекция автоматизаций и скриптов для Home Assistant.

---

## 📺 Media / Телевидение и медиаплееры

| Файл | Описание | Установка |
| ---- | -------- | --------- |
| [**tv_content_action.yaml**](https://github.com/BrainDeLook/home-assistant-blueprints/blob/main/tv_content_action.yaml) | **[RU]** Отправляет команды, когда Apple TV/телевизор остаётся на заданном канале, а отдельная сущность показывает нужную передачу и/или наступил заданный интервал. Настраиваемая задержка защищает от срабатывания при перелистывании каналов. | [![Import Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2FBrainDeLook%2Fhome-assistant-blueprints%2Fmain%2Ftv_content_action.yaml) |

---

## 🔊 Voice / Яндекс Станция и Алиса

| Файл | Описание | Установка |
| ---- | -------- | --------- |
| [**script/alice_smart_speaker_parallel.yaml**](https://github.com/BrainDeLook/home-assistant-blueprints/blob/main/script/alice_smart_speaker_parallel.yaml) | **[RU]** Скрипт «Алиса: Умный рупор» для озвучивания уведомлений и выполнения команд на одной или нескольких колонках Яндекс Станции. Умные стратегии громкости с возвратом исходного уровня у каждой колонки, голоса, эффекты (шёпот, мегафон и др.) и большая база звуков. **Отличие от оригинала: запускается в режиме `parallel`, поэтому вызовы для разных колонок с разными текстами выполняются одновременно, а не по очереди.** | [![Import Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2FBrainDeLook%2Fhome-assistant-blueprints%2Fmain%2Fscript%2Falice_smart_speaker_parallel.yaml) |

**Требования:** интеграция [YandexStation](https://github.com/AlexxIT/YandexStation) (`media_player` колонок и `tts.yandex_station_say`).

**Как пользоваться:**

1. Импортируйте блюпринт кнопкой выше.
2. Перейдите в **Настройки → Автоматизации и сцены → Скрипты → Добавить скрипт → Использовать проект** и выберите «Алиса: Умный рупор (параллельный)».
3. Сохраните скрипт.
4. В автоматизации в блоке «Тогда» выберите **Выполнить действие** и найдите свой скрипт. Укажите колонку, текст, громкость, голос и эффект.

**Ограничение параллельного режима:** не вызывайте скрипт одновременно для одной и той же колонки. Запуски могут конфликтовать при установке и возврате громкости. Для разных колонок проблемы нет.

**Если нужна очередь:** используйте оригинальный блюпринт (режим `queued`).

**Благодарности:** основано на блюпринте [Eugen417/homeassistant-blueprints](https://github.com/Eugen417/homeassistant-blueprints/blob/main/script/ya_st_alice_simple.yaml) (v4.7). Единственное функциональное изменение: режим запуска `queued` заменён на `parallel`.

---

## 🚀 Как установить

Нажмите кнопку **Import Blueprint** напротив нужного файла.

Для ручной установки скопируйте YAML-файл в каталог Home Assistant:

| Тип | Путь |
| --- | ---- |
| Автоматизация (`tv_content_action.yaml`) | `/config/blueprints/automation/personal/tv_content_action.yaml` |
| Скрипт (`alice_smart_speaker_parallel.yaml`) | `/config/blueprints/script/personal/alice_smart_speaker_parallel.yaml` |

Затем перезагрузите автоматизации/скрипты или Home Assistant.
