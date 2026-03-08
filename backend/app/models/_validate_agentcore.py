"""Quick validation script for agentcore data models."""
from __future__ import annotations
import sys
import os

# Add backend to path so we can import without Flask
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

# Patch flask imports to avoid dependency
import types
flask_mod = types.ModuleType('flask')
flask_mod.Flask = type('Flask', (), {})
flask_mod.g = type('g', (), {})()
flask_mod.current_app = type('current_app', (), {'config': {}})()
sys.modules['flask'] = flask_mod
flask_cors_mod = types.ModuleType('flask_cors')
flask_cors_mod.CORS = lambda *a, **kw: None
sys.modules['flask_cors'] = flask_cors_mod

from backend.app.models.agentcore import (
    AgentTemplate, AgentConfig, SubAgentToolConfig,
    FamilyMemoryRecord, MemberMemoryRecord, IdentityContext,
    StreamEvent, CombinedSessionManager, MemoryConfig,
    FamilyMemoryCategory, StreamEventType, CONTENT_MAX_LENGTH,
)

errors = []

# Test 1: AgentTemplate valid
t = AgentTemplate(
    template_id="tmpl_01", agent_type="health_advisor", name="Health Advisor",
    description="Advises on health", system_prompt="You are a health advisor",
    available_to="all", created_by="system",
)
try:
    t.validate()
except Exception as e:
    errors.append(f"AgentTemplate valid case failed: {e}")

# Test 2: AgentTemplate invalid agent_type
t2 = AgentTemplate(
    template_id="tmpl_02", agent_type="INVALID TYPE!", name="Bad",
    description="Bad", system_prompt="",
)
try:
    t2.validate()
    errors.append("AgentTemplate should reject invalid agent_type")
except ValueError:
    pass

# Test 3: AgentTemplate available_to empty list
t3 = AgentTemplate(
    template_id="tmpl_03", agent_type="test_agent", name="Test",
    description="Test", system_prompt="", available_to=[],
)
try:
    t3.validate()
    errors.append("AgentTemplate should reject empty available_to list")
except ValueError:
    pass

# Test 4: AgentConfig valid
ac = AgentConfig(user_id="usr_01", agent_type="health_advisor")
try:
    ac.validate()
except Exception as e:
    errors.append(f"AgentConfig valid case failed: {e}")

# Test 5: FamilyMemoryRecord valid
fm = FamilyMemoryRecord(
    family_id="fam_01", memory_key="health/allergy/peanut",
    category="health", content="Peanut allergy",
)
try:
    fm.validate()
except Exception as e:
    errors.append(f"FamilyMemoryRecord valid case failed: {e}")

# Test 6: FamilyMemoryRecord invalid category
fm2 = FamilyMemoryRecord(
    family_id="fam_01", memory_key="health/allergy/peanut",
    category="invalid", content="test",
)
try:
    fm2.validate()
    errors.append("FamilyMemoryRecord should reject invalid category")
except ValueError:
    pass

# Test 7: FamilyMemoryRecord content too long
fm3 = FamilyMemoryRecord(
    family_id="fam_01", memory_key="health/allergy/peanut",
    category="health", content="x" * 10001,
)
try:
    fm3.validate()
    errors.append("FamilyMemoryRecord should reject content > 10000 chars")
except ValueError:
    pass

# Test 8: FamilyMemoryRecord invalid memory_key format
fm4 = FamilyMemoryRecord(
    family_id="fam_01", memory_key="bad-key",
    category="health", content="test",
)
try:
    fm4.validate()
    errors.append("FamilyMemoryRecord should reject invalid memory_key format")
except ValueError:
    pass

# Test 9: IdentityContext valid
ic = IdentityContext(user_id="usr_01", family_id="fam_01", role="admin", cognito_sub="abc-123")
try:
    ic.validate()
except Exception as e:
    errors.append(f"IdentityContext valid case failed: {e}")

# Test 10: IdentityContext invalid role
ic2 = IdentityContext(user_id="usr_01", family_id=None, role="superuser", cognito_sub="abc")
try:
    ic2.validate()
    errors.append("IdentityContext should reject invalid role")
except ValueError:
    pass

# Test 11: StreamEvent valid
se = StreamEvent(type="text_delta", content="Hello")
try:
    se.validate()
except Exception as e:
    errors.append(f"StreamEvent valid case failed: {e}")

# Test 12: StreamEvent invalid type
se2 = StreamEvent(type="invalid_type")
try:
    se2.validate()
    errors.append("StreamEvent should reject invalid type")
except ValueError:
    pass

# Test 13: CombinedSessionManager valid
csm = CombinedSessionManager(
    family_config=MemoryConfig(memory_id="fam-store", session_id="s1", actor_id="fam_01"),
    member_config=MemoryConfig(memory_id="mem-store", session_id="s1", actor_id="usr_01"),
)
try:
    csm.validate()
except Exception as e:
    errors.append(f"CombinedSessionManager valid case failed: {e}")

# Test 14: CombinedSessionManager same memory_id
csm2 = CombinedSessionManager(
    family_config=MemoryConfig(memory_id="same-id", session_id="s1", actor_id="fam_01"),
    member_config=MemoryConfig(memory_id="same-id", session_id="s1", actor_id="usr_01"),
)
try:
    csm2.validate()
    errors.append("CombinedSessionManager should reject same memory_ids")
except ValueError:
    pass

# Test 15: CONTENT_MAX_LENGTH is 10000
assert CONTENT_MAX_LENGTH == 10_000, f"Expected 10000, got {CONTENT_MAX_LENGTH}"

# Test 16: Enums
assert FamilyMemoryCategory.HEALTH.value == "health"
assert FamilyMemoryCategory.PREFERENCES.value == "preferences"
assert FamilyMemoryCategory.CONTEXT.value == "context"
assert StreamEventType.TEXT_DELTA.value == "text_delta"
assert StreamEventType.TOOL_USE.value == "tool_use"
assert StreamEventType.MESSAGE_DONE.value == "message_done"
assert StreamEventType.ERROR.value == "error"

if errors:
    print("FAILURES:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("All 16 validation checks passed!")
