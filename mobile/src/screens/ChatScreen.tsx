import React, {useCallback, useEffect, useLayoutEffect, useRef, useState} from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import {ChatInput} from '../components/ChatInput';
import {MessageBubble} from '../components/MessageBubble';
import {getConversations, getMessages} from '../services/api';
import {uploadImage} from '../services/chatMedia';
import {streamChat} from '../services/sse';
import {useSession} from '../store';
import type {ChatMediaUpload, SSEEvent} from '../types';
import type {RootStackParamList} from '../navigation/AppNavigator';
import {colors} from '../theme';

type Props = NativeStackScreenProps<RootStackParamList, 'Chat'>;

interface DisplayMedia {
  uri: string;
  media_id?: string;
}

interface DisplayMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  localImages?: DisplayMedia[];
}

export function ChatScreen({route, navigation}: Props) {
  const conversationId = route.params?.conversationId ?? null;
  const {actions} = useSession();
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(conversationId);
  const [streaming, setStreaming] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const flatListRef = useRef<FlatList<DisplayMessage>>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Set header with title and settings gear icon
  useLayoutEffect(() => {
    navigation.setOptions({
      title: route.params?.title || 'HomeAgent',
      headerRight: () => (
        <TouchableOpacity
          onPress={() => navigation.navigate('Settings')}
          hitSlop={{top: 10, bottom: 10, left: 10, right: 10}}>
          <Text style={{fontSize: 22}}>&#9881;</Text>
        </TouchableOpacity>
      ),
    });
  }, [navigation, route.params?.title]);

  // Auto-load the most recent conversation (single channel mode)
  useEffect(() => {
    setLoadError(null);

    if (conversationId) {
      // Explicit conversation passed — load it directly
      setLoadingMessages(true);
      getMessages(conversationId)
        .then(result => {
          setMessages(
            result.messages.map(m => ({
              id: m.message_id,
              role: m.role,
              content: m.content,
            })),
          );
        })
        .catch(() => setLoadError('Failed to load messages. Please go back and try again.'))
        .finally(() => setLoadingMessages(false));
      return;
    }

    // No conversationId — fetch the most recent conversation
    setLoadingMessages(true);
    getConversations(1)
      .then(result => {
        const latest = result.conversations[0];
        if (latest) {
          setCurrentConversationId(latest.conversation_id);
          return getMessages(latest.conversation_id).then(msgResult => {
            setMessages(
              msgResult.messages.map(m => ({
                id: m.message_id,
                role: m.role,
                content: m.content,
              })),
            );
          });
        }
        // No conversations yet — start fresh
      })
      .catch(() => setLoadError('Failed to load messages. Please go back and try again.'))
      .finally(() => setLoadingMessages(false));
  }, [conversationId]);

  const scrollToEnd = useCallback(() => {
    setTimeout(() => {
      flatListRef.current?.scrollToEnd({animated: true});
    }, 100);
  }, []);

  const handleSend = useCallback(
    async (text: string, attachments: ChatMediaUpload[], isVoice?: boolean) => {
      // Build local images for display (skip audio attachments)
      const imageAttachments = attachments.filter(
        a => !a.contentType.startsWith('audio/'),
      );
      const localImages: DisplayMedia[] = imageAttachments.map(a => ({
        uri: a.uri,
      }));
      const hasAudio = attachments.some(a =>
        a.contentType.startsWith('audio/'),
      );

      // Add user message locally
      const userMsg: DisplayMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: text || (hasAudio ? '🎤 Voice message' : ''),
        localImages: localImages.length > 0 ? localImages : undefined,
      };
      setMessages(prev => [...prev, userMsg]);
      setStreaming(true);
      scrollToEnd();

      // Upload media if any (audio attachments may already have mediaId)
      const mediaIds: string[] = [];
      if (attachments.length > 0) {
        try {
          const uploadPromises = attachments.map(a => {
            if (a.mediaId) return Promise.resolve(a.mediaId);
            return uploadImage(a.uri, a.contentType, a.fileSize);
          });
          const ids = await Promise.all(uploadPromises);
          mediaIds.push(...ids);
        } catch {
          setMessages(prev => [
            ...prev,
            {
              id: `error-${Date.now()}`,
              role: 'assistant',
              content: 'Failed to upload media. Please try again.',
            },
          ]);
          setStreaming(false);
          return;
        }
      }

      // Prepare streaming assistant message
      const assistantId = `assistant-${Date.now()}`;
      setMessages(prev => [
        ...prev,
        {id: assistantId, role: 'assistant', content: ''},
      ]);

      const controller = new AbortController();
      abortRef.current = controller;

      // Track whether this is a new conversation (no ID yet)
      const isNewConversation = !currentConversationId;

      streamChat(
        text,
        currentConversationId,
        (event: SSEEvent) => {
          if (event.type === 'text_delta' && event.content) {
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId
                  ? {...m, content: m.content + event.content}
                  : m,
              ),
            );
            scrollToEnd();
          } else if (event.type === 'message_done') {
            if (event.conversation_id) {
              setCurrentConversationId(event.conversation_id);

              // If a new conversation was created, add it to the session store
              if (isNewConversation) {
                actions.addConversation({
                  conversation_id: event.conversation_id,
                  user_id: '',
                  title: text.slice(0, 50) || 'New conversation',
                  created_at: new Date().toISOString(),
                  updated_at: new Date().toISOString(),
                });
              }
            }
            setStreaming(false);
          } else if (event.type === 'error') {
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId
                  ? {...m, content: event.content || 'An error occurred.'}
                  : m,
              ),
            );
            setStreaming(false);
          }
        },
        () => {
          setStreaming(false);
        },
        controller.signal,
        mediaIds.length > 0 ? mediaIds : undefined,
        isVoice,
      );
    },
    [currentConversationId, scrollToEnd, actions],
  );

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  return (
    <View style={styles.container}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}>
        {loadingMessages ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color={colors.primary} />
          </View>
        ) : loadError ? (
          <View style={styles.loadingContainer}>
            <Text style={styles.errorText}>{loadError}</Text>
          </View>
        ) : (
          <FlatList
            ref={flatListRef}
            data={messages}
            keyExtractor={item => item.id}
            renderItem={({item}) => <MessageBubble message={item} />}
            contentContainerStyle={styles.messageList}
            onContentSizeChange={scrollToEnd}
          />
        )}
        <ChatInput
          onSend={handleSend}
          disabled={streaming || loadingMessages}
        />
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.surface,
  },
  flex: {
    flex: 1,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  errorText: {
    color: colors.destructive,
    fontSize: 16,
    textAlign: 'center',
    paddingHorizontal: 32,
  },
  messageList: {
    paddingVertical: 8,
  },
});
