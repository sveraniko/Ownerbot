Rule-pack 20 фраз (Owner Actions + Ops)
FX / Цены

«Проверь курс» / «Какой сейчас курс?»
→ REPORT → sis_fx_status
→ без params
→ ответ: rate, last_apply, would_apply (если есть)

«Проверь курс и если надо обнови цены»
→ PLAN (ACT-03a) → step1 sis_fx_reprice_auto(dry_run)
→ если would_apply=True → confirm → commit
→ если noop → сообщить “не нужно”

«Обнови цены по курсу» / «Пересчитай цены по курсу» / «Сделай репрайс»
→ ACTION → sis_fx_reprice_auto(dry_run)
→ confirm если would_apply=True

«Принудительно обнови цены по курсу» / «форс репрайс»
→ ACTION → sis_fx_reprice_auto(dry_run, force=true)
→ confirm всегда

«Откатить последнее обновление цен» / «Rollback цен»
→ ACTION → sis_fx_rollback_last(dry_run)
→ confirm всегда

«Подними цены на 5%» / «Сделай +10 процентов»
→ ACTION → prices_bump(dry_run, mode="delta_percent", value=+5)
→ confirm если would_apply=True

«Снизь цены на 3%» / «Сделай -7 процентов»
→ ACTION → prices_bump(dry_run, mode="delta_percent", value=-3)
→ confirm если would_apply=True

Купоны / Скидки

«Сделай купон -10% на сутки»
→ PLAN → step1 create_coupon(dry_run, percent_off=10, hours_valid=24)
→ confirm → commit → (optional step2 notify_team)

«Сделай скидку 15% на 48 часов»
→ PLAN → create_coupon(dry_run, percent_off=15, hours_valid=48)

«Сделай купон -20% на 7 дней»
→ PLAN → create_coupon(dry_run, percent_off=20, hours_valid=168) (7*24)
→ confirm

«Выключи купон CODE» / «Отключи купон CODE»
→ ACTION → coupon_disable(dry_run, code="CODE") (если tool есть; иначе: UNKNOWN + “нет инструмента, нужен PR”)
→ confirm

«Поставь скидку 10% на товары 12,13,14»
→ ACTION → discounts_set(dry_run, product_ids=[12,13,14], percent=10) (или ваш реальный tool)
→ confirm

«Убери скидки с товаров 12,13» / «Очисти скидки по ID»
→ ACTION → discounts_clear(dry_run, product_ids=[...])
→ confirm

Каталог (товары/луки)

«Опубликуй товары 12,13» / «Publish товары 12 13»
→ ACTION → products_publish_ids(dry_run, ids=[12,13])
→ confirm

«Скрой товары 44,45» / «Архивируй товары 44 45»
→ ACTION → products_archive_ids(dry_run, ids=[44,45])
→ confirm

«Опубликуй луки 1,2» / «Publish looks 1 2»
→ ACTION → looks_publish_ids(dry_run, ids=[1,2])
→ confirm

«Скрой луки 7,8» / «Архивируй луки 7 8»
→ ACTION → looks_archive_ids(dry_run, ids=[7,8])
→ confirm

Ops / Команда / Срочное

«Что горит?» / «Покажи проблемы» / «Дай опс отчёт»
→ REPORT → biz_dashboard_ops(pdf) (или focus burn panel; зависит от вашей реализации)
→ без confirm

«Пингни команду: <текст>» / «Сообщи команде: <текст>»
→ ACTION (non-destructive, но лучше confirm по умолчанию) → notify_team(dry_run, message=...)
→ confirm (можно сделать auto-commit только если “подтверди” не требуется, но лучше одинаково)

«Пингни менеджера по заказу 1234» / «Напомни по заказу OB-1003»
→ PLAN → step1 orders_find_by_id/report (optional) или сразу notify
→ step1 (ACT): notify_team(dry_run, order_id=1234, message=template)
→ confirm → commit

Нормализация параметров (общие правила парсинга)

проценты: (\d{1,2})(\s*%| процентов| процента) → percent_off=int, clamp 1..95

время:

на сутки → 24h

на (\d+) час → hours

на (\d+) дн → hours = days*24

на неделю → 168h

IDs: товары 1,2,3 / луки 4 5 / id 7,8 → list[int]

order_id: заказ (OB-)?\d+ → сохранять строкой/числом как у вас принято