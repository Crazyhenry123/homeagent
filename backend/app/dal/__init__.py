"""Unified Data Access Layer for HomeAgent DynamoDB tables."""

from typing import Any

from flask import current_app

from app.dal.repositories import (
    AgentConfigRepository,
    AgentTemplateRepository,
    ChatMediaRepository,
    ConversationRepository,
    DeviceRepository,
    FamilyRelationshipRepository,
    FamilyRepository,
    HealthAuditRepository,
    HealthDocumentRepository,
    HealthObservationRepository,
    HealthRecordRepository,
    InviteCodeRepository,
    MemberPermissionRepository,
    MembershipRepository,
    MemorySharingConfigRepository,
    MessageRepository,
    OAuthStateRepository,
    OAuthTokenRepository,
    ProfileRepository,
    StorageConfigRepository,
    UserRepository,
)


class DAL:
    """Container for all repository instances.

    Instantiated once per Flask app and stored in ``app.extensions["dal"]``.
    """

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        self.users = UserRepository(dynamodb_resource, table_prefix)
        self.devices = DeviceRepository(dynamodb_resource, table_prefix)
        self.invite_codes = InviteCodeRepository(dynamodb_resource, table_prefix)
        self.families = FamilyRepository(dynamodb_resource, table_prefix)
        self.memberships = MembershipRepository(dynamodb_resource, table_prefix)
        self.conversations = ConversationRepository(dynamodb_resource, table_prefix)
        self.messages = MessageRepository(dynamodb_resource, table_prefix)
        self.profiles = ProfileRepository(dynamodb_resource, table_prefix)
        self.agent_configs = AgentConfigRepository(dynamodb_resource, table_prefix)
        self.agent_templates = AgentTemplateRepository(dynamodb_resource, table_prefix)
        self.health_records = HealthRecordRepository(dynamodb_resource, table_prefix)
        self.health_observations = HealthObservationRepository(
            dynamodb_resource, table_prefix
        )
        self.health_audit = HealthAuditRepository(dynamodb_resource, table_prefix)
        self.health_documents = HealthDocumentRepository(
            dynamodb_resource, table_prefix
        )
        self.family_relationships = FamilyRelationshipRepository(
            dynamodb_resource, table_prefix
        )
        self.chat_media = ChatMediaRepository(dynamodb_resource, table_prefix)
        self.member_permissions = MemberPermissionRepository(
            dynamodb_resource, table_prefix
        )
        self.memory_sharing_config = MemorySharingConfigRepository(
            dynamodb_resource, table_prefix
        )
        self.storage_config = StorageConfigRepository(dynamodb_resource, table_prefix)
        self.oauth_tokens = OAuthTokenRepository(dynamodb_resource, table_prefix)
        self.oauth_state = OAuthStateRepository(dynamodb_resource, table_prefix)


def get_dal() -> DAL:
    """Return the DAL instance from the current Flask app context."""
    return current_app.extensions["dal"]
