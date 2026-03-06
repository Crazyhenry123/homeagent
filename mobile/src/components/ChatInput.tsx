import React, {useState, useCallback, useRef} from 'react';
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
import {Audio} from 'expo-av';
import {getInfoAsync} from 'expo-file-system/legacy';
import * as ImagePicker from 'expo-image-picker';
import {ImageAttachment} from './ImageAttachment';
import {VoiceButton} from './VoiceButton';
import {getContentType, uploadAudio} from '../services/chatMedia';
import type {ChatMediaUpload} from '../types';

interface Props {
  onSend: (message: string, attachments: ChatMediaUpload[]) => void;
  disabled?: boolean;
}

export function ChatInput({onSend, disabled}: Props) {
  const insets = useSafeAreaInsets();
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<ChatMediaUpload[]>([]);
  const [recording, setRecording] = useState(false);
  const recordingRef = useRef<Audio.Recording | null>(null);

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

    const newAttachments: ChatMediaUpload[] = result.assets.map(asset => ({
      localId: `img-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      uri: asset.uri,
      contentType: asset.mimeType || getContentType(asset.uri),
      fileSize: asset.fileSize || 0,
      status: 'pending' as const,
    }));

    setAttachments(prev => [...prev, ...newAttachments].slice(0, 5));
  }, [attachments.length]);

  const handleRemoveAttachment = useCallback((localId: string) => {
    setAttachments(prev => prev.filter(a => a.localId !== localId));
  }, []);

  const handleVoicePress = useCallback(async () => {
    if (recording) {
      // Stop recording and send
      if (!recordingRef.current) return;
      try {
        await recordingRef.current.stopAndUnloadAsync();
        const uri = recordingRef.current.getURI();
        recordingRef.current = null;
        setRecording(false);

        if (!uri) {
          Alert.alert('Error', 'Failed to save recording.');
          return;
        }

        // Get file info for size
        const fileInfo = await getInfoAsync(uri);
        const fileSize = fileInfo.exists ? (fileInfo.size ?? 0) : 0;

        // Upload audio via presigned URL and send as attachment
        const mediaId = await uploadAudio(uri, fileSize);
        const audioAttachment: ChatMediaUpload = {
          localId: `audio-${Date.now()}`,
          uri,
          contentType: 'audio/wav',
          fileSize,
          mediaId,
          status: 'uploaded',
        };
        onSend(text.trim(), [audioAttachment]);
        setText('');
        setAttachments([]);
      } catch (error) {
        console.error('[Voice] Failed to process recording:', error);
        setRecording(false);
        recordingRef.current = null;
        Alert.alert('Error', `Failed to process recording: ${error instanceof Error ? error.message : String(error)}`);
      }
    } else {
      // Start recording
      try {
        const permission = await Audio.requestPermissionsAsync();
        if (!permission.granted) {
          Alert.alert(
            'Permission required',
            'Microphone access is needed to record voice messages.',
          );
          return;
        }

        await Audio.setAudioModeAsync({
          allowsRecordingIOS: true,
          playsInSilentModeIOS: true,
        });

        const {recording: newRecording} = await Audio.Recording.createAsync(
          Audio.RecordingOptionsPresets.HIGH_QUALITY,
        );
        recordingRef.current = newRecording;
        setRecording(true);
      } catch (error) {
        Alert.alert('Error', 'Failed to start recording. Please try again.');
      }
    }
  }, [recording, text, onSend]);

  const canSend = (text.trim().length > 0 || attachments.length > 0) && !disabled;

  // On iOS, add safe area bottom inset + extra padding for thumb reach.
  // On Android, just add a reasonable default padding.
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
      {recording && (
        <View style={styles.recordingIndicator}>
          <Text style={styles.recordingDot}>●</Text>
          <Text style={styles.recordingText}>Recording... Tap mic to stop</Text>
        </View>
      )}
      <View style={styles.container}>
        <TouchableOpacity
          style={styles.attachButton}
          onPress={handlePickImage}
          disabled={disabled || recording}>
          <Text style={[styles.attachIcon, (disabled || recording) && styles.attachIconDisabled]}>
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
          editable={!disabled && !recording}
          onSubmitEditing={handleSend}
          blurOnSubmit={false}
        />
        <TouchableOpacity
          style={[styles.sendButton, !canSend && styles.sendButtonDisabled]}
          onPress={handleSend}
          disabled={!canSend || recording}>
          <Text style={styles.sendText}>Send</Text>
        </TouchableOpacity>
        <VoiceButton
          onPress={handleVoicePress}
          disabled={disabled}
          recording={recording}
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
