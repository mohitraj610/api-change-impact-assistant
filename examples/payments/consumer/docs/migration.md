# Payments API v2 migration

`POST /payments` requires `currency` as a three-letter currency code.
The v2 `201` response no longer contains `receipt_url`. Use the payment ID to look up receipts separately.

## Other endpoints

The legacy payments listing (`GET /legacy-payments`) was removed in v2.
