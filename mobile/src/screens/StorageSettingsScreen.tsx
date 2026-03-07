import React, {useCallback, useEffect, useState} from 'react';
import {
  ActivityIndicator,
  Alert,
  Linking,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import type {RootStackParamList} from '../navigation/AppNavigator';
import {useSession} from '../store';
import type {StorageProviderInfo, StorageProviderType} from '../types';
import {
  connectStorageProvider,
  disconnectStorageProvider,
  getStorageProviders,
  testStorageConnection,
} from '../services/api';

type Props = NativeStackScreenProps<RootStackParamList, 'StorageSettings'>;

// Provider icon/color mapping
const PROVIDER_COLORS: Record<StorageProviderType, string> = {
  local: '#34C759',
  google_drive: '#4285F4',
  onedrive: '#0078D4',
  dropbox: '#0061FF',
  box: '#0061D5',
};

const PROVIDER_ICONS: Record<StorageProviderType, string> = {
  local: '\u2601\uFE0F',
  google_drive: '\uD83D\uDCC1',
  onedrive: '\uD83D\uDCC2',
  dropbox: '\uD83D\uDCA7',
  box: '\uD83D\uDCE6',
};

export function StorageSettingsScreen({navigation}: Props) {
  const {session, actions} = useSession();
  const currentProvider = session.storage?.provider ?? 'local';
  const currentStatus = session.storage?.status ?? 'active';

  const [providers, setProviders] = useState<StorageProviderInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{reachable: boolean; latency_ms: number} | null>(null);

  useEffect(() => {
    getStorageProviders()
      .then(res => setProviders(res.providers))
      .catch(() => Alert.alert('Error', 'Failed to load storage providers'))
      .finally(() => setLoading(false));
  }, []);

  // Listen for deep link callbacks from OAuth
  useEffect(() => {
    const handler = (event: {url: string}) => {
      if (event.url.startsWith('homeagent://storage-connected')) {
        try {
          // Parse query params manually since URL() may not handle custom schemes
          const queryString = event.url.split('?')[1] ?? '';
          const params = new URLSearchParams(queryString);
          const status = params.get('status');
          if (status === 'success') {
            actions.refreshStorage();
            Alert.alert('Connected', 'Storage provider connected successfully.');
          } else {
            Alert.alert('Error', params.get('message') ?? 'Failed to connect provider.');
          }
        } catch {
          Alert.alert('Error', 'Failed to process storage callback.');
        }
        setConnecting(null);
      }
    };
    const sub = Linking.addEventListener('url', handler);
    return () => sub.remove();
  }, [actions]);

  // Clear connecting state when screen regains focus (e.g., returning from OAuth browser)
  useEffect(() => {
    const unsubscribe = navigation.addListener('focus', () => {
      // Give deep link a moment to fire first
      const timer = setTimeout(() => setConnecting(null), 1500);
      return () => clearTimeout(timer);
    });
    return unsubscribe;
  }, [navigation]);

  const handleConnect = useCallback(async (providerId: string) => {
    setConnecting(providerId);
    try {
      const {auth_url} = await connectStorageProvider(providerId);
      if (!auth_url.startsWith('https://')) {
        throw new Error('Invalid auth URL received from server');
      }
      await Linking.openURL(auth_url);
    } catch (err) {
      setConnecting(null);
      Alert.alert('Error', err instanceof Error ? err.message : 'Failed to start connection');
    }
  }, []);

  const handleDisconnect = useCallback(async () => {
    Alert.alert(
      'Disconnect Storage',
      'This will revert to default storage. Your data in the cloud provider will NOT be deleted. You may need to migrate data manually.',
      [
        {text: 'Cancel', style: 'cancel'},
        {
          text: 'Disconnect',
          style: 'destructive',
          onPress: async () => {
            try {
              await disconnectStorageProvider();
              await actions.refreshStorage();
            } catch {
              Alert.alert('Error', 'Failed to disconnect provider.');
            }
          },
        },
      ],
    );
  }, [actions]);

  const handleTest = useCallback(async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testStorageConnection();
      setTestResult(result);
    } catch {
      setTestResult({reachable: false, latency_ms: 0});
    } finally {
      setTesting(false);
    }
  }, []);

  // Status indicator
  const statusColor = currentStatus === 'active' ? '#34C759' : currentStatus === 'migrating' ? '#FF9500' : '#FF3B30';
  const statusLabel = currentStatus === 'active' ? 'Connected' : currentStatus === 'migrating' ? 'Migrating...' : 'Error';

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  return (
    <ScrollView style={styles.container}>
      {/* Current Provider Section */}
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionHeaderText}>CURRENT STORAGE</Text>
      </View>
      <View style={styles.currentCard}>
        <View style={styles.currentRow}>
          <Text style={styles.currentIcon}>
            {PROVIDER_ICONS[currentProvider]}
          </Text>
          <View style={styles.currentInfo}>
            <Text style={styles.currentName}>
              {providers.find(p => p.id === currentProvider)?.name ?? 'Default (Secure Cloud)'}
            </Text>
            <View style={styles.statusRow}>
              <View style={[styles.statusDot, {backgroundColor: statusColor}]} />
              <Text style={styles.statusText}>{statusLabel}</Text>
            </View>
          </View>
        </View>
        {currentProvider !== 'local' && (
          <View style={styles.currentActions}>
            <TouchableOpacity
              style={styles.testButton}
              onPress={handleTest}
              disabled={testing}>
              <Text style={styles.testButtonText}>
                {testing ? 'Testing...' : 'Test Connection'}
              </Text>
            </TouchableOpacity>
            {testResult && (
              <Text style={[styles.testResult, {color: testResult.reachable ? '#34C759' : '#FF3B30'}]}>
                {testResult.reachable ? `Connected (${testResult.latency_ms}ms)` : 'Unreachable'}
              </Text>
            )}
          </View>
        )}
      </View>

      {/* Privacy Info */}
      <View style={styles.infoBox}>
        <Text style={styles.infoTitle}>Your Data, Your Choice</Text>
        <Text style={styles.infoText}>
          Health records, observations, and documents created by your agents are stored in your chosen provider.
          Chat history and account data always remain in HomeAgent's secure cloud.
        </Text>
      </View>

      {/* Available Providers */}
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionHeaderText}>AVAILABLE PROVIDERS</Text>
      </View>
      {providers.map(provider => {
        const isActive = provider.id === currentProvider;
        const isConnecting = connecting === provider.id;
        const isUnavailable = provider.requires_oauth && !provider.oauth_configured;

        return (
          <TouchableOpacity
            key={provider.id}
            style={[styles.providerRow, isActive && styles.providerRowActive, isUnavailable && styles.providerRowDisabled]}
            onPress={() => {
              if (isActive && provider.id !== 'local') {
                handleDisconnect();
              } else if (!isActive) {
                if (provider.requires_oauth) {
                  handleConnect(provider.id);
                } else {
                  // Local — just disconnect current
                  if (currentProvider !== 'local') {
                    handleDisconnect();
                  }
                }
              }
            }}
            disabled={isUnavailable || isConnecting || currentStatus === 'migrating'}>
            <View style={styles.providerInfo}>
              <Text style={[styles.providerIcon, isUnavailable && {opacity: 0.4}]}>{PROVIDER_ICONS[provider.id]}</Text>
              <View style={styles.providerText}>
                <Text style={[styles.providerName, isUnavailable && {color: '#C7C7CC'}]}>{provider.name}</Text>
                <Text style={styles.providerDescription}>
                  {isUnavailable ? 'Not configured on server' : provider.description}
                </Text>
              </View>
            </View>
            {isActive ? (
              <View style={[styles.badge, {backgroundColor: PROVIDER_COLORS[provider.id]}]}>
                <Text style={styles.badgeText}>Active</Text>
              </View>
            ) : isConnecting ? (
              <ActivityIndicator size="small" />
            ) : isUnavailable ? (
              <Text style={styles.unavailableText}>Unavailable</Text>
            ) : (
              <Text style={styles.connectText}>
                {provider.requires_oauth ? 'Connect' : 'Select'}
              </Text>
            )}
          </TouchableOpacity>
        );
      })}

      {/* Data Awareness Note */}
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionHeaderText}>WHAT'S STORED WHERE</Text>
      </View>
      <View style={styles.dataCard}>
        <View style={styles.dataRow}>
          <Text style={styles.dataIcon}>{PROVIDER_ICONS[currentProvider]}</Text>
          <View style={styles.dataInfo}>
            <Text style={styles.dataLabel}>Your Chosen Storage</Text>
            <Text style={styles.dataItems}>Health records, observations, medical documents</Text>
          </View>
        </View>
        <View style={styles.dataDivider} />
        <View style={styles.dataRow}>
          <Text style={styles.dataIcon}>{'\uD83D\uDD12'}</Text>
          <View style={styles.dataInfo}>
            <Text style={styles.dataLabel}>Always in HomeAgent Cloud</Text>
            <Text style={styles.dataItems}>Chat history, account info, family data, agent configs</Text>
          </View>
        </View>
      </View>

      <View style={{height: 40}} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: '#F2F2F7'},
  centered: {flex: 1, justifyContent: 'center', alignItems: 'center'},
  sectionHeader: {paddingHorizontal: 16, paddingTop: 24, paddingBottom: 8},
  sectionHeaderText: {fontSize: 13, color: '#8E8E93', fontWeight: '500', letterSpacing: 0.5},
  currentCard: {
    backgroundColor: '#FFFFFF',
    marginHorizontal: 16,
    borderRadius: 12,
    padding: 16,
  },
  currentRow: {flexDirection: 'row', alignItems: 'center'},
  currentIcon: {fontSize: 32, marginRight: 12},
  currentInfo: {flex: 1},
  currentName: {fontSize: 18, fontWeight: '600', color: '#000'},
  statusRow: {flexDirection: 'row', alignItems: 'center', marginTop: 4},
  statusDot: {width: 8, height: 8, borderRadius: 4, marginRight: 6},
  statusText: {fontSize: 14, color: '#8E8E93'},
  currentActions: {marginTop: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#E5E5EA', paddingTop: 12},
  testButton: {
    backgroundColor: '#F2F2F7',
    borderRadius: 8,
    paddingVertical: 8,
    paddingHorizontal: 16,
    alignSelf: 'flex-start',
  },
  testButtonText: {fontSize: 14, color: '#007AFF', fontWeight: '500'},
  testResult: {fontSize: 13, marginTop: 8},
  infoBox: {
    backgroundColor: '#EBF5FF',
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 12,
    padding: 16,
  },
  infoTitle: {fontSize: 15, fontWeight: '600', color: '#007AFF', marginBottom: 4},
  infoText: {fontSize: 13, color: '#3C3C43', lineHeight: 18},
  providerRow: {
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E5E5EA',
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  providerRowActive: {backgroundColor: '#F0FFF4'},
  providerInfo: {flexDirection: 'row', alignItems: 'center', flex: 1},
  providerIcon: {fontSize: 24, marginRight: 12},
  providerText: {flex: 1},
  providerName: {fontSize: 16, fontWeight: '500', color: '#000'},
  providerDescription: {fontSize: 13, color: '#8E8E93', marginTop: 2},
  badge: {borderRadius: 12, paddingHorizontal: 10, paddingVertical: 4},
  badgeText: {fontSize: 12, fontWeight: '600', color: '#FFFFFF'},
  connectText: {fontSize: 15, color: '#007AFF', fontWeight: '500'},
  unavailableText: {fontSize: 13, color: '#C7C7CC', fontWeight: '500'},
  providerRowDisabled: {opacity: 0.7},
  dataCard: {
    backgroundColor: '#FFFFFF',
    marginHorizontal: 16,
    borderRadius: 12,
    padding: 16,
  },
  dataRow: {flexDirection: 'row', alignItems: 'flex-start'},
  dataIcon: {fontSize: 20, marginRight: 12, marginTop: 2},
  dataInfo: {flex: 1},
  dataLabel: {fontSize: 15, fontWeight: '600', color: '#000', marginBottom: 2},
  dataItems: {fontSize: 13, color: '#8E8E93', lineHeight: 18},
  dataDivider: {height: StyleSheet.hairlineWidth, backgroundColor: '#E5E5EA', marginVertical: 12},
});
