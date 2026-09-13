"""Knowledge prerequisite graph: shared structure, layering, blocked-state
and user-scoped explainable recommendations."""
from __future__ import annotations

EXPECTED_CHAINS = {
    "Python / asyncio", "FastAPI / Depends", "Database / ORM", "Redis / Cache",
    "RAG", "Agent / Tool Calling", "System Design", "LeetCode / Algorithms",
}


def _graph(client, headers) -> dict:
    response = client.get("/api/knowledge/prerequisites", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_graph_acyclic_and_layered(client, make_user):
    user = make_user()
    data = _graph(client, user["headers"])

    nodes = {n["slug"]: n for n in data["nodes"]}
    assert set(n["chain"] for n in data["nodes"]) == EXPECTED_CHAINS
    assert len(nodes) == len(data["nodes"])  # slugs unique
    assert len(nodes) >= 35

    cross_chain = [e for e in data["edges"] if e["cross_chain"]]
    assert len(cross_chain) == 3  # async-endpoint→event-loop, isolation→race-condition, nx-lock→race-condition
    for edge in data["edges"]:
        assert nodes[edge["from_slug"]]["layer"] < nodes[edge["to_slug"]]["layer"]


def test_chain_mastery_defaults_from_seed(client, make_user):
    user = make_user()
    data = _graph(client, user["headers"])
    mastery = data["chain_mastery"]

    assert mastery["FastAPI / Depends"]["score"] == 78
    assert mastery["System Design"]["score"] == 52
    assert mastery["RAG"]["retrievability"] is not None


def test_blocked_nodes_follow_weak_prerequisite_chains(client, make_user):
    user = make_user()
    nodes = {n["slug"]: n for n in _graph(client, user["headers"])["nodes"]}

    # Python / asyncio seeded at 61 (< 70) so everything downstream of the
    # chain is blocked, including via cross-chain edges.
    assert nodes["lock"]["blocked"] is True
    assert "Race Condition 竞态" in nodes["lock"]["weak_prereqs"]
    assert nodes["race-condition"]["blocked"] is True

    # FastAPI / Depends is seeded at 78 (>= 70): its own nodes are not
    # blocked even when one of them feeds the weak asyncio chain.
    assert nodes["depends"]["blocked"] is False
    assert nodes["middleware"]["blocked"] is False
    assert nodes["async-endpoint"]["blocked"] is False
    # ...but the cross-chain edge async-endpoint -> event-loop leaves
    # event-loop blocked through the weak asyncio chain anyway (task).
    assert nodes["event-loop"]["blocked"] is True


def test_recommendations_list_only_weak_chains_sorted(client, make_user):
    user = make_user()
    response = client.get("/api/knowledge/prerequisites/recommendations", headers=user["headers"])
    assert response.status_code == 200, response.text
    recs = response.json()

    chains = {r["chain"] for r in recs}
    assert chains == {"Python / asyncio", "Database / ORM", "Redis / Cache", "System Design", "LeetCode / Algorithms"}
    assert "FastAPI / Depends" not in chains and "RAG" not in chains

    assert [r["blocked_count"] for r in recs] == sorted((r["blocked_count"] for r in recs), reverse=True)
    weak_chain = next(r for r in recs if r["chain"] == "Python / asyncio")
    assert weak_chain["blocked_count"] > 0
    assert weak_chain["score"] == 61
    assert "61" in weak_chain["reason"]
    assert weak_chain["first_steps"]


def test_recommendations_reflect_review_progress(client, make_user):
    """Reviewing a weak chain past the threshold removes it from that user's
    recommendations only — Alice's plan is untouched."""
    alice = make_user("alice")
    bob = make_user("bob")

    def recommendations(headers):
        response = client.get("/api/knowledge/prerequisites/recommendations", headers=headers)
        assert response.status_code == 200, response.text
        return response.json()

    before = recommendations(bob["headers"])
    assert any(r["chain"] == "System Design" for r in before)

    for _ in range(2):  # 52 + 9 + 9 = 70 reaches the threshold
        reviewed = client.post("/api/learning/System Design/review?grade=5", headers=bob["headers"])
        assert reviewed.status_code == 200, reviewed.text

    after_bob = recommendations(bob["headers"])
    assert all(r["chain"] != "System Design" for r in after_bob)

    after_alice = recommendations(alice["headers"])
    assert any(r["chain"] == "System Design" for r in after_alice)

    # Shared structure: both users see identical layers regardless of progress.
    alice_nodes = {n["slug"]: n["layer"] for n in _graph(client, alice["headers"])["nodes"]}
    bob_nodes = {n["slug"]: n["layer"] for n in _graph(client, bob["headers"])["nodes"]}
    assert alice_nodes == bob_nodes
