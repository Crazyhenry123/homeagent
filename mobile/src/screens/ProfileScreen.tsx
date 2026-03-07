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
import {useSession} from '../store';
import type {RootStackParamList} from '../navigation/AppNavigator';
import {colors} from '../theme';

type Props = NativeStackScreenProps<RootStackParamList, 'Profile'>;

export function ProfileScreen({}: Props) {
  const {session, actions} = useSession();
  const profile = session.profile;

  const [saving, setSaving] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [familyRole, setFamilyRole] = useState('');
  const [healthNotes, setHealthNotes] = useState('');
  const [interestsText, setInterestsText] = useState('');

  // Populate form fields from session profile
  useEffect(() => {
    if (profile) {
      setDisplayName(profile.display_name);
      setFamilyRole(profile.family_role);
      setHealthNotes(profile.health_notes);
      setInterestsText(profile.interests.join(', '));
    }
  }, [profile]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const interests = interestsText
        .split(',')
        .map(s => s.trim())
        .filter(Boolean);
      await actions.updateProfile({
        display_name: displayName,
        family_role: familyRole,
        health_notes: healthNotes,
        interests,
      });
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

  if (!profile) {
    return (
      <View style={[styles.container, styles.centered]}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <ScrollView style={styles.container}>
      <View style={{paddingHorizontal: 16, paddingTop: 24, paddingBottom: 8}}>
        <Text style={{fontSize: 13, color: colors.textTertiary, fontWeight: '500', letterSpacing: 0.5}}>YOUR PROFILE</Text>
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

      <View style={styles.infoSection}>
        <Text style={styles.infoText}>Role: {profile.role}</Text>
        <Text style={styles.infoText}>User ID: {profile.user_id}</Text>
      </View>

      <TouchableOpacity
        style={[{marginTop: 24, marginHorizontal: 16, marginBottom: 32, height: 48, borderRadius: 10, backgroundColor: colors.primary, justifyContent: 'center' as const, alignItems: 'center' as const}, saving && {opacity: 0.6}]}
        onPress={handleSave}
        disabled={saving}>
        <Text style={{color: colors.surface, fontSize: 17, fontWeight: '600'}}>
          {saving ? 'Saving...' : 'Save Profile'}
        </Text>
      </TouchableOpacity>
    </ScrollView>
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
  field: {
    backgroundColor: colors.surface,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separator,
  },
  label: {
    fontSize: 13,
    color: colors.textTertiary,
    marginBottom: 6,
  },
  input: {
    fontSize: 16,
    color: colors.textPrimary,
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
    color: colors.textTertiary,
    marginBottom: 4,
  },
});
