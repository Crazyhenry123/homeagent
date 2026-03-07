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
import {Ionicons} from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import {ImageAttachment} from './ImageAttachment';
import {VoiceButton} from './VoiceButton';
import {getContentType, uploadAudio} from '../services/chatMedia';
import type {ChatMediaUpload} from '../types';

interface Props {
  onSend: (message: string, attachments: ChatMediaUpload[], isVoice?: boolean) => void;
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
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
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
    if (recording) {
      if (!recordingRef.current) return;
      try {
        await recordingRef.current.stopAndUnloadAsync();
        const uri = recordingRef.current.getURI();
        recordingRef.current = null;
        setRecording(false);
        await Audio.setAudioModeAsync({allowsRecordingIOS: false});

        if (!uri) {
          Alert.alert('Error', 'Failed to save recording.');
          return;
        }

        const fileInfo = await getInfoAsync(uri);
        const fileSize = fileInfo.exists ? (fileInfo.size ?? 0) : 0;

        const mediaId = await uploadAudio(uri, fileSize);
        const audioAttachment: ChatMediaUpload = {
          localId: `audio-${Date.now()}`,
          uri,
          contentType: 'audio/wav',
          fileSize,
          mediaId,
          status: 'uploaded',
        };
        onSend(text.trim(), [audioAttachment], true);
        setText('');
        setAttachments([]);
      } catch (error) {
        console.error('[Voice] Failed to process recording:', error);
        setRecording(false);
        recordingRef.current = null;
        Audio.setAudioModeAsync({allowsRecordingIOS: false}).catch(() => {});
        Alert.alert(
          'Error',
          `Failed to process recording: ${error instanceof Error ? error.message : String(error)}`,
        );
      }
    } else {
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

        const wavPreset: Audio.RecordingOptions = {
          isMeteringEnabled: false,
          android: {
            extension: '.wav',
            outputFormat: Audio.AndroidOutputFormat.DEFAULT,
            audioEncoder: Audio.AndroidAudioEncoder.DEFAULT,
            sampleRate: 44100,
            numberOfChannels: 1,
            bitRate: 128000,
          },
          ios: {
            extension: '.wav',
            outputFormat: Audio.IOSOutputFormat.LINEARPCM,
            audioQuality: Audio.IOSAudioQuality.HIGH,
            sampleRate: 44100,
            numberOfChannels: 1,
            bitRate: 128000,
            linearPCMBitDepth: 16,
            linearPCMIsBigEndian: false,
            linearPCMIsFloat: false,
          },
          web: {
            mimeType: 'audio/wav',
            bitsPerSecond: 128000,
          },
        };
        const {recording: newRecording} = await Audio.Recording.createAsync(
          wavPreset,
        );
        recordingRef.current = newRecording;
        setRecording(true);
      } catch (_error) {
        Audio.setAudioModeAsync({allowsRecordingIOS: false}).catch(() => {});
        Alert.alert('Error', 'Failed to start recording. Please try again.');
      }
    }
  }, [recording, text, onSend]);

  const showSend = text.trim().length > 0 || attachments.length > 0;

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
          <Ionicons name="radio" size={14} color="#FF3B30" style={{marginRight: 6}} />
          <Text style={styles.recordingText}>Recording... Tap mic to stop & send</Text>
        </View>
      )}
      <View style={styles.container}>
        <TouchableOpacity
          style={styles.attachButton}
          onPress={handlePickImage}
          disabled={disabled || recording}>
          <Ionicons
            name="image-outline"
            size={22}
            color={disabled || recording ? '#C7C7CC' : '#007AFF'}
          />
        </TouchableOpacity>
        <TextInput
          style={styles.input}
          value={text}
          onChangeText={setText}
          placeholder="Type a message..."
          placeholderTextColor="#3C3C43"
          multiline
          maxLength={4000}
          editable={!disabled && !recording}
          onSubmitEditing={handleSend}
          blurOnSubmit={false}
        />
        {showSend ? (
          <TouchableOpacity
            style={[styles.sendButton, !showSend && styles.sendButtonDisabled]}
            onPress={handleSend}
            disabled={!showSend || recording}>
            <Ionicons name="arrow-up" size={20} color="#FFFFFF" />
          </TouchableOpacity>
        ) : (
          <VoiceButton
            onPress={handleVoicePress}
            disabled={disabled}
            recording={recording}
          />
        )}
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
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#007AFF',
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendButtonDisabled: {
    backgroundColor: '#E5E5EA',
  },
});
