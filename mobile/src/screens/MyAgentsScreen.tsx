import React, {useCallback, useEffect, useState} from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  StyleSheet,
  Switch,
  Text,
  View,
} from 'react-native';
import type {AvailableAgent} from '../types';
import {disableMyAgent, enableMyAgent, getAvailableAgents} from '../services/api';

export function MyAgentsScreen() {
  const [agents, setAgents] = useState<AvailableAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);

  const loadAgents = useCallback(async () => {
    try {
      const result = await getAvailableAgents();
      setAgents(result.agents);
    } catch (err) {
      Alert.alert('Error', err instanceof Error ? err.message : 'Failed to load agents');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  const handleToggle = async (agent: AvailableAgent) => {
    setToggling(agent.agent_type);
    try {
      if (agent.enabled) {
        await disableMyAgent(agent.agent_type);
      } else {
        await enableMyAgent(agent.agent_type);
      }
      // Optimistic update
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

  const renderAgent = ({item}: {item: AvailableAgent}) => (
    <View style={styles.row}>
      <View style={styles.rowContent}>
        <View style={styles.rowHeader}>
          <Text style={styles.rowName}>{item.name}</Text>
          {item.is_builtin && (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>Built-in</Text>
            </View>
          )}
        </View>
        <Text style={styles.rowDescription} numberOfLines={2}>
          {item.description}
        </Text>
      </View>
      <Switch
        value={item.enabled}
        onValueChange={() => handleToggle(item)}
        disabled={toggling === item.agent_type}
        trackColor={{false: '#E5E5EA', true: '#34C759'}}
        thumbColor="#FFFFFF"
      />
    </View>
  );

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
  row: {
    backgroundColor: '#FFFFFF',
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    marginHorizontal: 16,
    marginTop: 12,
    borderRadius: 10,
  },
  rowContent: {
    flex: 1,
    marginRight: 12,
  },
  rowHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
  },
  rowName: {
    fontSize: 17,
    fontWeight: '600',
    color: '#000000',
    marginRight: 8,
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
  rowDescription: {
    fontSize: 14,
    color: '#3C3C43',
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
