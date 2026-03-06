import React, {useEffect, useState} from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import {
  deleteAgentConfig,
  deleteMember,
  getAgentConfigs,
  getProfile,
  putAgentConfig,
  updateProfile,
} from '../services/api';
import {useSession} from '../store';
import type {RootStackParamList} from '../navigation/AppNavigator';
import type {AgentConfig, MemberProfile} from '../types';

type Props = NativeStackScreenProps<RootStackParamList, 'AdminMemberDetail'>;

export function AdminMemberDetailScreen({route, navigation}: Props) {
  const {userId} = route.params;
  const {session} = useSession();
  const agentTypes = session.agents.agentTypes;
  const [profile, setProfile] = useState<MemberProfile | null>(null);
  const [agentConfigs, setAgentConfigs] = useState<AgentConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [familyRole, setFamilyRole] = useState('');
  const [healthNotes, setHealthNotes] = useState('');

  // Verify admin role from session
  const currentUserRole = session.user?.role;

  useEffect(() => {
    Promise.all([
      getProfile(userId),
      getAgentConfigs(userId),
    ])
      .then(([p, configs]) => {
        setProfile(p);
        setFamilyRole(p.family_role);
        setHealthNotes(p.health_notes);
        setAgentConfigs(configs.agent_configs);
      })
      .catch(err =>
        Alert.alert(
          'Error',
          err instanceof Error ? err.message : 'Failed to load member data',
        ),
      )
      .finally(() => setLoading(false));
  }, [userId]);

  const handleSaveProfile = async () => {
    setSaving(true);
    try {
      const updated = await updateProfile(userId, {
        family_role: familyRole,
        health_notes: healthNotes,
      });
      setProfile(updated);
      Alert.alert('Saved', 'Profile updated');
    } catch (err) {
      Alert.alert(
        'Error',
        err instanceof Error ? err.message : 'Failed to save',
      );
    } finally {
      setSaving(false);
    }
  };

  const handleToggleAgent = async (agentType: string, enabled: boolean) => {
    try {
      if (enabled) {
        const config = await putAgentConfig(userId, agentType, {enabled: true});
        setAgentConfigs(prev => {
          const filtered = prev.filter(c => c.agent_type !== agentType);
          return [...filtered, config];
        });
      } else {
        await deleteAgentConfig(userId, agentType);
        setAgentConfigs(prev =>
          prev.filter(c => c.agent_type !== agentType),
        );
      }
    } catch (err) {
      Alert.alert(
        'Error',
        err instanceof Error ? err.message : 'Failed to update agent',
      );
    }
  };

  const handleDeleteMember = () => {
    Alert.alert(
      'Remove Member',
      `Are you sure you want to remove ${profile?.display_name ?? 'this member'}? This will permanently delete all their data including conversations, messages, and device registrations. This action cannot be undone.`,
      [
        {text: 'Cancel', style: 'cancel'},
        {
          text: 'Remove',
          style: 'destructive',
          onPress: async () => {
            setDeleting(true);
            try {
              await deleteMember(userId);
              Alert.alert('Removed', 'Member has been removed.', [
                {text: 'OK', onPress: () => navigation.goBack()},
              ]);
            } catch (err) {
              Alert.alert(
                'Error',
                err instanceof Error ? err.message : 'Failed to remove member',
              );
            } finally {
              setDeleting(false);
            }
          },
        },
      ],
    );
  };

  const isAgentEnabled = (agentType: string): boolean => {
    return agentConfigs.some(
      c => c.agent_type === agentType && c.enabled,
    );
  };

  if (loading) {
    return (
      <View style={[styles.container, styles.centered]}>
        <ActivityIndicator size="large" color="#007AFF" />
      </View>
    );
  }

  if (currentUserRole && currentUserRole !== 'admin' && currentUserRole !== 'owner') {
    return (
      <View style={[styles.container, styles.centered]}>
        <Text style={{fontSize: 16, color: '#8E8E93'}}>Access denied. Admin role required.</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container}>
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionHeaderText}>MEMBER INFO</Text>
      </View>

      <View style={styles.infoRow}>
        <Text style={styles.label}>Name</Text>
        <Text style={styles.value}>{profile?.display_name}</Text>
      </View>
      <View style={styles.infoRow}>
        <Text style={styles.label}>Role</Text>
        <Text style={styles.value}>{profile?.role}</Text>
      </View>

      <View style={styles.sectionHeader}>
        <Text style={styles.sectionHeaderText}>PROFILE</Text>
      </View>

      <View style={styles.field}>
        <Text style={styles.label}>Family Role</Text>
        <TextInput
          style={styles.input}
          value={familyRole}
          onChangeText={setFamilyRole}
          placeholder="e.g., Parent, Child"
        />
      </View>
      <View style={styles.field}>
        <Text style={styles.label}>Health Notes</Text>
        <TextInput
          style={[styles.input, styles.multilineInput]}
          value={healthNotes}
          onChangeText={setHealthNotes}
          placeholder="Allergies, restrictions, etc."
          multiline
        />
      </View>

      <TouchableOpacity
        style={[styles.saveButton, saving && styles.saveButtonDisabled]}
        onPress={handleSaveProfile}
        disabled={saving}>
        <Text style={styles.saveButtonText}>
          {saving ? 'Saving...' : 'Save Profile'}
        </Text>
      </TouchableOpacity>

      <View style={styles.sectionHeader}>
        <Text style={styles.sectionHeaderText}>AI AGENTS</Text>
      </View>

      {Object.entries(agentTypes).map(([type, info]) => (
        <View key={type} style={styles.agentRow}>
          <View style={styles.agentInfo}>
            <Text style={styles.agentName}>{info.name}</Text>
            <Text style={styles.agentDescription}>{info.description}</Text>
          </View>
          <Switch
            value={isAgentEnabled(type)}
            onValueChange={value => handleToggleAgent(type, value)}
          />
        </View>
      ))}

      {userId !== session.user?.userId && (
        <>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionHeaderText}>DANGER ZONE</Text>
          </View>
          <TouchableOpacity
            style={[styles.deleteButton, deleting && styles.deleteButtonDisabled]}
            onPress={handleDeleteMember}
            disabled={deleting}>
            <Text style={styles.deleteButtonText}>
              {deleting ? 'Removing...' : 'Remove Member'}
            </Text>
          </TouchableOpacity>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F2F2F7',
  },
  centered: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  sectionHeader: {
    paddingHorizontal: 16,
    paddingTop: 24,
    paddingBottom: 8,
  },
  sectionHeaderText: {
    fontSize: 13,
    color: '#8E8E93',
    fontWeight: '500',
    letterSpacing: 0.5,
  },
  infoRow: {
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E5E5EA',
  },
  field: {
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E5E5EA',
  },
  label: {
    fontSize: 13,
    color: '#8E8E93',
    marginBottom: 4,
  },
  value: {
    fontSize: 16,
    color: '#000000',
  },
  input: {
    fontSize: 16,
    color: '#000000',
    padding: 0,
  },
  multilineInput: {
    minHeight: 60,
    textAlignVertical: 'top',
  },
  saveButton: {
    marginTop: 16,
    marginHorizontal: 16,
    height: 44,
    borderRadius: 10,
    backgroundColor: '#007AFF',
    justifyContent: 'center',
    alignItems: 'center',
  },
  saveButtonDisabled: {
    opacity: 0.6,
  },
  saveButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  agentRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E5E5EA',
  },
  agentInfo: {
    flex: 1,
    marginRight: 12,
  },
  agentName: {
    fontSize: 16,
    color: '#000000',
    fontWeight: '500',
  },
  agentDescription: {
    fontSize: 13,
    color: '#8E8E93',
    marginTop: 2,
  },
  agentNotReady: {
    fontSize: 12,
    color: '#FF9500',
    marginTop: 2,
    fontStyle: 'italic',
  },
  deleteButton: {
    marginTop: 16,
    marginHorizontal: 16,
    marginBottom: 32,
    height: 48,
    borderRadius: 10,
    backgroundColor: '#FF3B30',
    justifyContent: 'center',
    alignItems: 'center',
  },
  deleteButtonDisabled: {
    opacity: 0.6,
  },
  deleteButtonText: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '600',
  },
});
