import React, {useCallback, useEffect, useState} from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import {listProfiles} from '../services/api';
import {useSession} from '../store';
import type {RootStackParamList} from '../navigation/AppNavigator';
import type {MemberProfile} from '../types';
import {colors} from '../theme';

type Props = NativeStackScreenProps<RootStackParamList, 'AdminMembers'>;

export function AdminMembersScreen({navigation}: Props) {
  const {session} = useSession();
  const [profiles, setProfiles] = useState<MemberProfile[]>([]);
  const [loading, setLoading] = useState(true);

  // Verify user has admin/owner role via session
  const userRole = session.user?.role;

  const loadProfiles = useCallback(async () => {
    try {
      const result = await listProfiles();
      setProfiles(result.profiles);
    } catch (err) {
      Alert.alert(
        'Error',
        err instanceof Error ? err.message : 'Failed to load members',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProfiles();
  }, [loadProfiles]);

  useEffect(() => {
    const unsubscribe = navigation.addListener('focus', () => {
      loadProfiles();
    });
    return unsubscribe;
  }, [navigation, loadProfiles]);

  const renderItem = ({item}: {item: MemberProfile}) => (
    <TouchableOpacity
      style={styles.memberRow}
      onPress={() =>
        navigation.navigate('AdminMemberDetail', {userId: item.user_id})
      }>
      <View style={styles.memberInfo}>
        <Text style={styles.memberName}>{item.display_name}</Text>
        <Text style={styles.memberDetail}>
          {item.family_role || 'No role set'} · {item.role}
        </Text>
      </View>
      <Text style={{fontSize: 20, color: colors.chevron, marginLeft: 8}}>›</Text>
    </TouchableOpacity>
  );

  if (loading) {
    return (
      <View style={[styles.container, styles.centered]}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  if (userRole && userRole !== 'admin' && userRole !== 'owner') {
    return (
      <View style={[styles.container, styles.centered]}>
        <Text style={{fontSize: 16, color: colors.textTertiary}}>Access denied. Admin role required.</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={profiles}
        keyExtractor={item => item.user_id}
        renderItem={renderItem}
        ListEmptyComponent={
          <View style={{padding: 32, alignItems: 'center'} as const}>
            <Text style={{fontSize: 16, color: colors.textTertiary}}>No family members yet</Text>
          </View>
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
  memberRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separator,
  },
  memberInfo: {
    flex: 1,
    marginLeft: 12,
  },
  memberName: {
    fontSize: 16,
    color: colors.textPrimary,
    fontWeight: '500',
  },
  memberDetail: {
    fontSize: 13,
    color: colors.textTertiary,
    marginTop: 2,
  },
});
