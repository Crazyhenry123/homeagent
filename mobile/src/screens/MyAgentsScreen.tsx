import React, {useCallback, useEffect, useState} from 'react';
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
import type {AvailableAgent, PermissionGrant} from '../types';
import {
  disableMyAgent,
  enableMyAgent,
  getAvailableAgents,
  getMyPermissions,
  grantPermission,
  revokePermission,
} from '../services/api';

const PERMISSION_LABELS: Record<string, string> = {
  email_access: 'Email Account Access',
  calendar_access: 'Calendar Access',
  health_data: 'Health Data Access',
  medical_records: 'Medical Records Access',
};

export function MyAgentsScreen() {
  const [agents, setAgents] = useState<AvailableAgent[]>([]);
  const [permissions, setPermissions] = useState<PermissionGrant[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [agentResult, permResult] = await Promise.all([
        getAvailableAgents(),
        getMyPermissions(),
      ]);
      setAgents(agentResult.agents);
      setPermissions(permResult.permissions);
    } catch (err) {
      Alert.alert('Error', err instanceof Error ? err.message : 'Failed to load agents');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const grantedPermissionTypes = new Set(
    permissions
      .filter(p => p.status === 'active')
      .map(p => p.permission_type),
  );

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
      setAgents(prev =>
        prev.map(a =>
          a.agent_type === agent.agent_type
            ? {...a, enabled: !a.enabled}
            : a,
        ),
      );
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
        setPermissions(prev =>
          prev.map(p =>
            p.permission_type === permissionType
              ? {...p, status: 'revoked' as const}
              : p,
          ),
        );
      } else {
        const defaultConfigs: Record<string, Record<string, unknown>> = {
          email_access: {email_address: '', provider: 'gmail'},
          calendar_access: {calendar_id: 'default', provider: 'gmail'},
          health_data: {consent_given: true, data_sources: ['healthkit']},
          medical_records: {folder_path: '/health-documents', s3_prefix: 'health-documents/'},
        };
        const result = await grantPermission(
          permissionType,
          defaultConfigs[permissionType] ?? {},
        );
        setPermissions(prev => {
          const filtered = prev.filter(p => p.permission_type !== permissionType);
          return [...filtered, result];
        });
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
            trackColor={{false: '#E5E5EA', true: '#34C759'}}
            thumbColor="#FFFFFF"
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
                    trackColor={{false: '#E5E5EA', true: '#34C759'}}
                    thumbColor="#FFFFFF"
                  />
                </View>
              );
            })}
          </View>
        )}
      </View>
    );
  };

  if (loading) {
    return (
      <View style={[styles.container, styles.centered]}>
        <ActivityIndicator size="large" color="#007AFF" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={agents}
        keyExtractor={item => item.template_id}
        renderItem={renderAgent}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyTitle}>No Agents Available</Text>
            <Text style={styles.emptyText}>
              Your admin hasn't made any agents available to you yet.
            </Text>
          </View>
        }
      />
    </View>
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
  agentContainer: {
    marginHorizontal: 16,
    marginTop: 12,
    borderRadius: 10,
    backgroundColor: '#FFFFFF',
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
    color: '#000000',
  },
  badge: {
    backgroundColor: '#E5E5EA',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 8,
  },
  badgeText: {
    fontSize: 12,
    color: '#8E8E93',
    fontWeight: '500',
  },
  setupBadge: {
    backgroundColor: '#FFE0B2',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 8,
  },
  setupBadgeText: {
    fontSize: 12,
    color: '#E65100',
    fontWeight: '500',
  },
  rowDescription: {
    fontSize: 14,
    color: '#3C3C43',
  },
  permissionSummary: {
    fontSize: 12,
    color: '#8E8E93',
    marginTop: 4,
  },
  permissionsPanel: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: '#E5E5EA',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#FAFAFA',
  },
  permissionsTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#3C3C43',
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
    color: '#000000',
  },
  permissionStatus: {
    fontSize: 12,
    color: '#8E8E93',
    marginTop: 2,
  },
  emptyContainer: {
    alignItems: 'center',
    marginTop: 48,
    paddingHorizontal: 32,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#000000',
    marginBottom: 8,
  },
  emptyText: {
    fontSize: 15,
    color: '#8E8E93',
    textAlign: 'center',
  },
});
