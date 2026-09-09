from pathlib import Path

from sqlalchemy import func, select

from app.models import AIGeneration, Assessment, Question, QuestionScore, StudentAssessment, Worksheet

ROOT = Path(__file__).resolve().parents[2]


def test_complete_demo_flow(client):
    health = client.get("/health")
    assert health.status_code == 200

    seeded = client.post("/api/v1/demo/load")
    assert seeded.status_code == 200, seeded.text
    assessment_id = seeded.json()["id"]

    overview = client.get(f"/api/v1/assessments/{assessment_id}/overview")
    assert overview.status_code == 200
    assert overview.json()["student_count"] == 4

    students = client.get(f"/api/v1/assessments/{assessment_id}/students").json()
    assert len(students) == 4
    student_id = students[0]["id"]

    detail = client.get(f"/api/v1/students/{student_id}")
    assert detail.status_code == 200
    assert detail.json()["analysis"]["percentage"] >= 0

    for endpoint in (
        "generate-diagnosis", "generate-recommendations", "generate-lesson-plan",
        "generate-worksheet",
    ):
        response = client.post(f"/api/v1/students/{student_id}/{endpoint}", json={})
        assert response.status_code == 200, response.text
        assert response.json()["content"]

    assert client.get(f"/api/v1/students/{student_id}/report").status_code == 200
    assert client.get(f"/api/v1/students/{student_id}/worksheet").status_code == 200


def test_upload_contract_returns_actionable_validation(client):
    created = client.post("/api/v1/assessments", json={"title": "Cycles test"}).json()
    with (ROOT / "examples" / "p4_light_blueprint.json").open("rb") as blueprint:
        response = client.post(
            f"/api/v1/assessments/{created['id']}/blueprint",
            files={"file": ("blueprint.json", blueprint, "application/json")},
        )
    assert response.status_code == 200
    invalid_csv = b"student_id,student_name,Q1\nS1,A,99"
    response = client.post(
        f"/api/v1/assessments/{created['id']}/results",
        files={"file": ("scores.csv", invalid_csv, "text/csv")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0]["suggested_fix"]


def test_delete_assessment_removes_related_data(client, db):
    seeded = client.post("/api/v1/demo/load")
    assessment_id = seeded.json()["id"]
    student_id = client.get(
        f"/api/v1/assessments/{assessment_id}/students"
    ).json()[0]["id"]
    generated = client.post(f"/api/v1/students/{student_id}/generate-worksheet", json={})
    assert generated.status_code == 200

    deleted = client.delete(f"/api/v1/assessments/{assessment_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/assessments/{assessment_id}").status_code == 404

    for model in (Assessment, Question, StudentAssessment, QuestionScore, AIGeneration, Worksheet):
        assert db.scalar(select(func.count()).select_from(model)) == 0
