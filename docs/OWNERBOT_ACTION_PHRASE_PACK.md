# OWNERBOT_ACTION_PHRASE_PACK

Источник истины по реализации phrase pack: `app/agent_actions/phrase_pack.py`.

## FX reprice
- Примеры:
  - «обнови цены по курсу»
  - «пересчитай цены»
  - «репрайс»
  - «fx apply»
  - «проверь курс»
- Mapping: `sis_fx_reprice_auto`
- Извлекаемые параметры:
  - `refresh_snapshot=true`
  - `force=false`

## Price bump
- Примеры:
  - «подними цены на 5%»
  - «снизь цены на 3%»
  - «сделай +10 процентов»
- Mapping: `sis_prices_bump`
- Извлекаемые параметры:
  - `value=5`
  - `value=-3`
  - `value=10`

## Coupon
- Примеры:
  - «купон -10% на сутки»
  - «скидка 15% на 48 часов»
  - «создай купон 20 процентов»
- Mapping: `create_coupon`
- Извлекаемые параметры:
  - `percent_off=10`, `hours_valid=24`
  - `percent_off=15`, `hours_valid=48`
  - `percent_off=20` (duration wizard step)

## Notify team / order ping
- Примеры:
  - «пинг менеджеру по заказу 1234»
  - «напомни по заказу 123»
  - «сообщи команде проверь заказ OB-1003»
- Mapping: `notify_team`
- Извлекаемые параметры:
  - `order_id=1234`
  - `order_id=123`
  - `order_id=OB-1003`, `message="проверь заказ OB-1003"`

## Publish/archive products/looks
- Примеры:
  - «опубликуй товары 12,13»
  - «скрой товары 44»
  - «опубликуй луки 1,2»
  - «скрой луки 5»
- Mapping:
  - products: `sis_products_publish`
  - looks: `sis_looks_publish`
- Извлекаемые параметры:
  - `product_ids=["12","13"]`, `target_status="ACTIVE"`
  - `product_ids=["44"]`, `target_status="ARCHIVED"`
  - `look_ids=["1","2"]`, `target_active=true`
  - `look_ids=["5"]`, `target_active=false`

## Cancel/stop
- Примеры:
  - «отмена»
  - «cancel»
  - «стоп»
- Mapping: action wizard cancel (без вызова tool)

## Rule-pack contract
- `docs/Rule-pack.md` используется как продуктовая спецификация.
- Контрактные тесты в `tests/test_rule_pack_contract.py` проверяют покрытие ключевых 20 фраз и защищают от дрейфа между docs и SSOT-кодом.
