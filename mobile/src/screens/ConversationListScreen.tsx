import React, {useCallback, useEffect, useLayoutEffect, useState} from 'react';
import {
  Alert,
  FlatList,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import {ConversationItem} from '../components/ConversationItem';
import {deleteConversation, getConversations} from '../services/api';
import type {Conversation} from '../types';
import type {RootStackParamList} from '../navigation/AppNavigator';

type Props = NativeStackScreenProps<RootStackParamList, 'ConversationList'>;

export function ConversationListScreen({navigation}: Props) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <TouchableOpacity
          onPress={() => navigation.navigate('Settings')}
          hitSlop={{top: 10, bottom: 10, left: 10, right: 10}}>
          <Text style={styles.headerButton}>Settings</Text>
        </TouchableOpacity>
      ),
    });
  }, [navigation]);

  const loadConversations = useCallback(async () => {
    try {
      const result = await getConversations();
      setConversations(result.conversations);
    } catch (err) {
      Alert.alert('Error', 'Failed to load conversations');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const unsubscribe = navigation.addListener('focus', loadConversations);
    return unsubscribe;
  }, [navigation, loadConversations]);

  const handlePress = (conversationId: string) => {
    const conv = conversations.find(c => c.conversation_id === conversationId);
    navigation.navigate('Chat', {conversationId, title: conv?.title});
  };

  const handleDelete = (conversationId: string) => {
    Alert.alert('Delete Conversation', 'Are you sure?', [
      {text: 'Cancel', style: 'cancel'},
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          await deleteConversation(conversationId);
          setConversations(prev =>
            prev.filter(c => c.conversation_id !== conversationId),
          );
        },
      },
    ]);
  };

  const handleNewChat = () => {
    navigation.navigate('Chat', {});
  };

  return (
    <View style={styles.container}>
      <FlatList
        data={conversations}
        keyExtractor={item => item.conversation_id}
        renderItem={({item}) => (
          <ConversationItem
            conversation={item}
            onPress={handlePress}
            onLongPress={handleDelete}
          />
        )}
        refreshing={loading}
        onRefresh={loadConversations}
        ListEmptyComponent={
          !loading ? (
            <View style={styles.empty}>
              <Text style={styles.emptyText}>No conversations yet</Text>
              <Text style={styles.emptySubtext}>
                Tap + to start chatting
              </Text>
            </View>
          ) : null
        }
      />
      <TouchableOpacity style={styles.fab} onPress={handleNewChat}>
        <Text style={styles.fabText}>+</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F2F2F7',
  },
  headerButton: {
    color: '#007AFF',
    fontSize: 16,
  },
  empty: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 100,
  },
  emptyText: {
    fontSize: 18,
    color: '#8E8E93',
    marginBottom: 4,
  },
  emptySubtext: {
    fontSize: 14,
    color: '#AEAEB2',
  },
  fab: {
    position: 'absolute',
    right: 20,
    bottom: 30,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#007AFF',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 2},
    shadowOpacity: 0.25,
    shadowRadius: 4,
    elevation: 5,
  },
  fabText: {
    color: '#FFFFFF',
    fontSize: 28,
    fontWeight: '400',
    marginTop: -2,
  },
});
