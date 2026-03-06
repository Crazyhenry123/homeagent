import React, {useCallback, useEffect, useState} from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import {
  cancelInvite,
  createFamily,
  getPendingInvites,
  inviteMember,
} from '../services/api';
import {useSession} from '../store';
import type {RootStackParamList} from '../navigation/AppNavigator';
import type {FamilyInvite} from '../types';

type Props = NativeStackScreenProps<RootStackParamList, 'FamilyManage'>;

export function FamilyManageScreen({}: Props) {
  const {session, actions} = useSession();
  const familyData = session.family;
  const family = familyData?.info ?? null;
  const members = familyData?.members ?? [];

  const [invites, setInvites] = useState<FamilyInvite[]>([]);
  const [loadingInvites, setLoadingInvites] = useState(true);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviting, setInviting] = useState(false);
  const [showInviteInput, setShowInviteInput] = useState(false);
  const [familyName, setFamilyName] = useState('');
  const [creatingFamily, setCreatingFamily] = useState(false);

  const noFamily = !familyData;

  const loadInvites = useCallback(async () => {
    try {
      const invitesResult = await getPendingInvites();
      setInvites(invitesResult.invites);
    } catch {
      // Invites may not be available
    } finally {
      setLoadingInvites(false);
    }
  }, []);

  useEffect(() => {
    if (!noFamily) {
      loadInvites();
    } else {
      setLoadingInvites(false);
    }
  }, [noFamily, loadInvites]);

  const handleCreateFamily = async () => {
    if (!familyName.trim()) {
      Alert.alert('Error', 'Please enter a family name');
      return;
    }
    setCreatingFamily(true);
    try {
      await createFamily(familyName.trim());
      setFamilyName('');
      await actions.refreshFamily();
      await loadInvites();
    } catch (err) {
      Alert.alert(
        'Error',
        err instanceof Error ? err.message : 'Failed to create family',
      );
    } finally {
      setCreatingFamily(false);
    }
  };

  const handleInvite = async () => {
    if (!inviteEmail.trim()) {
      Alert.alert('Error', 'Please enter an email address');
      return;
    }
    setInviting(true);
    try {
      const result = await inviteMember(inviteEmail.trim());
      const message = result.email_sent
        ? `Invite sent to ${inviteEmail.trim()}`
        : `Invite code: ${result.code}\n\nEmail sending is not configured. Share this code manually.`;
      Alert.alert('Invite Created', message);
      setInviteEmail('');
      setShowInviteInput(false);
      await actions.refreshFamily();
      await loadInvites();
    } catch (err) {
      Alert.alert(
        'Error',
        err instanceof Error ? err.message : 'Failed to send invite',
      );
    } finally {
      setInviting(false);
    }
  };

  const handleCancelInvite = (code: string, email?: string) => {
    Alert.alert(
      'Cancel Invite',
      `Cancel invite${email ? ` for ${email}` : ` (code: ${code})`}?`,
      [
        {text: 'No', style: 'cancel'},
        {
          text: 'Yes, Cancel',
          style: 'destructive',
          onPress: async () => {
            try {
              await cancelInvite(code);
              await actions.refreshFamily();
              await loadInvites();
            } catch (err) {
              Alert.alert(
                'Error',
                err instanceof Error
                  ? err.message
                  : 'Failed to cancel invite',
              );
            }
          },
        },
      ],
    );
  };

  if (session.status === 'loading' || loadingInvites) {
    return (
      <View style={[styles.container, styles.centered]}>
        <ActivityIndicator size="large" color="#007AFF" />
      </View>
    );
  }

  if (noFamily) {
    return (
      <View style={styles.container}>
        <View style={styles.createFamilySection}>
          <Text style={styles.noFamilyText}>
            You haven't created a family yet.
          </Text>
          <Text style={styles.noFamilySubtext}>
            Create one to start inviting members.
          </Text>
          <TextInput
            style={styles.input}
            placeholder="Family Name"
            placeholderTextColor="#8E8E93"
            value={familyName}
            onChangeText={setFamilyName}
            autoCapitalize="words"
          />
          <TouchableOpacity
            style={styles.createButton}
            onPress={handleCreateFamily}
            disabled={creatingFamily}>
            <Text style={styles.createButtonText}>
              {creatingFamily ? 'Creating...' : 'Create Family'}
            </Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Family Info */}
      {family && (
        <View style={styles.familyInfo}>
          <Text style={styles.familyName}>{family.name}</Text>
          <Text style={styles.familyMeta}>
            {members.length} member{members.length !== 1 ? 's' : ''}
          </Text>
        </View>
      )}

      {/* Members Section */}
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionHeaderText}>MEMBERS</Text>
      </View>
      <FlatList
        data={members}
        keyExtractor={item => item.user_id}
        renderItem={({item}) => (
          <View style={styles.memberRow}>
            <View style={styles.memberInfo}>
              <Text style={styles.memberName}>{item.name}</Text>
              <Text style={styles.memberRole}>{item.role}</Text>
            </View>
          </View>
        )}
        ListEmptyComponent={
          <View style={styles.emptyState}>
            <Text style={styles.emptyText}>No members yet</Text>
          </View>
        }
        scrollEnabled={false}
      />

      {/* Invite Section */}
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionHeaderText}>INVITE MEMBER</Text>
      </View>
      {showInviteInput ? (
        <View style={styles.inviteInputContainer}>
          <TextInput
            style={styles.input}
            placeholder="Email address"
            placeholderTextColor="#8E8E93"
            value={inviteEmail}
            onChangeText={setInviteEmail}
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
          />
          <View style={styles.inviteButtonRow}>
            <TouchableOpacity
              style={styles.cancelInputButton}
              onPress={() => {
                setShowInviteInput(false);
                setInviteEmail('');
              }}>
              <Text style={styles.cancelInputButtonText}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.sendInviteButton}
              onPress={handleInvite}
              disabled={inviting}>
              <Text style={styles.sendInviteButtonText}>
                {inviting ? 'Sending...' : 'Send Invite'}
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : (
        <TouchableOpacity
          style={styles.inviteButton}
          onPress={() => setShowInviteInput(true)}>
          <Text style={styles.inviteButtonText}>+ Invite Member by Email</Text>
        </TouchableOpacity>
      )}

      {/* Pending Invites */}
      {invites.length > 0 && (
        <>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionHeaderText}>PENDING INVITES</Text>
          </View>
          <FlatList
            data={invites}
            keyExtractor={item => item.code}
            renderItem={({item}) => (
              <View style={styles.inviteRow}>
                <View style={styles.inviteInfo}>
                  <Text style={styles.inviteEmail}>
                    {item.invited_email || 'Code invite'}
                  </Text>
                  <Text style={styles.inviteCode}>Code: {item.code}</Text>
                </View>
                <TouchableOpacity
                  onPress={() =>
                    handleCancelInvite(item.code, item.invited_email)
                  }>
                  <Text style={styles.cancelText}>Cancel</Text>
                </TouchableOpacity>
              </View>
            )}
            scrollEnabled={false}
          />
        </>
      )}
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
  familyInfo: {
    backgroundColor: '#FFFFFF',
    padding: 20,
    alignItems: 'center',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E5E5EA',
  },
  familyName: {
    fontSize: 22,
    fontWeight: '600',
    color: '#000000',
  },
  familyMeta: {
    fontSize: 14,
    color: '#8E8E93',
    marginTop: 4,
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
  memberRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E5E5EA',
  },
  memberInfo: {
    flex: 1,
  },
  memberName: {
    fontSize: 16,
    color: '#000000',
    fontWeight: '500',
  },
  memberRole: {
    fontSize: 13,
    color: '#8E8E93',
    marginTop: 2,
    textTransform: 'capitalize',
  },
  emptyState: {
    padding: 32,
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
  },
  emptyText: {
    fontSize: 16,
    color: '#8E8E93',
  },
  inviteButton: {
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E5E5EA',
  },
  inviteButtonText: {
    fontSize: 16,
    color: '#007AFF',
    fontWeight: '500',
  },
  inviteInputContainer: {
    backgroundColor: '#FFFFFF',
    padding: 16,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E5E5EA',
  },
  input: {
    backgroundColor: '#F2F2F7',
    borderRadius: 10,
    paddingHorizontal: 16,
    paddingVertical: 12,
    fontSize: 16,
    color: '#000000',
    marginBottom: 12,
  },
  inviteButtonRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 12,
  },
  cancelInputButton: {
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  cancelInputButtonText: {
    fontSize: 16,
    color: '#8E8E93',
  },
  sendInviteButton: {
    backgroundColor: '#007AFF',
    borderRadius: 8,
    paddingHorizontal: 20,
    paddingVertical: 10,
  },
  sendInviteButtonText: {
    fontSize: 16,
    color: '#FFFFFF',
    fontWeight: '600',
  },
  inviteRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E5E5EA',
  },
  inviteInfo: {
    flex: 1,
  },
  inviteEmail: {
    fontSize: 16,
    color: '#000000',
    fontWeight: '500',
  },
  inviteCode: {
    fontSize: 13,
    color: '#8E8E93',
    marginTop: 2,
  },
  cancelText: {
    fontSize: 14,
    color: '#FF3B30',
    fontWeight: '500',
  },
  createFamilySection: {
    padding: 24,
    alignItems: 'center',
  },
  noFamilyText: {
    fontSize: 18,
    fontWeight: '600',
    color: '#000000',
    marginBottom: 8,
  },
  noFamilySubtext: {
    fontSize: 14,
    color: '#8E8E93',
    marginBottom: 24,
  },
  createButton: {
    backgroundColor: '#007AFF',
    borderRadius: 10,
    paddingHorizontal: 24,
    paddingVertical: 14,
    width: '100%',
    alignItems: 'center',
  },
  createButtonText: {
    fontSize: 16,
    color: '#FFFFFF',
    fontWeight: '600',
  },
});
