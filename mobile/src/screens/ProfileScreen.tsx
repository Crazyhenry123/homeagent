import React, {useEffect, useState} from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import {getMyProfile, updateMyProfile} from '../services/api';
import type {RootStackParamList} from '../navigation/AppNavigator';
import type {MemberProfile} from '../types';

type Props = NativeStackScreenProps<RootStackParamList, 'Profile'>;

export function ProfileScreen({}: Props) {
  const [profile, setProfile] = useState<MemberProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [familyRole, setFamilyRole] = useState('');
  const [healthNotes, setHealthNotes] = useState('');
  const [interestsText, setInterestsText] = useState('');

  useEffect(() => {
    getMyProfile()
      .then(p => {
        setProfile(p);
        setDisplayName(p.display_name);
        setFamilyRole(p.family_role);
        setHealthNotes(p.health_notes);
        setInterestsText(p.interests.join(', '));
      })
      .catch(() => Alert.alert('Error', 'Failed to load profile'))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const interests = interestsText
        .split(',')
        .map(s => s.trim())
        .filter(Boolean);
      const updated = await updateMyProfile({
        display_name: displayName,
        family_role: familyRole,
        health_notes: healthNotes,
        interests,
      });
      setProfile(updated);
      Alert.alert('Saved', 'Profile updated successfully');
    } catch (err) {
      Alert.alert(
        'Error',
        err instanceof Error ? err.message : 'Failed to save profile',
      );
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <View style={[styles.container, styles.centered]}>
        <ActivityIndicator size="large" color="#007AFF" />
      </View>
    );
  }

  return (
    <ScrollView style={styles.container}>
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionHeaderText}>YOUR PROFILE</Text>
      </View>

      <View style={styles.field}>
        <Text style={styles.label}>Display Name</Text>
        <TextInput
          style={styles.input}
          value={displayName}
          onChangeText={setDisplayName}
          placeholder="Your name"
        />
      </View>

      <View style={styles.field}>
        <Text style={styles.label}>Family Role</Text>
        <TextInput
          style={styles.input}
          value={familyRole}
          onChangeText={setFamilyRole}
          placeholder="e.g., Parent, Child, Grandparent"
        />
      </View>

      <View style={styles.field}>
        <Text style={styles.label}>Health Notes</Text>
        <TextInput
          style={[styles.input, styles.multilineInput]}
          value={healthNotes}
          onChangeText={setHealthNotes}
          placeholder="Allergies, dietary restrictions, etc."
          multiline
        />
      </View>

      <View style={styles.field}>
        <Text style={styles.label}>Interests (comma-separated)</Text>
        <TextInput
          style={styles.input}
          value={interestsText}
          onChangeText={setInterestsText}
          placeholder="cooking, hiking, reading"
        />
      </View>

      {profile && (
        <View style={styles.infoSection}>
          <Text style={styles.infoText}>Role: {profile.role}</Text>
          <Text style={styles.infoText}>User ID: {profile.user_id}</Text>
        </View>
      )}

      <TouchableOpacity
        style={[styles.saveButton, saving && styles.saveButtonDisabled]}
        onPress={handleSave}
        disabled={saving}>
        <Text style={styles.saveButtonText}>
          {saving ? 'Saving...' : 'Save Profile'}
        </Text>
      </TouchableOpacity>
    </ScrollView>
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
  field: {
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E5E5EA',
  },
  label: {
    fontSize: 13,
    color: '#8E8E93',
    marginBottom: 6,
  },
  input: {
    fontSize: 16,
    color: '#000000',
    padding: 0,
  },
  multilineInput: {
    minHeight: 60,
    textAlignVertical: 'top',
  },
  infoSection: {
    paddingHorizontal: 16,
    paddingTop: 16,
  },
  infoText: {
    fontSize: 13,
    color: '#8E8E93',
    marginBottom: 4,
  },
  saveButton: {
    marginTop: 24,
    marginHorizontal: 16,
    marginBottom: 32,
    height: 48,
    borderRadius: 10,
    backgroundColor: '#007AFF',
    justifyContent: 'center',
    alignItems: 'center',
  },
  saveButtonDisabled: {
    opacity: 0.6,
  },
  saveButtonText: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '600',
  },
});
