import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  StyleSheet,
  Switch,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import type {RootStackParamList} from '../navigation/AppNavigator';
import type {AvailableAgent} from '../types';
import {useSession} from '../store';
import {
  disableMyAgent,
  enableMyAgent,
  grantPermission,
  revokePermission,
} from '../services/api';
import {EmptyState} from '../components/ui';
import {colors} from '../theme';

const PERMISSION_LABELS: Record<string, string> = {
  email_access: 'Email Account Access',
  calendar_access: 'Calendar Access',
  health_data: 'Health Data Access',
  medical_records: 'Medical Records Access',
};

type Props = NativeStackScreenProps<RootStackParamList, 'MyAgents'>;

export function MyAgentsScreen({navigation}: Props) {
  const {session, actions} = useSession();
  const [toggling, setToggling] = useState<string | null>(null);
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  // Local copy of permissions for optimistic UI updates on toggle
  const [localPermissionOverrides, setLocalPermissionOverrides] = useState<
    Record<string, 'active' | 'revoked'>
  >({});

  // Auto-refresh agents when screen comes into focus
  useEffect(() => {
    const unsubscribe = navigation.addListener('focus', () => {
      actions.refreshAgents().catch(() => {});
    });
    return unsubscribe;
  }, [navigation, actions]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await actions.refreshAgents();
    } catch {
      // ignore
    } finally {
      setRefreshing(false);
    }
  }, [actions]);

  const allAgents = session.agents.available;
  const myConfigs = session.agents.myConfigs;
  const permissions = session.permissions;

  // Only show agents that admin has authorized (have an AgentConfig record)
  const authorizedTypes = useMemo(
    () => new Set(myConfigs.map(c => c.agent_type)),
    [myConfigs],
  );
  const agents = useMemo(
    () => allAgents.filter(a => authorizedTypes.has(a.agent_type)),
    [allAgents, authorizedTypes],
  );

  const grantedPermissionTypes = useMemo(() => {
    const set = new Set<string>();
    for (const p of permissions) {
      const override = localPermissionOverrides[p.permission_type];
      const status = override ?? p.status;
      if (status === 'active') {
        set.add(p.permission_type);
      }
    }
    // Also include permissions that were freshly granted (not in original list)
    for (const [type, status] of Object.entries(localPermissionOverrides)) {
      if (status === 'active') set.add(type);
    }
    return set;
  }, [permissions, localPermissionOverrides]);

  const getMissingPermissions = (agent: AvailableAgent): string[] => {
    const required = agent.required_permissions ?? [];
    return required.filter(p => !grantedPermissionTypes.has(p));
  };

  const handleToggle = async (agent: AvailableAgent) => {
    setToggling(agent.agent_type);
    try {
      if (agent.enabled) {
        await disableMyAgent(agent.agent_type);
      } else {
        await enableMyAgent(agent.agent_type);
      }
      await actions.refreshAgents();
    } catch (err) {
      Alert.alert('Error', err instanceof Error ? err.message : 'Failed to update');
    } finally {
      setToggling(null);
    }
  };

  const handlePermissionToggle = async (
    permissionType: string,
    currentlyGranted: boolean,
  ) => {
    try {
      if (currentlyGranted) {
        await revokePermission(permissionType);
        setLocalPermissionOverrides(prev => ({...prev, [permissionType]: 'revoked'}));
        await actions.refreshPermissions();
        setLocalPermissionOverrides({});
      } else {
        if (permissionType === 'email_access') {
          Alert.alert(
            'Setup Required',
            'Please configure your email in Agent Setup to enable email access.',
            [
              {text: 'Go to Setup', onPress: () => navigation.navigate('AgentSetup')},
              {text: 'Cancel'},
            ],
          );
          return;
        }
        const defaultConfigs: Record<string, Record<string, unknown>> = {
          calendar_access: {calendar_id: 'default', provider: 'gmail'},
          health_data: {consent_given: true, data_sources: ['healthkit']},
          medical_records: {folder_path: '/health-documents', s3_prefix: 'health-documents/'},
        };
        await grantPermission(
          permissionType,
          defaultConfigs[permissionType] ?? {},
        );
        setLocalPermissionOverrides(prev => ({...prev, [permissionType]: 'active'}));
        await actions.refreshPermissions();
        setLocalPermissionOverrides({});
      }
    } catch (err) {
      Alert.alert('Error', err instanceof Error ? err.message : 'Failed to update permission');
    }
  };

  const handleAgentPress = (agentType: string) => {
    setExpandedAgent(prev => (prev === agentType ? null : agentType));
  };

  const renderAgent = ({item}: {item: AvailableAgent}) => {
    const missing = getMissingPermissions(item);
    const hasRequired = (item.required_permissions ?? []).length > 0;
    const isExpanded = expandedAgent === item.agent_type;

    return (
      <View style={styles.agentContainer}>
        <TouchableOpacity
          style={styles.row}
          onPress={() => handleAgentPress(item.agent_type)}
          activeOpacity={0.7}>
          <View style={styles.rowContent}>
            <View style={styles.rowHeader}>
              <Text style={styles.rowName}>{item.name}</Text>
              {item.is_builtin && (
                <View style={styles.badge}>
                  <Text style={styles.badgeText}>Built-in</Text>
                </View>
              )}
              {missing.length > 0 && item.enabled && (
                <View style={styles.setupBadge}>
                  <Text style={styles.setupBadgeText}>Setup Required</Text>
                </View>
              )}
            </View>
            <Text style={styles.rowDescription} numberOfLines={2}>
              {item.description}
            </Text>
            {hasRequired && !isExpanded && (
              <Text style={styles.permissionSummary}>
                {missing.length === 0
                  ? 'All permissions granted'
                  : `${missing.length} permission${missing.length > 1 ? 's' : ''} needed`}
              </Text>
            )}
          </View>
          <Switch
            value={item.enabled}
            onValueChange={() => handleToggle(item)}
            disabled={toggling === item.agent_type}
            trackColor={{false: colors.separator, true: colors.success}}
            thumbColor={colors.surface}
          />
        </TouchableOpacity>

        {isExpanded && hasRequired && (
          <View style={styles.permissionsPanel}>
            <Text style={styles.permissionsTitle}>Required Permissions</Text>
            {(item.required_permissions ?? []).map(perm => {
              const isGranted = grantedPermissionTypes.has(perm);
              return (
                <View key={perm} style={styles.permissionRow}>
                  <View style={styles.permissionContent}>
                    <Text style={styles.permissionLabel}>
                      {PERMISSION_LABELS[perm] ?? perm}
                    </Text>
                    <Text style={styles.permissionStatus}>
                      {isGranted ? 'Granted' : 'Not granted'}
                    </Text>
                  </View>
                  <Switch
                    value={isGranted}
                    onValueChange={() =>
                      handlePermissionToggle(perm, isGranted)
                    }
                    trackColor={{false: colors.separator, true: colors.success}}
                    thumbColor={colors.surface}
                  />
                </View>
              );
            })}
          </View>
        )}
      </View>
    );
  };

  if (session.status === 'loading') {
    return (
      <View style={[styles.container, styles.centered]}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={agents}
        keyExtractor={item => item.template_id}
        renderItem={renderAgent}
        refreshing={refreshing}
        onRefresh={handleRefresh}
        ListEmptyComponent={
          <EmptyState
            icon="hardware-chip-outline"
            title="No Agents Authorized"
            subtitle="Your family admin hasn't authorized any agents for you yet. Ask them to enable agents in your member settings."
          />
        }
      />
    </View>
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
  agentContainer: {
    marginHorizontal: 16,
    marginTop: 12,
    borderRadius: 10,
    backgroundColor: colors.surface,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
  },
  rowContent: {
    flex: 1,
    marginRight: 12,
  },
  rowHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
    flexWrap: 'wrap',
    gap: 6,
  },
  rowName: {
    fontSize: 17,
    fontWeight: '600',
    color: colors.textPrimary,
  },
  badge: {
    backgroundColor: colors.badgeBackground,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 8,
  },
  badgeText: {
    fontSize: 12,
    color: colors.badgeText,
    fontWeight: '500',
  },
  setupBadge: {
    backgroundColor: colors.setupBadgeBackground,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 8,
  },
  setupBadgeText: {
    fontSize: 12,
    color: colors.setupBadgeText,
    fontWeight: '500',
  },
  rowDescription: {
    fontSize: 14,
    color: colors.textSecondary,
  },
  permissionSummary: {
    fontSize: 12,
    color: colors.textTertiary,
    marginTop: 4,
  },
  permissionsPanel: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.separator,
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: colors.surfaceSecondary,
  },
  permissionsTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.textSecondary,
    marginBottom: 8,
  },
  permissionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
  },
  permissionContent: {
    flex: 1,
    marginRight: 12,
  },
  permissionLabel: {
    fontSize: 15,
    fontWeight: '500',
    color: colors.textPrimary,
  },
  permissionStatus: {
    fontSize: 12,
    color: colors.textTertiary,
    marginTop: 2,
  },
});
