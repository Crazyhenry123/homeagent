import React, {useState, useCallback, useRef, useEffect} from 'react';
import {
  Alert,
  Platform,
  ScrollView,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  View,
  Text,
} from 'react-native';
import {useSafeAreaInsets} from 'react-native-safe-area-context';
import {getInfoAsync} from 'expo-file-system/legacy';
import * as ImagePicker from 'expo-image-picker';
import {
  ExpoSpeechRecognitionModule,
  useSpeechRecognitionEvent,
} from 'expo-speech-recognition';
import {ImageAttachment} from './ImageAttachment';
import {VoiceButton} from './VoiceButton';
import {getContentType} from '../services/chatMedia';
import type {ChatMediaUpload} from '../types';

interface Props {
  onSend: (message: string, attachments: ChatMediaUpload[], isVoice?: boolean) => void;
  disabled?: boolean;
}

export function ChatInput({onSend, disabled}: Props) {
  const insets = useSafeAreaInsets();
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<ChatMediaUpload[]>([]);
  const [recognizing, setRecognizing] = useState(false);
  const [voiceTranscript, setVoiceTranscript] = useState('');
  // Track whether we got a final result so we can auto-send
  const finalTranscriptRef = useRef<string | null>(null);

  useSpeechRecognitionEvent('start', () => {
    setRecognizing(true);
    setVoiceTranscript('');
    finalTranscriptRef.current = null;
  });

  useSpeechRecognitionEvent('end', () => {
    setRecognizing(false);
    // Auto-send on end if we have a final transcript
    const transcript = finalTranscriptRef.current;
    if (transcript && transcript.trim()) {
      onSend(transcript.trim(), [], true);
      setText('');
      setVoiceTranscript('');
    }
    finalTranscriptRef.current = null;
  });

  useSpeechRecognitionEvent('result', (event) => {
    const result = event.results[0]?.transcript || '';
    setVoiceTranscript(result);
    if (event.isFinal) {
      finalTranscriptRef.current = result;
    }
  });

  useSpeechRecognitionEvent('error', (event) => {
    console.error('[Speech] error:', event.error, event.message);
    setRecognizing(false);
    setVoiceTranscript('');
    finalTranscriptRef.current = null;
    if (event.error !== 'no-speech') {
      Alert.alert('Voice Error', event.message || 'Speech recognition failed.');
    }
  });

  const handleSend = () => {
    const trimmed = text.trim();
    if ((!trimmed && attachments.length === 0) || disabled) return;
    onSend(trimmed, attachments);
    setText('');
    setAttachments([]);
  };

  const handlePickImage = useCallback(async () => {
    if (attachments.length >= 5) {
      Alert.alert('Limit reached', 'You can attach up to 5 images per message.');
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.8,
      allowsMultipleSelection: true,
      selectionLimit: 5 - attachments.length,
    });

    if (result.canceled || !result.assets) return;

    const newAttachments: ChatMediaUpload[] = [];
    for (const asset of result.assets) {
      let size = asset.fileSize || 0;
      if (size <= 0) {
        try {
          const info = await getInfoAsync(asset.uri);
          size = info.exists ? (info.size ?? 0) : 0;
        } catch {
          // Fall through with size 0
        }
      }
      newAttachments.push({
        localId: `img-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        uri: asset.uri,
        contentType: asset.mimeType || getContentType(asset.uri),
        fileSize: size,
        status: 'pending' as const,
      });
    }

    setAttachments(prev => [...prev, ...newAttachments].slice(0, 5));
  }, [attachments.length]);

  const handleRemoveAttachment = useCallback((localId: string) => {
    setAttachments(prev => prev.filter(a => a.localId !== localId));
  }, []);

  const handleVoicePress = useCallback(async () => {
    if (recognizing) {
      // Stop recognition — will trigger 'end' event which auto-sends
      ExpoSpeechRecognitionModule.stop();
    } else {
      // Request permissions and start
      const result = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
      if (!result.granted) {
        Alert.alert(
          'Permission required',
          'Microphone access is needed for voice input.',
        );
        return;
      }

      ExpoSpeechRecognitionModule.start({
        lang: 'en-US',
        interimResults: true,
        continuous: true,
        addsPunctuation: true,
        iosTaskHint: 'dictation',
        iosCategory: {
          category: 'playAndRecord',
          categoryOptions: ['defaultToSpeaker', 'allowBluetooth'],
          mode: 'measurement',
        },
      });
    }
  }, [recognizing]);

  const canSend = (text.trim().length > 0 || attachments.length > 0) && !disabled;

  const bottomPadding =
    Platform.OS === 'ios' ? insets.bottom + 12 : 20;

  return (
    <View style={[styles.wrapper, {paddingBottom: bottomPadding}]}>
      {attachments.length > 0 && (
        <ScrollView
          horizontal
          style={styles.attachmentRow}
          contentContainerStyle={styles.attachmentRowContent}
          showsHorizontalScrollIndicator={false}>
          {attachments.map(a => (
            <ImageAttachment
              key={a.localId}
              attachment={a}
              onRemove={handleRemoveAttachment}
            />
          ))}
        </ScrollView>
      )}
      {recognizing && (
        <View style={styles.recordingIndicator}>
          <Text style={styles.recordingDot}>●</Text>
          <Text style={styles.recordingText}>
            {voiceTranscript
              ? 'Listening... Tap mic to send'
              : 'Listening... Speak now'}
          </Text>
        </View>
      )}
      {recognizing && voiceTranscript ? (
        <View style={styles.transcriptPreview}>
          <Text style={styles.transcriptText}>{voiceTranscript}</Text>
        </View>
      ) : null}
      <View style={styles.container}>
        <TouchableOpacity
          style={styles.attachButton}
          onPress={handlePickImage}
          disabled={disabled || recognizing}>
          <Text style={[styles.attachIcon, (disabled || recognizing) && styles.attachIconDisabled]}>
            +
          </Text>
        </TouchableOpacity>
        <TextInput
          style={styles.input}
          value={text}
          onChangeText={setText}
          placeholder="Type a message..."
          placeholderTextColor="#8E8E93"
          multiline
          maxLength={4000}
          editable={!disabled && !recognizing}
          onSubmitEditing={handleSend}
          blurOnSubmit={false}
        />
        <TouchableOpacity
          style={[styles.sendButton, !canSend && styles.sendButtonDisabled]}
          onPress={handleSend}
          disabled={!canSend || recognizing}>
          <Text style={styles.sendText}>Send</Text>
        </TouchableOpacity>
        <VoiceButton
          onPress={handleVoicePress}
          disabled={disabled}
          recording={recognizing}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: '#C6C6C8',
    backgroundColor: '#FFFFFF',
  },
  attachmentRow: {
    maxHeight: 80,
    paddingHorizontal: 8,
    paddingTop: 8,
  },
  attachmentRowContent: {
    alignItems: 'center',
  },
  recordingIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingTop: 8,
  },
  recordingDot: {
    color: '#FF3B30',
    fontSize: 12,
    marginRight: 6,
  },
  recordingText: {
    color: '#FF3B30',
    fontSize: 13,
    fontWeight: '500',
  },
  transcriptPreview: {
    paddingHorizontal: 14,
    paddingTop: 6,
    paddingBottom: 2,
  },
  transcriptText: {
    color: '#333',
    fontSize: 15,
    fontStyle: 'italic',
  },
  container: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: 8,
    paddingVertical: 8,
  },
  attachButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#E9E9EB',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 6,
  },
  attachIcon: {
    fontSize: 22,
    color: '#007AFF',
    fontWeight: '600',
    lineHeight: 24,
  },
  attachIconDisabled: {
    color: '#B0B0B0',
  },
  input: {
    flex: 1,
    minHeight: 36,
    maxHeight: 120,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: '#C6C6C8',
    paddingHorizontal: 14,
    paddingVertical: 8,
    fontSize: 16,
    backgroundColor: '#F9F9F9',
    color: '#000000',
  },
  sendButton: {
    marginLeft: 8,
    paddingHorizontal: 14,
    minHeight: 44,
    borderRadius: 22,
    backgroundColor: '#007AFF',
    justifyContent: 'center',
  },
  sendButtonDisabled: {
    backgroundColor: '#B0B0B0',
  },
  sendText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
});
