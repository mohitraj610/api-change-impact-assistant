# API change impact report

Mode: ` evidence only `
Contracts: ` before.yaml ` to ` after.yaml `


## ` GET /legacy-payments `

- Contract change: ` Operation removed `
- Assessment: **No direct usage found**
- Next check: ` Check shared clients, generated SDKs, and dynamically constructed URLs for usage. `

### Open questions

- ` Does a shared client, generated SDK, or dynamic URL call this operation? `
- ` Which tests exercise this operation through indirect calls? `

### Docs evidence

- **doc-1** ` docs/migration.md:1 `: `` # Payments API v2 migration `POST /payments` requires `currency` as a three-letter currency code. The v2 `201` response no longer contains `receipt_url`. Use the payment ID to look up receipts separately. ## Other endpoints The legacy payments listing (`GET /legacy-payments`) was removed in v2. ``
- **doc-2** ` docs/operations.md:1 `: ` # Payments dashboard The payments dashboard shows daily totals and links to account settings. The dashboard refreshes every hour. It is independent of the client SDK version. `

## ` POST /payments `

- Contract change: ` JSON request field 'currency' became required `
- Assessment: **Potential impact**
- Next check: ` Trace request construction and test requests with and without 'currency'. `

### Open questions

- ` Does the final request always supply a valid 'currency'? `

### Code evidence

- **code-1** ` payments.py:2 `: ` response = client.post("/payments", json={"amount": amount}) return response.json()["receipt_url"] `

### Tests evidence

- **test-1** ` tests/test_payments.py:2 `: ` response = test_client.post("/payments", json={"amount": 1250}) assert response.status_code == 201 `

### Docs evidence

- **doc-1** ` docs/migration.md:1 `: `` # Payments API v2 migration `POST /payments` requires `currency` as a three-letter currency code. The v2 `201` response no longer contains `receipt_url`. Use the payment ID to look up receipts separately. ## Other endpoints The legacy payments listing (`GET /legacy-payments`) was removed in v2. ``
- **doc-2** ` docs/operations.md:1 `: ` # Payments dashboard The payments dashboard shows daily totals and links to account settings. The dashboard refreshes every hour. It is independent of the client SDK version. `

## ` POST /payments `

- Contract change: ` JSON response field 'receipt_url' removed from status 201 `
- Assessment: **Potential impact**
- Next check: ` Trace readers of 'receipt_url' and test against a response without it. `

### Open questions

- ` Which runtime paths still read 'receipt_url' from status 201? `

### Code evidence

- **code-1** ` payments.py:2 `: ` response = client.post("/payments", json={"amount": amount}) return response.json()["receipt_url"] `

### Tests evidence

- **test-1** ` tests/test_payments.py:2 `: ` response = test_client.post("/payments", json={"amount": 1250}) assert response.status_code == 201 `

### Docs evidence

- **doc-1** ` docs/migration.md:1 `: `` # Payments API v2 migration `POST /payments` requires `currency` as a three-letter currency code. The v2 `201` response no longer contains `receipt_url`. Use the payment ID to look up receipts separately. ## Other endpoints The legacy payments listing (`GET /legacy-payments`) was removed in v2. ``
- **doc-2** ` docs/operations.md:1 `: ` # Payments dashboard The payments dashboard shows daily totals and links to account settings. The dashboard refreshes every hour. It is independent of the client SDK version. `
