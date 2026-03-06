import React from 'react';
import {
  Alert,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import Constants from 'expo-constants';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import {useSession} from '../store';
import type {RootStackParamList} from '../navigation/AppNavigator';

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

      {isOwnerOrAdmin && (
        <>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionHeaderText}>ADMIN</Text>
          </View>
          <TouchableOpacity
            style={styles.actionRow}
            onPress={() => navigation.navigate('FamilyManage')}>
            <Text style={styles.actionText}>Manage Family</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.adminPanelButton}
            onPress={() => navigation.navigate('AdminPanel')}>
            <Text style={styles.adminPanelButtonText}>Open Admin Panel</Text>
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
  adminPanelButton: {
    marginTop: 8,
    marginHorizontal: 16,
    height: 48,
    borderRadius: 10,
    backgroundColor: '#007AFF',
    justifyContent: 'center',
    alignItems: 'center',
  },
  adminPanelButtonText: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '600',
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
