import aws_cdk as cdk
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_s3 as s3
from constructs import Construct


class DataStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        self.tables: dict[str, dynamodb.Table] = {}

        # Users table
        self.tables["Users"] = dynamodb.Table(
            self,
            "UsersTable",
            table_name="Users",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # Devices table
        self.tables["Devices"] = dynamodb.Table(
            self,
            "DevicesTable",
            table_name="Devices",
            partition_key=dynamodb.Attribute(
                name="device_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )
        self.tables["Devices"].add_global_secondary_index(
            index_name="device_token-index",
            partition_key=dynamodb.Attribute(
                name="device_token", type=dynamodb.AttributeType.STRING
            ),
        )

        # InviteCodes table
        self.tables["InviteCodes"] = dynamodb.Table(
            self,
            "InviteCodesTable",
            table_name="InviteCodes",
            partition_key=dynamodb.Attribute(
                name="code", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # Conversations table
        self.tables["Conversations"] = dynamodb.Table(
            self,
            "ConversationsTable",
            table_name="Conversations",
            partition_key=dynamodb.Attribute(
                name="conversation_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )
        self.tables["Conversations"].add_global_secondary_index(
            index_name="user_conversations-index",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="updated_at", type=dynamodb.AttributeType.STRING
            ),
        )

        # Messages table
        self.tables["Messages"] = dynamodb.Table(
            self,
            "MessagesTable",
            table_name="Messages",
            partition_key=dynamodb.Attribute(
                name="conversation_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="sort_key", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # MemberProfiles table
        self.tables["MemberProfiles"] = dynamodb.Table(
            self,
            "MemberProfilesTable",
            table_name="MemberProfiles",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # AgentConfigs table
        self.tables["AgentConfigs"] = dynamodb.Table(
            self,
            "AgentConfigsTable",
            table_name="AgentConfigs",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="agent_type", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # FamilyRelationships table
        self.tables["FamilyRelationships"] = dynamodb.Table(
            self,
            "FamilyRelationshipsTable",
            table_name="FamilyRelationships",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="related_user_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # NOTE: Devices user_id-index GSI already exists on the physical table
        # but is not tracked by CloudFormation. Do NOT add it here or CFN will
        # fail with "index already exists". The GSI was created out-of-band.

        # HealthAuditLog table
        self.tables["HealthAuditLog"] = dynamodb.Table(
            self,
            "HealthAuditLogTable",
            table_name="HealthAuditLog",
            partition_key=dynamodb.Attribute(
                name="record_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="audit_sk", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )
        self.tables["HealthAuditLog"].add_global_secondary_index(
            index_name="user-audit-index",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at", type=dynamodb.AttributeType.STRING
            ),
        )

        # HealthRecords table
        self.tables["HealthRecords"] = dynamodb.Table(
            self,
            "HealthRecordsTable",
            table_name="HealthRecords",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="record_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )
        self.tables["HealthRecords"].add_global_secondary_index(
            index_name="record_type-index",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="record_type", type=dynamodb.AttributeType.STRING
            ),
        )

        # HealthObservations table
        self.tables["HealthObservations"] = dynamodb.Table(
            self,
            "HealthObservationsTable",
            table_name="HealthObservations",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="observation_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )
        self.tables["HealthObservations"].add_global_secondary_index(
            index_name="category-index",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="category", type=dynamodb.AttributeType.STRING
            ),
        )

        # HealthDocuments table
        self.tables["HealthDocuments"] = dynamodb.Table(
            self,
            "HealthDocumentsTable",
            table_name="HealthDocuments",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="document_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # AgentTemplates table
        self.tables["AgentTemplates"] = dynamodb.Table(
            self,
            "AgentTemplatesTable",
            table_name="AgentTemplates",
            partition_key=dynamodb.Attribute(
                name="template_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )
        self.tables["AgentTemplates"].add_global_secondary_index(
            index_name="agent_type-index",
            partition_key=dynamodb.Attribute(
                name="agent_type", type=dynamodb.AttributeType.STRING
            ),
        )

        # ChatMedia table (for image uploads with TTL)
        self.tables["ChatMedia"] = dynamodb.Table(
            self,
            "ChatMediaTable",
            table_name="ChatMedia",
            partition_key=dynamodb.Attribute(
                name="media_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            time_to_live_attribute="expires_at",
        )

        # MemorySharingConfig table
        self.tables["MemorySharingConfig"] = dynamodb.Table(
            self,
            "MemorySharingConfigTable",
            table_name="MemorySharingConfig",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # StorageConfig table (user storage provider preferences)
        self.tables["StorageConfig"] = dynamodb.Table(
            self,
            "StorageConfigTable",
            table_name="StorageConfig",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # OAuthTokens table (cloud storage provider OAuth tokens)
        self.tables["OAuthTokens"] = dynamodb.Table(
            self,
            "OAuthTokensTable",
            table_name="OAuthTokens",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="provider", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # OAuthState table (CSRF protection for OAuth flows)
        self.tables["OAuthState"] = dynamodb.Table(
            self,
            "OAuthStateTable",
            table_name="OAuthState",
            partition_key=dynamodb.Attribute(
                name="state", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            time_to_live_attribute="expires_at",
        )


        # S3 bucket for health documents
        self.documents_bucket = s3.Bucket(
            self,
            "HealthDocumentsBucket",
            bucket_name=f"homeagent-health-documents-{cdk.Aws.ACCOUNT_ID}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=cdk.Duration.days(90),
                        )
                    ]
                )
            ],
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.PUT],
                    allowed_origins=["*"],
                    allowed_headers=["*"],
                    max_age=3600,
                )
            ],
        )
