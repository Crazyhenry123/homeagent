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
import {SectionHeader, ToggleRow, PrimaryButton} from '../components/ui';
import {colors} from '../theme';

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
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  if (currentUserRole && currentUserRole !== 'admin' && currentUserRole !== 'owner') {
    return (
      <View style={[styles.container, styles.centered]}>
        <Text style={{fontSize: 16, color: colors.textTertiary}}>Access denied. Admin role required.</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container}>
      <SectionHeader title="MEMBER INFO" />

      <View style={styles.infoRow}>
        <Text style={styles.label}>Name</Text>
        <Text style={styles.value}>{profile?.display_name}</Text>
      </View>
      <View style={styles.infoRow}>
        <Text style={styles.label}>Role</Text>
        <Text style={styles.value}>{profile?.role}</Text>
      </View>

      <SectionHeader title="PROFILE" />

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

      <View style={{marginTop: 16}}>
        <PrimaryButton
          title={saving ? 'Saving...' : 'Save Profile'}
          onPress={handleSaveProfile}
          disabled={saving}
          loading={saving}
        />
      </View>

      <SectionHeader title="AI AGENTS" />

      {Object.entries(agentTypes).map(([type, info]) => (
        <ToggleRow
          key={type}
          label={info.name}
          sublabel={info.description}
          value={isAgentEnabled(type)}
          onValueChange={value => handleToggleAgent(type, value)}
        />
      ))}

      {userId !== session.user?.userId && (
        <>
          <SectionHeader title="DANGER ZONE" />
          <View style={{marginTop: 16, marginBottom: 32}}>
            <PrimaryButton
              title={deleting ? 'Removing...' : 'Remove Member'}
              variant="destructive"
              onPress={handleDeleteMember}
              disabled={deleting}
              loading={deleting}
            />
          </View>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  centered: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  infoRow: {
    backgroundColor: colors.surface,
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separator,
  },
  field: {
    backgroundColor: colors.surface,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separator,
  },
  label: {
    fontSize: 13,
    color: colors.textTertiary,
    marginBottom: 4,
  },
  value: {
    fontSize: 16,
    color: colors.textPrimary,
  },
  input: {
    fontSize: 16,
    color: colors.textPrimary,
    padding: 0,
  },
  multilineInput: {
    minHeight: 60,
    textAlignVertical: 'top',
  },
});
