def create_payment(client, amount):
    response = client.post("/payments", json={"amount": amount})
    return response.json()["receipt_url"]
