

def test_dictionaries_overview(client):
    response = client.get("/api/v1/dictionaries/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["directions_count"] >= 4
    assert data["specializations_count"] >= 6
    assert data["grades_count"] >= 4
    assert data["categories_count"] >= 24
    assert data["skills_count"] >= 300


def test_directions_and_specializations(client):
    response = client.get("/api/v1/dictionaries/directions")
    assert response.status_code == 200
    data = response.json()
    codes = [d["code"] for d in data]
    assert "DEVELOPMENT" in codes
    assert "DATA_ML" in codes
    assert "QA" in codes
    assert "INFRASTRUCTURE" in codes


def test_grades_and_behavioral_indicators(client):
    response = client.get("/api/v1/dictionaries/grades")
    assert response.status_code == 200
    grades = response.json()
    assert len(grades) == 4
    grade_codes = [g["code"] for g in grades]
    assert grade_codes == ["INTERN", "JUNIOR", "MIDDLE", "SENIOR"]
    
    # Check behavioral indicators are populated
    for g in grades:
        assert g["behavioral_indicators"] is not None
        assert len(g["behavioral_indicators"]) >= 3


def test_categories(client):
    response = client.get("/api/v1/dictionaries/categories?specialization=BACKEND")
    assert response.status_code == 200
    cats = response.json()
    assert len(cats) == 4
    cat_codes = [c["code"] for c in cats]
    assert "BACKEND_INTERN" in cat_codes
    assert "BACKEND_MIDDLE" in cat_codes


def test_skill_search_and_synonyms(client):
    # Search by direct name
    res = client.get("/api/v1/dictionaries/skills?q=python")
    assert res.status_code == 200
    names = [s["name"] for s in res.json()]
    assert any("Python" in n for n in names)

    # Search by Russian synonym: "постгрес" -> should match PostgreSQL
    res = client.get("/api/v1/dictionaries/skills?q=постгрес")
    assert res.status_code == 200
    names = [s["name"] for s in res.json()]
    assert any("PostgreSQL" in n for n in names)

    # Search by abbreviation / slang: "k8s" -> should match Kubernetes
    res = client.get("/api/v1/dictionaries/skills?q=k8s")
    assert res.status_code == 200
    names = [s["name"] for s in res.json()]
    assert any("Kubernetes" in n for n in names)
