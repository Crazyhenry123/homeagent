import React, {useState, useCallback} from 'react';
import {
  Alert,
  ScrollView,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  View,
  Text,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import {ImageAttachment} from './ImageAttachment';
import {getContentType} from '../services/chatMedia';
import type {ChatMediaUpload} from '../types';

interface Props {
  onSend: (message: string, attachments: ChatMediaUpload[]) => void;
  onVoicePress?: () => void;
  disabled?: boolean;
}

export function ChatInput({onSend, disabled}: Props) {
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<ChatMediaUpload[]>([]);

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

  const canSend = (text.trim().length > 0 || attachments.length > 0) && !disabled;

  return (
    <View style={styles.wrapper}>
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
      <View style={styles.container}>
        <TouchableOpacity
          style={styles.attachButton}
          onPress={handlePickImage}
          disabled={disabled}>
          <Text style={[styles.attachIcon, disabled && styles.attachIconDisabled]}>
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
          editable={!disabled}
          onSubmitEditing={handleSend}
          blurOnSubmit={false}
        />
        <TouchableOpacity
          style={[styles.sendButton, !canSend && styles.sendButtonDisabled]}
          onPress={handleSend}
          disabled={!canSend}>
          <Text style={styles.sendText}>Send</Text>
        </TouchableOpacity>
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
  container: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: 8,
    paddingVertical: 8,
  },
  attachButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
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
    paddingVertical: 8,
    borderRadius: 18,
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
