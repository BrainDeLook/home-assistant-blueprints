# Home Assistant Blueprints

Личная коллекция Blueprints для Home Assistant.

## Автоматизации

### Действие при просмотре канала или программы

Файл: [`tv_content_action.yaml`](tv_content_action.yaml)

Blueprint выполняет выбранное действие, когда телевизор включён и текущий
канал или передача совпадает с заданным названием. Поддерживаются временной
интервал, сравнение по состоянию или атрибуту сущности и защита от повторов.

### Ручная установка

Скопируйте YAML-файл в каталог Home Assistant:

```text
/config/blueprints/automation/personal/tv_content_action.yaml
```

Затем перезагрузите автоматизации или Home Assistant.

> Репозиторий приватный, поэтому Home Assistant не сможет импортировать Raw URL
> без GitHub-аутентификации. Для кнопки быстрого импорта Blueprint должен быть
> доступен Home Assistant по публичному URL.
