import React, {useCallback, useEffect, useRef, useState} from 'react';
import {
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
  ScrollView,
} from 'react-native';
import {Audio} from 'expo-av';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import {VoiceSessionClient} from '../services/voiceSession';
import type {VoiceEvent} from '../types';
import type {RootStackParamList} from '../navigation/AppNavigator';

type Props = NativeStackScreenProps<RootStackParamList, 'VoiceMode'>;

interface Transcript {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

export function VoiceModeScreen({route, navigation}: Props) {
  const conversationId = route.params?.conversationId ?? null;
  const [connected, setConnected] = useState(false);
  const [recording, setRecording] = useState(false);
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [error, setError] = useState<string | null>(null);

  const sessionRef = useRef<VoiceSessionClient | null>(null);
  const recordingRef = useRef<Audio.Recording | null>(null);
  const scrollRef = useRef<ScrollView>(null);

  const handleEvent = useCallback((event: VoiceEvent) => {
    if (event.type === 'transcript') {
      const newTranscript: Transcript = {
        id: `t-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        role: (event.role as 'user' | 'assistant') || 'assistant',
        content: event.content || '',
      };
      setTranscripts(prev => [...prev, newTranscript]);
    } else if (event.type === 'audio_chunk') {
      // Audio playback would go here — for now we rely on transcripts
    } else if (event.type === 'error') {
      setError(event.content || 'An error occurred');
    } else if (event.type === 'session_end') {
      setConnected(false);
    }
  }, []);

  const handleClose = useCallback(() => {
    setConnected(false);
    setRecording(false);
  }, []);

  // Connect on mount
  useEffect(() => {
    const session = new VoiceSessionClient(conversationId, handleEvent, handleClose);
    sessionRef.current = session;

    session.connect().then(() => {
      setConnected(true);
      session.sendAudioStart();
    }).catch(() => {
      setError('Failed to connect to voice service');
    });

    return () => {
      session.disconnect();
    };
  }, [conversationId, handleEvent, handleClose]);

  const startRecording = useCallback(async () => {
    try {
      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) {
        setError('Microphone permission is required');
        return;
      }

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      const {recording: rec} = await Audio.Recording.createAsync({
        android: {
          extension: '.wav',
          outputFormat: Audio.AndroidOutputFormat.DEFAULT,
          audioEncoder: Audio.AndroidAudioEncoder.DEFAULT,
          sampleRate: 16000,
          numberOfChannels: 1,
          bitRate: 256000,
        },
        ios: {
          extension: '.wav',
          outputFormat: Audio.IOSOutputFormat.LINEARPCM,
          audioQuality: Audio.IOSAudioQuality.HIGH,
          sampleRate: 16000,
          numberOfChannels: 1,
          bitRate: 256000,
          linearPCMBitDepth: 16,
          linearPCMIsBigEndian: false,
          linearPCMIsFloat: false,
        },
        web: {
          mimeType: 'audio/wav',
          bitsPerSecond: 256000,
        },
      });

      recordingRef.current = rec;
      setRecording(true);
    } catch {
      setError('Failed to start recording');
    }
  }, []);

  const stopRecording = useCallback(async () => {
    const rec = recordingRef.current;
    if (!rec) return;

    setRecording(false);
    try {
      await rec.stopAndUnloadAsync();
      const uri = rec.getURI();
      recordingRef.current = null;

      if (uri && sessionRef.current) {
        // Read file as base64 and send as audio chunk
        const FileSystem = await import('expo-file-system');
        const base64 = await FileSystem.readAsStringAsync(uri, {
          encoding: FileSystem.EncodingType.Base64,
        });
        sessionRef.current.sendAudioChunk(base64);
        sessionRef.current.sendAudioEnd();
      }
    } catch {
      setError('Failed to process recording');
    }
  }, []);

  const handleMicPress = useCallback(() => {
    if (recording) {
      stopRecording();
    } else {
      startRecording();
    }
  }, [recording, startRecording, stopRecording]);

  return (
    <View style={styles.container}>
      <ScrollView
        ref={scrollRef}
        style={styles.transcriptArea}
        contentContainerStyle={styles.transcriptContent}
        onContentSizeChange={() => scrollRef.current?.scrollToEnd({animated: true})}>
        {transcripts.map(t => (
          <View
            key={t.id}
            style={[
              styles.transcript,
              t.role === 'user' ? styles.userTranscript : styles.assistantTranscript,
            ]}>
            <Text style={styles.roleLabel}>
              {t.role === 'user' ? 'You' : 'Assistant'}
            </Text>
            <Text style={styles.transcriptText}>{t.content}</Text>
          </View>
        ))}
        {error && (
          <Text style={styles.errorText}>{error}</Text>
        )}
      </ScrollView>

      <View style={styles.controls}>
        <Text style={styles.statusText}>
          {!connected
            ? 'Connecting...'
            : recording
              ? 'Listening...'
              : 'Tap to speak'}
        </Text>
        <TouchableOpacity
          style={[
            styles.micButton,
            recording && styles.micButtonActive,
            !connected && styles.micButtonDisabled,
          ]}
          onPress={handleMicPress}
          disabled={!connected}>
          <Text style={styles.micIcon}>{recording ? 'STOP' : 'MIC'}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.backButton}
          onPress={() => navigation.goBack()}>
          <Text style={styles.backText}>Back to Chat</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1C1C1E',
  },
  transcriptArea: {
    flex: 1,
    paddingHorizontal: 16,
  },
  transcriptContent: {
    paddingVertical: 16,
  },
  transcript: {
    marginBottom: 12,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 12,
  },
  userTranscript: {
    backgroundColor: '#2C2C2E',
    alignSelf: 'flex-end',
    maxWidth: '80%',
  },
  assistantTranscript: {
    backgroundColor: '#3A3A3C',
    alignSelf: 'flex-start',
    maxWidth: '80%',
  },
  roleLabel: {
    color: '#8E8E93',
    fontSize: 12,
    marginBottom: 2,
  },
  transcriptText: {
    color: '#FFFFFF',
    fontSize: 16,
    lineHeight: 22,
  },
  errorText: {
    color: '#FF453A',
    fontSize: 14,
    textAlign: 'center',
    marginTop: 8,
  },
  controls: {
    alignItems: 'center',
    paddingVertical: 24,
    paddingBottom: 40,
    backgroundColor: '#2C2C2E',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
  },
  statusText: {
    color: '#8E8E93',
    fontSize: 14,
    marginBottom: 16,
  },
  micButton: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#007AFF',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  micButtonActive: {
    backgroundColor: '#FF453A',
  },
  micButtonDisabled: {
    backgroundColor: '#48484A',
  },
  micIcon: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '700',
  },
  backButton: {
    paddingHorizontal: 20,
    paddingVertical: 10,
  },
  backText: {
    color: '#007AFF',
    fontSize: 16,
  },
});
