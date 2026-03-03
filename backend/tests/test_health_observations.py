"""Tests for health observations service — create, list, filter, validation."""

import pytest

from app.services.health_observations import (
    create_observation,
    delete_all_observations,
    list_observations,
)


def test_create_observation(app):
    with app.app_context():
        obs = create_observation(
            user_id="user1",
            category="diet",
            summary="Ate mostly vegetables today",
            detail="Had salad for lunch and stir-fry for dinner",
            confidence="high",
        )
        assert obs["category"] == "diet"
        assert obs["summary"] == "Ate mostly vegetables today"
        assert "observation_id" in obs
        assert "created_at" in obs


def test_create_observation_invalid_category(app):
    with app.app_context():
        with pytest.raises(ValueError, match="Invalid category"):
            create_observation(
                user_id="user1",
                category="invalid_cat",
                summary="Test",
            )


def test_create_observation_all_valid_categories(app):
    with app.app_context():
        for cat in ["diet", "exercise", "sleep", "symptom", "mood", "general"]:
            obs = create_observation(
                user_id="user1",
                category=cat,
                summary=f"Test {cat}",
            )
            assert obs["category"] == cat


def test_list_observations(app):
    with app.app_context():
        create_observation(user_id="user2", category="diet", summary="Obs 1")
        create_observation(user_id="user2", category="exercise", summary="Obs 2")
        create_observation(user_id="user2", category="diet", summary="Obs 3")

        all_obs = list_observations("user2")
        assert len(all_obs) == 3


def test_list_observations_filter_by_category(app):
    with app.app_context():
        create_observation(user_id="user3", category="diet", summary="Diet 1")
        create_observation(user_id="user3", category="sleep", summary="Sleep 1")
        create_observation(user_id="user3", category="diet", summary="Diet 2")

        diet_obs = list_observations("user3", category="diet")
        assert len(diet_obs) == 2
        assert all(o["category"] == "diet" for o in diet_obs)

        sleep_obs = list_observations("user3", category="sleep")
        assert len(sleep_obs) == 1


def test_list_observations_empty(app):
    with app.app_context():
        obs = list_observations("nonexistent_user")
        assert obs == []


def test_create_observation_with_source_conversation(app):
    with app.app_context():
        obs = create_observation(
            user_id="user4",
            category="symptom",
            summary="Headache reported",
            source_conversation_id="conv_123",
        )
        assert obs["source_conversation_id"] == "conv_123"


def test_create_observation_default_confidence(app):
    with app.app_context():
        obs = create_observation(
            user_id="user5",
            category="mood",
            summary="Seemed happy",
        )
        assert obs["confidence"] == "medium"


def test_delete_all_observations(app):
    with app.app_context():
        create_observation(user_id="user6", category="diet", summary="Obs 1")
        create_observation(user_id="user6", category="sleep", summary="Obs 2")

        delete_all_observations("user6")

        obs = list_observations("user6")
        assert obs == []


def test_delete_all_observations_no_records(app):
    """delete_all_observations should not error when there are no records."""
    with app.app_context():
        delete_all_observations("nonexistent_user")
