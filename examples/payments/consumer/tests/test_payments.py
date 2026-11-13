def check_payment_endpoint(test_client):
    response = test_client.post("/payments", json={"amount": 1250})
    assert response.status_code == 201
