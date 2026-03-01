import React, {useEffect, useState} from 'react';
import {
  Alert,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
  ActivityIndicator,
} from 'react-native';
import Constants from 'expo-constants';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import {verify, generateInviteCode} from '../services/api';
import {clearToken} from '../services/auth';
import type {RootStackParamList} from '../navigation/AppNavigator';

type Props = NativeStackScreenProps<RootStackParamList, 'Settings'>;

export function SettingsScreen({navigation}: Props) {
  const [name, setName] = useState('');
  const [userId, setUserId] = useState('');
  const [role, setRole] = useState('');
  const [loading, setLoading] = useState(true);
  const [generatingCode, setGeneratingCode] = useState(false);

  useEffect(() => {
    verify()
      .then(result => {
        setName(result.name);
        setUserId(result.user_id);
        setRole(result.role);
      })
      .catch(() => {
        // Token may be invalid
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  const handleGenerateInviteCode = async () => {
    setGeneratingCode(true);
    try {
      const result = await generateInviteCode();
      Alert.alert(
        'Invite Code Created',
        `Share this code with a family member:\n\n${result.code ?? 'Unknown'}`,
        [{text: 'OK'}],
      );
    } catch (err) {
      Alert.alert(
        'Error',
        err instanceof Error ? err.message : 'Failed to generate invite code',
      );
    } finally {
      setGeneratingCode(false);
    }
  };

  const handleLogout = () => {
    Alert.alert('Log Out', 'You will need an invite code to log back in.', [
      {text: 'Cancel', style: 'cancel'},
      {
        text: 'Log Out',
        style: 'destructive',
        onPress: async () => {
          await clearToken();
          navigation.reset({index: 0, routes: [{name: 'Register'}]});
        },
      },
    ]);
  };

  if (loading) {
    return (
      <View style={[styles.container, styles.loadingContainer]}>
        <ActivityIndicator size="large" color="#007AFF" />
      </View>
    );
  }

  const appVersion = Constants.expoConfig?.version ?? '0.1.0';

  return (
    <View style={styles.container}>
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

      {role === 'admin' && (
        <>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionHeaderText}>ADMIN</Text>
          </View>
          <TouchableOpacity
            style={styles.actionRow}
            onPress={handleGenerateInviteCode}
            disabled={generatingCode}>
            <Text style={styles.actionText}>
              {generatingCode ? 'Generating...' : 'Generate Invite Code'}
            </Text>
          </TouchableOpacity>
        </>
      )}

      <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
        <Text style={styles.logoutText}>Log Out</Text>
      </TouchableOpacity>

      <Text style={styles.versionText}>HomeAgent v{appVersion}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F2F2F7',
  },
  loadingContainer: {
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
  section: {
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 16,
    paddingVertical: 14,
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
  actionRow: {
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E5E5EA',
  },
  actionText: {
    fontSize: 16,
    color: '#007AFF',
  },
  logoutButton: {
    marginTop: 32,
    marginHorizontal: 16,
    height: 48,
    borderRadius: 10,
    backgroundColor: '#FF3B30',
    justifyContent: 'center',
    alignItems: 'center',
  },
  logoutText: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '600',
  },
  versionText: {
    textAlign: 'center',
    color: '#AEAEB2',
    fontSize: 13,
    marginTop: 24,
  },
});
