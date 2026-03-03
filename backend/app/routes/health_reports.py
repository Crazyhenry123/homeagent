"""Health report generation endpoint."""

from flask import Blueprint, jsonify

from app.auth import require_admin, require_auth
from app.services.health_observations import list_observations
from app.services.health_records import get_health_summary
from app.services.profile import get_profile

health_reports_bp = Blueprint("health_reports", __name__)


@health_reports_bp.route(
    "/health-reports/<user_id>/generate", methods=["POST"]
)
@require_auth
@require_admin
def generate_health_report(user_id: str):
    """Build a health report from records + observations for a user."""
    profile = get_profile(user_id)
    if not profile:
        return jsonify({"error": "User not found"}), 404

    summary = get_health_summary(user_id)
    observations = list_observations(user_id)

    # Group observations by category
    obs_by_category: dict[str, list[dict]] = {}
    for obs in observations:
        cat = obs["category"]
        obs_by_category.setdefault(cat, []).append(
            {
                "summary": obs["summary"],
                "detail": obs.get("detail", ""),
                "confidence": obs.get("confidence", "medium"),
                "observed_at": obs.get("observed_at", ""),
            }
        )

    report = {
        "user_id": user_id,
        "display_name": profile.get("display_name", ""),
        "family_role": profile.get("family_role", ""),
        "health_notes": profile.get("health_notes", ""),
        "records_summary": summary,
        "observations": obs_by_category,
        "observation_count": len(observations),
    }

    return jsonify(report)
