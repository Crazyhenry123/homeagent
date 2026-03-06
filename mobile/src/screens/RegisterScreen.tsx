import React, {useState} from 'react';
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import {register} from '../services/api';
import {saveToken} from '../services/auth';
import {signUp, confirmSignUp, signIn} from '../services/cognitoAuth';
import type {RootStackParamList} from '../navigation/AppNavigator';

type Props = NativeStackScreenProps<RootStackParamList, 'Register'>;

type RegistrationMode = 'select' | 'owner' | 'member' | 'confirm';

export function RegisterScreen({navigation}: Props) {
  const [mode, setMode] = useState<RegistrationMode>('select');

  // Member (invite code) flow
  const [inviteCode, setInviteCode] = useState('');
  const [displayName, setDisplayName] = useState('');

  // Owner (Cognito) flow
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [ownerDisplayName, setOwnerDisplayName] = useState('');

  // Confirmation flow
  const [confirmationCode, setConfirmationCode] = useState('');

  const [loading, setLoading] = useState(false);

  const handleMemberRegister = async () => {
    if (!inviteCode.trim() || !displayName.trim()) {
      Alert.alert('Error', 'Please fill in all fields');
      return;
    }

    setLoading(true);
    try {
      const result = await register({
        invite_code: inviteCode.trim().toUpperCase(),
        device_name: `${Platform.OS} device`,
        platform: Platform.OS as 'ios' | 'android',
        display_name: displayName.trim(),
      });
      await saveToken(result.device_token);
      navigation.reset({index: 0, routes: [{name: 'AgentSetup'}]});
    } catch (err) {
      Alert.alert(
        'Registration Failed',
        err instanceof Error ? err.message : 'Unknown error',
      );
    } finally {
      setLoading(false);
    }
  };

  const handleOwnerSignup = async () => {
    if (
      !email.trim() ||
      !password ||
      !confirmPassword ||
      !ownerDisplayName.trim()
    ) {
      Alert.alert('Error', 'Please fill in all fields');
      return;
    }

    if (password !== confirmPassword) {
      Alert.alert('Error', 'Passwords do not match');
      return;
    }

    if (password.length < 8) {
      Alert.alert('Error', 'Password must be at least 8 characters');
      return;
    }

    const hasUpper = /[A-Z]/.test(password);
    const hasLower = /[a-z]/.test(password);
    const hasNumber = /\d/.test(password);
    const hasSpecial = /[^a-zA-Z\d]/.test(password);

    if (!hasUpper || !hasLower || !hasNumber || !hasSpecial) {
      Alert.alert(
        'Error',
        'Password must contain uppercase, lowercase, number, and special character',
      );
      return;
    }

    setLoading(true);
    try {
      await signUp(email.trim().toLowerCase(), password, ownerDisplayName.trim());
      setMode('confirm');
    } catch (err) {
      Alert.alert(
        'Signup Failed',
        err instanceof Error ? err.message : 'Unknown error',
      );
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async () => {
    if (!confirmationCode.trim()) {
      Alert.alert('Error', 'Please enter the verification code');
      return;
    }

    setLoading(true);
    try {
      await confirmSignUp(email.trim().toLowerCase(), confirmationCode.trim());
      // Auto-login after confirmation
      await signIn(email.trim().toLowerCase(), password);
      setPassword('');
      setConfirmPassword('');
      navigation.reset({index: 0, routes: [{name: 'ConversationList'}]});
    } catch (err) {
      Alert.alert(
        'Verification Failed',
        err instanceof Error ? err.message : 'Unknown error',
      );
    } finally {
      setLoading(false);
    }
  };

  const handleResendCode = async () => {
    try {
      const {resendCode} = await import('../services/cognitoAuth');
      await resendCode(email.trim().toLowerCase());
      Alert.alert('Code Sent', 'A new verification code has been sent to your email');
    } catch (err) {
      Alert.alert(
        'Error',
        err instanceof Error ? err.message : 'Failed to resend code',
      );
    }
  };

  // Mode selection screen
  if (mode === 'select') {
    return (
      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.content}>
          <Text style={styles.title}>Welcome to HomeAgent</Text>
          <Text style={styles.subtitle}>How would you like to get started?</Text>

          <TouchableOpacity
            style={styles.button}
            onPress={() => setMode('owner')}>
            <Text style={styles.buttonText}>Create Family</Text>
          </TouchableOpacity>

          <Text style={styles.orText}>or</Text>

          <TouchableOpacity
            style={[styles.button, styles.secondaryButton]}
            onPress={() => setMode('member')}>
            <Text style={[styles.buttonText, styles.secondaryButtonText]}>
              Join Family
            </Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    );
  }

  // Email verification screen
  if (mode === 'confirm') {
    return (
      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.content}>
          <Text style={styles.title}>Verify Your Email</Text>
          <Text style={styles.subtitle}>
            We sent a verification code to {email.trim().toLowerCase()}
          </Text>

          <TextInput
            style={styles.input}
            placeholder="Verification Code"
            placeholderTextColor="#8E8E93"
            value={confirmationCode}
            onChangeText={setConfirmationCode}
            keyboardType="number-pad"
            autoComplete="one-time-code"
            maxLength={6}
          />

          <TouchableOpacity
            style={[styles.button, loading && styles.buttonDisabled]}
            onPress={handleConfirm}
            disabled={loading}>
            <Text style={styles.buttonText}>
              {loading ? 'Verifying...' : 'Verify & Sign In'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.linkButton}
            onPress={handleResendCode}>
            <Text style={styles.linkText}>Resend Code</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.linkButton}
            onPress={() => setMode('owner')}>
            <Text style={styles.linkText}>Back</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    );
  }

  // Owner signup screen
  if (mode === 'owner') {
    return (
      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled">
          <Text style={styles.title}>Create Your Family</Text>
          <Text style={styles.subtitle}>
            Sign up with your email to get started
          </Text>

          <TextInput
            style={styles.input}
            placeholder="Email"
            placeholderTextColor="#8E8E93"
            value={email}
            onChangeText={setEmail}
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="email"
          />

          <TextInput
            style={styles.input}
            placeholder="Your Name"
            placeholderTextColor="#8E8E93"
            value={ownerDisplayName}
            onChangeText={setOwnerDisplayName}
            autoCapitalize="words"
            maxLength={50}
          />

          <TextInput
            style={styles.input}
            placeholder="Password"
            placeholderTextColor="#8E8E93"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete="new-password"
          />

          <TextInput
            style={styles.input}
            placeholder="Confirm Password"
            placeholderTextColor="#8E8E93"
            value={confirmPassword}
            onChangeText={setConfirmPassword}
            secureTextEntry
            autoComplete="new-password"
          />

          <Text style={styles.passwordHint}>
            Min 8 characters with uppercase, lowercase, number, and special
            character
          </Text>

          <TouchableOpacity
            style={[styles.button, loading && styles.buttonDisabled]}
            onPress={handleOwnerSignup}
            disabled={loading}>
            <Text style={styles.buttonText}>
              {loading ? 'Creating...' : 'Create Family'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.linkButton}
            onPress={() => setMode('select')}>
            <Text style={styles.linkText}>Back</Text>
          </TouchableOpacity>
        </ScrollView>
      </KeyboardAvoidingView>
    );
  }

  // Member (invite code) screen
  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={styles.content}>
        <Text style={styles.title}>Join Your Family</Text>
        <Text style={styles.subtitle}>Enter your invite code to get started</Text>

        <TextInput
          style={styles.input}
          placeholder="Invite Code"
          placeholderTextColor="#8E8E93"
          value={inviteCode}
          onChangeText={setInviteCode}
          autoCapitalize="characters"
          autoCorrect={false}
          maxLength={6}
        />

        <TextInput
          style={styles.input}
          placeholder="Your Name"
          placeholderTextColor="#8E8E93"
          value={displayName}
          onChangeText={setDisplayName}
          autoCapitalize="words"
          maxLength={50}
        />

        <TouchableOpacity
          style={[styles.button, loading && styles.buttonDisabled]}
          onPress={handleMemberRegister}
          disabled={loading}>
          <Text style={styles.buttonText}>
            {loading ? 'Registering...' : 'Join Family'}
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.linkButton}
          onPress={() => setMode('select')}>
          <Text style={styles.linkText}>Back</Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 32,
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'center',
    paddingHorizontal: 32,
    paddingVertical: 48,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    textAlign: 'center',
    color: '#000000',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    textAlign: 'center',
    color: '#8E8E93',
    marginBottom: 32,
  },
  input: {
    height: 48,
    borderWidth: 1,
    borderColor: '#C6C6C8',
    borderRadius: 10,
    paddingHorizontal: 16,
    fontSize: 16,
    marginBottom: 16,
    color: '#000000',
    backgroundColor: '#F9F9F9',
  },
  passwordHint: {
    fontSize: 12,
    color: '#8E8E93',
    textAlign: 'center',
    marginBottom: 16,
  },
  button: {
    height: 48,
    borderRadius: 10,
    backgroundColor: '#007AFF',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 8,
  },
  secondaryButton: {
    backgroundColor: '#FFFFFF',
    borderWidth: 2,
    borderColor: '#007AFF',
  },
  buttonDisabled: {
    backgroundColor: '#B0B0B0',
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '600',
  },
  secondaryButtonText: {
    color: '#007AFF',
  },
  orText: {
    textAlign: 'center',
    color: '#8E8E93',
    fontSize: 14,
    marginVertical: 12,
  },
  linkButton: {
    marginTop: 16,
    alignItems: 'center',
  },
  linkText: {
    color: '#007AFF',
    fontSize: 15,
  },
});
