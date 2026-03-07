import React, {useCallback, useEffect, useState} from 'react';
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
import Constants from 'expo-constants';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import {useSession} from '../store';
import {getMemorySharingConfig, updateMemorySharingConfig} from '../services/api';
import type {MemorySharingConfig} from '../types';
import type {RootStackParamList} from '../navigation/AppNavigator';
import {colors} from '../theme';

type Props = NativeStackScreenProps<RootStackParamList, 'Settings'>;

export function SettingsScreen({navigation}: Props) {
  const {session, actions, isOwnerOrAdmin} = useSession();

  const name = session.user?.name ?? '';
  const userId = session.user?.userId ?? '';
  const role = session.user?.role ?? '';

  const handleLogout = () => {
    Alert.alert('Log Out', 'Are you sure you want to log out?', [
      {text: 'Cancel', style: 'cancel'},
      {
        text: 'Log Out',
        style: 'destructive',
        onPress: async () => {
          await actions.logout();
          navigation.reset({index: 0, routes: [{name: 'Register'}]});
        },
      },
    ]);
  };

  const appVersion = Constants.expoConfig?.version ?? '0.1.0';

  // Memory sharing state
  const [sharingConfig, setSharingConfig] = useState<MemorySharingConfig | null>(null);
  const [sharingLoading, setSharingLoading] = useState(true);
  const [savingSharing, setSavingSharing] = useState(false);

  useEffect(() => {
    getMemorySharingConfig()
      .then(setSharingConfig)
      .catch(() => {})
      .finally(() => setSharingLoading(false));
  }, []);

  type BooleanSharingField = 'share_profile' | 'share_interests' | 'share_health_notes' | 'share_conversation_insights';

  const handleSharingToggle = useCallback(
    async (field: BooleanSharingField, value: boolean) => {
      if (!sharingConfig) return;
      const updated = {...sharingConfig, [field]: value};
      setSharingConfig(updated);
      setSavingSharing(true);
      try {
        const result = await updateMemorySharingConfig({[field]: value});
        setSharingConfig(result);
      } catch {
        setSharingConfig(sharingConfig); // revert
        Alert.alert('Error', 'Failed to update sharing settings.');
      } finally {
        setSavingSharing(false);
      }
    },
    [sharingConfig],
  );

  const handleSharingLevelChange = useCallback(async () => {
    if (!sharingConfig) return;
    const levels: Array<MemorySharingConfig['sharing_level']> = ['none', 'basic', 'full'];
    const currentIdx = levels.indexOf(sharingConfig.sharing_level);
    const nextLevel = levels[(currentIdx + 1) % levels.length];
    const updated = {...sharingConfig, sharing_level: nextLevel};
    setSharingConfig(updated);
    setSavingSharing(true);
    try {
      const result = await updateMemorySharingConfig({sharing_level: nextLevel});
      setSharingConfig(result);
    } catch {
      setSharingConfig(sharingConfig);
      Alert.alert('Error', 'Failed to update sharing level.');
    } finally {
      setSavingSharing(false);
    }
  }, [sharingConfig]);

  const handleCustomInfoSave = useCallback(
    async (text: string) => {
      if (!sharingConfig) return;
      setSavingSharing(true);
      try {
        const result = await updateMemorySharingConfig({custom_shared_info: text});
        setSharingConfig(result);
      } catch {
        Alert.alert('Error', 'Failed to save custom info.');
      } finally {
        setSavingSharing(false);
      }
    },
    [sharingConfig],
  );

  return (
    <ScrollView style={styles.container}>
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionHeaderText}>ACCOUNT</Text>
      </View>
      <View style={styles.section}>
        <Text style={styles.label}>Name</Text>
        <Text style={styles.value}>{name}</Text>
      </View>
      <View style={styles.section}>
        <Text style={styles.label}>User ID</Text>
        <Text style={styles.value}>{userId}</Text>
      </View>
      <View style={styles.section}>
        <Text style={styles.label}>Role</Text>
        <Text style={styles.value}>{role}</Text>
      </View>

      <View style={styles.sectionHeader}>
        <Text style={styles.sectionHeaderText}>PROFILE</Text>
      </View>
      <TouchableOpacity
        style={styles.actionRow}
        onPress={() => navigation.navigate('Profile')}>
        <Text style={styles.actionText}>Edit My Profile</Text>
      </TouchableOpacity>
      <TouchableOpacity
        style={styles.actionRow}
        onPress={() => navigation.navigate('MyAgents')}>
        <Text style={styles.actionText}>My Agents</Text>
      </TouchableOpacity>
      <TouchableOpacity
        style={styles.actionRow}
        onPress={() => navigation.navigate('StorageSettings')}>
        <Text style={styles.actionText}>Data Storage</Text>
      </TouchableOpacity>

      {isOwnerOrAdmin && (
        <>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionHeaderText}>ADMIN</Text>
          </View>
          <TouchableOpacity
            style={styles.adminPanelButton}
            onPress={() => navigation.navigate('AdminPanel')}>
            <Text style={styles.adminPanelButtonText}>Open Admin Panel</Text>
          </TouchableOpacity>
        </>
      )}

      <View style={styles.sectionHeader}>
        <Text style={styles.sectionHeaderText}>MEMORY &amp; SHARING</Text>
        {savingSharing && <ActivityIndicator size="small" style={{marginLeft: 8}} />}
      </View>
      {sharingLoading ? (
        <View style={styles.section}>
          <ActivityIndicator size="small" />
        </View>
      ) : sharingConfig ? (
        <>
          <TouchableOpacity style={styles.actionRow} onPress={handleSharingLevelChange}>
            <Text style={styles.label}>Sharing Level</Text>
            <Text style={styles.sharingLevelValue}>
              {sharingConfig.sharing_level.toUpperCase()}
            </Text>
          </TouchableOpacity>
          <View style={styles.toggleRow}>
            <Text style={styles.toggleLabel}>Share Profile</Text>
            <Switch
              value={sharingConfig.share_profile}
              onValueChange={v => handleSharingToggle('share_profile', v)}
            />
          </View>
          <View style={styles.toggleRow}>
            <Text style={styles.toggleLabel}>Share Interests</Text>
            <Switch
              value={sharingConfig.share_interests}
              onValueChange={v => handleSharingToggle('share_interests', v)}
            />
          </View>
          <View style={styles.toggleRow}>
            <Text style={styles.toggleLabel}>Share Health Notes</Text>
            <Switch
              value={sharingConfig.share_health_notes}
              onValueChange={v => handleSharingToggle('share_health_notes', v)}
            />
          </View>
          <View style={styles.toggleRow}>
            <Text style={styles.toggleLabel}>Share Conversation Insights</Text>
            <Switch
              value={sharingConfig.share_conversation_insights}
              onValueChange={v =>
                handleSharingToggle('share_conversation_insights', v)
              }
            />
          </View>
          <View style={styles.section}>
            <Text style={styles.label}>Custom Shared Info</Text>
            <TextInput
              style={styles.textInput}
              multiline
              placeholder="Add anything you'd like to share with family agents..."
              placeholderTextColor={colors.textTertiary}
              defaultValue={sharingConfig.custom_shared_info}
              onEndEditing={e => handleCustomInfoSave(e.nativeEvent.text)}
            />
          </View>
        </>
      ) : null}

      <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
        <Text style={styles.logoutText}>Log Out</Text>
      </TouchableOpacity>

      <Text style={styles.versionText}>HomeAgent v{appVersion}</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  section: {
    backgroundColor: colors.surface,
    paddingHorizontal: 16,
    paddingVertical: 14,
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
  actionRow: {
    backgroundColor: colors.surface,
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separator,
  },
  actionText: {
    fontSize: 16,
    color: colors.primary,
  },
  sharingLevelValue: {
    fontSize: 16,
    color: colors.primary,
    fontWeight: '600',
  },
  textInput: {
    marginTop: 8,
    fontSize: 15,
    color: colors.textPrimary,
    minHeight: 60,
    textAlignVertical: 'top',
  },
  sectionHeader: {
    paddingHorizontal: 16,
    paddingTop: 24,
    paddingBottom: 8,
  },
  sectionHeaderText: {
    fontSize: 13,
    color: colors.textTertiary,
    fontWeight: '500' as const,
    letterSpacing: 0.5,
  },
  adminPanelButton: {
    marginTop: 8,
    marginHorizontal: 16,
    height: 48,
    borderRadius: 10,
    backgroundColor: colors.primary,
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
  },
  adminPanelButtonText: {
    color: colors.surface,
    fontSize: 17,
    fontWeight: '600' as const,
  },
  logoutButton: {
    marginTop: 32,
    marginHorizontal: 16,
    height: 48,
    borderRadius: 10,
    backgroundColor: colors.destructive,
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
  },
  logoutText: {
    color: colors.surface,
    fontSize: 17,
    fontWeight: '600' as const,
  },
  toggleRow: {
    backgroundColor: colors.surface,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separator,
    flexDirection: 'row' as const,
    justifyContent: 'space-between' as const,
    alignItems: 'center' as const,
  },
  toggleLabel: {
    fontSize: 16,
    color: colors.textPrimary,
  },
  versionText: {
    textAlign: 'center' as const,
    color: colors.textQuaternary,
    fontSize: 13,
    marginTop: 24,
    marginBottom: 32,
  },
});
