import React from 'react';
import {StyleSheet, Text, TouchableOpacity, View} from 'react-native';
import type {Conversation} from '../types';

interface Props {
  conversation: Conversation;
  onPress: (conversationId: string) => void;
  onLongPress?: (conversationId: string) => void;
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

export function ConversationItem({conversation, onPress, onLongPress}: Props) {
  return (
    <TouchableOpacity
      style={styles.container}
      onPress={() => onPress(conversation.conversation_id)}
      onLongPress={() => onLongPress?.(conversation.conversation_id)}>
      <View style={styles.content}>
        <Text style={styles.title} numberOfLines={1}>
          {conversation.title}
        </Text>
        <Text style={styles.date}>{formatDate(conversation.updated_at)}</Text>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E5E5EA',
    backgroundColor: '#FFFFFF',
  },
  content: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  title: {
    flex: 1,
    fontSize: 16,
    color: '#000000',
    marginRight: 8,
  },
  date: {
    fontSize: 13,
    color: '#8E8E93',
  },
});
