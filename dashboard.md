# Дашборд проблем

Нужен плагин **Dataview** (Settings → Community plugins).

## Открытые

```dataview
TABLE severity AS "Серьёзность", plugin_version AS "Версия", os AS "ОС", reporter AS "Автор", created AS "Создана"
FROM "issues"
WHERE status != "closed" AND id
SORT created DESC
```

## Блокирующие

```dataview
LIST title
FROM "issues"
WHERE status != "closed" AND severity = "Блокирует работу"
```

## Закрытые за последнее время

```dataview
TABLE reporter AS "Автор", updated AS "Закрыта"
FROM "issues"
WHERE status = "closed"
SORT updated DESC
LIMIT 20
```

## По версиям плагина

```dataview
TABLE length(rows) AS "Проблем"
FROM "issues"
WHERE id
GROUP BY plugin_version
SORT length(rows) DESC
```
