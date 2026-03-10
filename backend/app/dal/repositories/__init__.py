"""Concrete repository implementations for each entity."""

from app.dal.repositories.agent_config_repo import AgentConfigRepository
from app.dal.repositories.agent_template_repo import AgentTemplateRepository
from app.dal.repositories.chat_media_repo import ChatMediaRepository
from app.dal.repositories.conversation_repo import ConversationRepository
from app.dal.repositories.device_repo import DeviceRepository
from app.dal.repositories.family_relationship_repo import FamilyRelationshipRepository
from app.dal.repositories.family_repo import FamilyRepository
from app.dal.repositories.health_audit_repo import HealthAuditRepository
from app.dal.repositories.health_document_repo import HealthDocumentRepository
from app.dal.repositories.health_observation_repo import HealthObservationRepository
from app.dal.repositories.health_record_repo import HealthRecordRepository
from app.dal.repositories.invite_code_repo import InviteCodeRepository
from app.dal.repositories.member_permission_repo import MemberPermissionRepository
from app.dal.repositories.membership_repo import MembershipRepository
from app.dal.repositories.memory_sharing_config_repo import (
    MemorySharingConfigRepository,
)
from app.dal.repositories.message_repo import MessageRepository
from app.dal.repositories.oauth_state_repo import OAuthStateRepository
from app.dal.repositories.oauth_token_repo import OAuthTokenRepository
from app.dal.repositories.profile_repo import ProfileRepository
from app.dal.repositories.storage_config_repo import StorageConfigRepository
from app.dal.repositories.user_repo import UserRepository

__all__ = [
    "AgentConfigRepository",
    "AgentTemplateRepository",
    "ChatMediaRepository",
    "ConversationRepository",
    "DeviceRepository",
    "FamilyRelationshipRepository",
    "FamilyRepository",
    "HealthAuditRepository",
    "HealthDocumentRepository",
    "HealthObservationRepository",
    "HealthRecordRepository",
    "InviteCodeRepository",
    "MemberPermissionRepository",
    "MembershipRepository",
    "MemorySharingConfigRepository",
    "MessageRepository",
    "OAuthStateRepository",
    "OAuthTokenRepository",
    "ProfileRepository",
    "StorageConfigRepository",
    "UserRepository",
]
