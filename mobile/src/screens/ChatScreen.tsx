import React, {useCallback, useEffect, useRef, useState} from 'react';
import {FlatList, StyleSheet, View} from 'react-native';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import {ChatInput} from '../components/ChatInput';
import {MessageBubble} from '../components/MessageBubble';
import {getMessages} from '../services/api';
import {streamChat} from '../services/sse';
import type {Message, SSEEvent} from '../types';
import type {RootStackParamList} from '../navigation/AppNavigator';

type Props = NativeStackScreenProps<RootStackParamList, 'Chat'>;

interface DisplayMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

export function ChatScreen({route}: Props) {
  const conversationId = route.params?.conversationId ?? null;
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(conversationId);
  const [streaming, setStreaming] = useState(false);
  const flatListRef = useRef<FlatList<DisplayMessage>>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Load existing messages
  useEffect(() => {
    if (!conversationId) return;

    getMessages(conversationId).then(result => {
      setMessages(
        result.messages.map(m => ({
          id: m.message_id,
          role: m.role,
          content: m.content,
        })),
      );
    });
  }, [conversationId]);

  const scrollToEnd = useCallback(() => {
    setTimeout(() => {
      flatListRef.current?.scrollToEnd({animated: true});
    }, 100);
  }, []);

  const handleSend = useCallback(
    (text: string) => {
      // Add user message locally
      const userMsg: DisplayMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: text,
      };
      setMessages(prev => [...prev, userMsg]);
      setStreaming(true);
      scrollToEnd();

      // Prepare streaming assistant message
      const assistantId = `assistant-${Date.now()}`;
      setMessages(prev => [
        ...prev,
        {id: assistantId, role: 'assistant', content: ''},
      ]);

      const controller = new AbortController();
      abortRef.current = controller;

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
      );
    },
    [currentConversationId, scrollToEnd],
  );

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  return (
    <View style={styles.container}>
      <FlatList
        ref={flatListRef}
        data={messages}
        keyExtractor={item => item.id}
        renderItem={({item}) => <MessageBubble message={item} />}
        contentContainerStyle={styles.messageList}
        onContentSizeChange={scrollToEnd}
      />
      <ChatInput onSend={handleSend} disabled={streaming} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  messageList: {
    paddingVertical: 8,
  },
});
