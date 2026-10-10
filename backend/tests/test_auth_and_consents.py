from backend.app.core.security import decode_access_token


def test_candidate_registration_and_token_claims(client):
    payload = {
        "email": "champion.coder@fsp.ru",
        "password": "secret_password_2026",
        "role": "CANDIDATE",
        "first_name": "Алексей",
        "last_name": "Смирнов",
        "fsp_id": "FSP-RUS-0042",
        "consent_personal_data": True,
        "consent_profile_distribution": True,
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["role"] == "CANDIDATE"
    assert data["fsp_id"] == "FSP-RUS-0042"
    assert data["email"] == "champion.coder@fsp.ru"
    assert data["email_verified"] is False

    # Verify JWT claims
    claims = decode_access_token(data["access_token"])
    assert claims is not None
    assert claims["email"] == "champion.coder@fsp.ru"
    assert claims["role"] == "CANDIDATE"
    assert claims["fsp_id"] == "FSP-RUS-0042"
    assert claims["sub"] == data["user_id"]


def test_login_and_auth_me(client):
    # Try invalid password
    bad_login = client.post("/api/v1/auth/login", json={
        "email": "champion.coder@fsp.ru",
        "password": "wrong_password",
    })
    assert bad_login.status_code == 401

    # Correct login
    login_res = client.post("/api/v1/auth/login", json={
        "email": "champion.coder@fsp.ru",
        "password": "secret_password_2026",
    })
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    # Call /auth/me
    headers = {"Authorization": f"Bearer {token}"}
    me_res = client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "champion.coder@fsp.ru"


def test_email_verification_simulation(client):
    login_res = client.post("/api/v1/auth/login", json={
        "email": "champion.coder@fsp.ru",
        "password": "secret_password_2026",
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    verify_res = client.post("/api/v1/auth/verify-email", json={"code": "123456"}, headers=headers)
    assert verify_res.status_code == 200
    assert verify_res.json()["email_verified"] is True


def test_employer_registration(client):
    payload = {
        "email": "recruiter@vk.company",
        "password": "vk_hiring_password",
        "role": "EMPLOYER",
        "company_name": "VK Технологии",
        "consent_personal_data": True,
        "consent_profile_distribution": False,
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["role"] == "EMPLOYER"


def test_152_fz_consents_flow(client):
    # Log in as candidate
    login_res = client.post("/api/v1/auth/login", json={
        "email": "champion.coder@fsp.ru",
        "password": "secret_password_2026",
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Check initial consent status
    status_res = client.get("/api/v1/consents/status", headers=headers)
    assert status_res.status_code == 200
    st_data = status_res.json()
    assert st_data["personal_data_active"] is True
    assert st_data["profile_distribution_active"] is True
    assert len(st_data["consents"]) == 2

    # 2. Revoke profile distribution consent
    revoke_res = client.post("/api/v1/consents/revoke", json={"consent_type": "PROFILE_DISTRIBUTION"}, headers=headers)
    assert revoke_res.status_code == 200
    rev_data = revoke_res.json()
    assert rev_data["is_given"] is False
    assert rev_data["revoked_at"] is not None

    # Check updated status
    st2 = client.get("/api/v1/consents/status", headers=headers).json()
    assert st2["profile_distribution_active"] is False

    # 3. Give consent again with version 2.0
    give_res = client.post("/api/v1/consents/give", json={"consent_type": "PROFILE_DISTRIBUTION", "version": "2.0"}, headers=headers)
    assert give_res.status_code == 200
    g_data = give_res.json()
    assert g_data["is_given"] is True
    assert g_data["version"] == "2.0"
    assert g_data["revoked_at"] is None


def test_administrator_cannot_self_register(client):
    res = client.post("/api/v1/auth/register", json={"email": "root@example.com", "password": "secret123", "role": "ADMIN"})
    assert res.status_code == 422


def test_registration_requires_personal_data_consent(client):
    res = client.post("/api/v1/auth/register", json={
        "email": "noconsent@example.com", "password": "secret123", "consent_personal_data": False,
    })
    assert res.status_code == 400 and "152" in res.json()["detail"]


def test_typed_in_fsp_id_is_not_marked_verified(client):
    res = client.post("/api/v1/auth/register", json={
        "email": "fspclaim@example.com", "password": "secret123", "fsp_id": "FSP-1001",
    })
    assert res.status_code == 201
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    profile = client.get("/api/v1/me/profile", headers=headers).json()
    assert profile["fsp_id"] == "FSP-1001" and profile["is_fsp_verified"] is False


def test_only_own_email_can_be_verified(client):
    victim = client.post("/api/v1/auth/register", json={"email": "victim@example.com", "password": "secret123"})
    attacker = client.post("/api/v1/auth/register", json={"email": "attacker@example.com", "password": "secret123"})
    assert victim.status_code == attacker.status_code == 201
    headers = {"Authorization": f"Bearer {attacker.json()['access_token']}"}

    res = client.post("/api/v1/auth/verify-email", json={"email": "victim@example.com", "code": "123456"}, headers=headers)
    assert res.status_code == 403
    victim_headers = {"Authorization": f"Bearer {victim.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=victim_headers).json()["email_verified"] is False
