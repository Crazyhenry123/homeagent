import React, {useState} from 'react';
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import type {RootStackParamList} from '../navigation/AppNavigator';
import {grantPermission} from '../services/api';

type Props = NativeStackScreenProps<RootStackParamList, 'AgentSetup'>;

type EmailProvider = 'gmail' | 'outlook' | 'other';

export function AgentSetupScreen({navigation}: Props) {
  // Logistics Assistant state
  const [emailAddress, setEmailAddress] = useState('');
  const [emailProvider, setEmailProvider] = useState<EmailProvider>('gmail');
  const [calendarEnabled, setCalendarEnabled] = useState(false);

  // Health Advisor state
  const [healthDataConsent, setHealthDataConsent] = useState(false);
  const [medicalRecordsConsent, setMedicalRecordsConsent] = useState(false);

  const [saving, setSaving] = useState(false);

  const handleContinue = async () => {
    setSaving(true);
    try {
      // Grant email_access if email provided
      if (emailAddress.trim()) {
        await grantPermission('email_access', {
          email_address: emailAddress.trim(),
          provider: emailProvider,
        });
      }

      // Grant calendar_access if toggled
      if (calendarEnabled) {
        await grantPermission('calendar_access', {
          calendar_id: 'default',
          provider: emailProvider,
        });
      }

      // Grant health_data if consented
      if (healthDataConsent) {
        await grantPermission('health_data', {
          consent_given: true,
          data_sources: ['healthkit'],
        });
      }

      // Grant medical_records if consented
      if (medicalRecordsConsent) {
        await grantPermission('medical_records', {
          folder_path: '/health-documents',
          s3_prefix: 'health-documents/',
        });
      }

      navigation.reset({index: 0, routes: [{name: 'ConversationList'}]});
    } catch (err) {
      Alert.alert(
        'Setup Error',
        err instanceof Error ? err.message : 'Failed to save permissions',
      );
    } finally {
      setSaving(false);
    }
  };

  const handleSkip = () => {
    navigation.reset({index: 0, routes: [{name: 'ConversationList'}]});
  };

  const providerOptions: {label: string; value: EmailProvider}[] = [
    {label: 'Gmail', value: 'gmail'},
    {label: 'Outlook', value: 'outlook'},
    {label: 'Other', value: 'other'},
  ];

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>Set Up Your Agents</Text>
        <Text style={styles.subtitle}>
          Configure data access for your default agents. You can change these
          settings later.
        </Text>

        {/* Logistics Assistant Section */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Logistics Assistant</Text>
            <Text style={styles.sectionDescription}>
              Helps with email drafting and schedule management
            </Text>
          </View>

          <View style={styles.card}>
            <Text style={styles.fieldLabel}>Email Account</Text>
            <Text style={styles.fieldDescription}>
              Connect your email so the agent can draft messages on your behalf
            </Text>
            <TextInput
              style={styles.input}
              placeholder="your@email.com"
              placeholderTextColor="#8E8E93"
              value={emailAddress}
              onChangeText={setEmailAddress}
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
            />

            <Text style={styles.fieldLabel}>Email Provider</Text>
            <View style={styles.providerRow}>
              {providerOptions.map(option => (
                <TouchableOpacity
                  key={option.value}
                  style={[
                    styles.providerButton,
                    emailProvider === option.value &&
                      styles.providerButtonActive,
                  ]}
                  onPress={() => setEmailProvider(option.value)}>
                  <Text
                    style={[
                      styles.providerButtonText,
                      emailProvider === option.value &&
                        styles.providerButtonTextActive,
                    ]}>
                    {option.label}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <View style={styles.toggleRow}>
              <View style={styles.toggleContent}>
                <Text style={styles.fieldLabel}>Calendar Access</Text>
                <Text style={styles.fieldDescription}>
                  Allow the agent to read your calendar and manage your agenda
                </Text>
              </View>
              <Switch
                value={calendarEnabled}
                onValueChange={setCalendarEnabled}
                trackColor={{false: '#E5E5EA', true: '#34C759'}}
                thumbColor="#FFFFFF"
              />
            </View>
          </View>
        </View>

        {/* Health Advisor Section */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Health Advisor</Text>
            <Text style={styles.sectionDescription}>
              Tracks health patterns and provides personalized wellness guidance
            </Text>
          </View>

          <View style={styles.card}>
            <View style={styles.toggleRow}>
              <View style={styles.toggleContent}>
                <Text style={styles.fieldLabel}>Health Data Access</Text>
                <Text style={styles.fieldDescription}>
                  Allow the agent to access your health data from your phone
                  (steps, heart rate, sleep data via HealthKit)
                </Text>
              </View>
              <Switch
                value={healthDataConsent}
                onValueChange={setHealthDataConsent}
                trackColor={{false: '#E5E5EA', true: '#34C759'}}
                thumbColor="#FFFFFF"
              />
            </View>

            <View style={[styles.toggleRow, styles.lastToggleRow]}>
              <View style={styles.toggleContent}>
                <Text style={styles.fieldLabel}>Medical Records</Text>
                <Text style={styles.fieldDescription}>
                  Allow the agent to access your uploaded medical records and
                  health documents for personalized advice
                </Text>
              </View>
              <Switch
                value={medicalRecordsConsent}
                onValueChange={setMedicalRecordsConsent}
                trackColor={{false: '#E5E5EA', true: '#34C759'}}
                thumbColor="#FFFFFF"
              />
            </View>
          </View>
        </View>

        {/* Action Buttons */}
        <View style={styles.buttonContainer}>
          <TouchableOpacity
            style={[styles.continueButton, saving && styles.buttonDisabled]}
            onPress={handleContinue}
            disabled={saving}>
            <Text style={styles.continueButtonText}>
              {saving ? 'Saving...' : 'Continue'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.skipButton}
            onPress={handleSkip}
            disabled={saving}>
            <Text style={styles.skipButtonText}>Skip for now</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F2F2F7',
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 40,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: '#000000',
    textAlign: 'center',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 15,
    color: '#8E8E93',
    textAlign: 'center',
    marginBottom: 24,
    lineHeight: 20,
  },
  section: {
    marginBottom: 24,
  },
  sectionHeader: {
    marginBottom: 12,
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: '#000000',
    marginBottom: 4,
  },
  sectionDescription: {
    fontSize: 14,
    color: '#8E8E93',
    lineHeight: 18,
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 16,
  },
  fieldLabel: {
    fontSize: 16,
    fontWeight: '600',
    color: '#000000',
    marginBottom: 4,
  },
  fieldDescription: {
    fontSize: 13,
    color: '#8E8E93',
    marginBottom: 12,
    lineHeight: 17,
  },
  input: {
    height: 44,
    borderWidth: 1,
    borderColor: '#C6C6C8',
    borderRadius: 8,
    paddingHorizontal: 12,
    fontSize: 16,
    color: '#000000',
    backgroundColor: '#F9F9F9',
    marginBottom: 16,
  },
  providerRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 16,
  },
  providerButton: {
    flex: 1,
    height: 36,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#C6C6C8',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#F9F9F9',
  },
  providerButtonActive: {
    borderColor: '#007AFF',
    backgroundColor: '#EBF5FF',
  },
  providerButtonText: {
    fontSize: 14,
    fontWeight: '500',
    color: '#8E8E93',
  },
  providerButtonTextActive: {
    color: '#007AFF',
  },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: '#E5E5EA',
  },
  lastToggleRow: {
    borderBottomWidth: 0,
  },
  toggleContent: {
    flex: 1,
    marginRight: 12,
  },
  buttonContainer: {
    marginTop: 8,
    gap: 12,
  },
  continueButton: {
    height: 48,
    borderRadius: 10,
    backgroundColor: '#007AFF',
    justifyContent: 'center',
    alignItems: 'center',
  },
  buttonDisabled: {
    backgroundColor: '#B0B0B0',
  },
  continueButtonText: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '600',
  },
  skipButton: {
    height: 44,
    justifyContent: 'center',
    alignItems: 'center',
  },
  skipButtonText: {
    color: '#007AFF',
    fontSize: 16,
    fontWeight: '500',
  },
});
