import React, {useCallback, useLayoutEffect, useMemo, useState} from 'react';
import {
  Alert,
  FlatList,
  Platform,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import {useSafeAreaInsets} from 'react-native-safe-area-context';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import {ConversationItem} from '../components/ConversationItem';
import {deleteConversation} from '../services/api';
import {useSession} from '../store';
import type {RootStackParamList} from '../navigation/AppNavigator';

const REFRESH_THRESHOLD_MS = 30_000; // 30 seconds

type Props = NativeStackScreenProps<RootStackParamList, 'ConversationList'>;

export function ConversationListScreen({navigation}: Props) {
  const insets = useSafeAreaInsets();
  const {session, actions} = useSession();
  const [refreshing, setRefreshing] = useState(false);

  const conversations = useMemo(
    () => session.conversations.items,
    [session.conversations.items],
  );

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

  // Refresh on focus only if stale (> 30s since last fetch)
  React.useEffect(() => {
    const unsubscribe = navigation.addListener('focus', () => {
      const lastFetched = session.conversations.lastFetched;
      if (!lastFetched || Date.now() - lastFetched > REFRESH_THRESHOLD_MS) {
        actions.refreshConversations().catch(() => {
          // Silently ignore refresh errors on focus
        });
      }
    });
    return unsubscribe;
  }, [navigation, session.conversations.lastFetched, actions]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await actions.refreshConversations();
    } catch {
      Alert.alert('Error', 'Failed to load conversations');
    } finally {
      setRefreshing(false);
    }
  }, [actions]);

  const handlePress = useCallback(
    (conversationId: string) => {
      const conv = conversations.find(c => c.conversation_id === conversationId);
      navigation.navigate('Chat', {conversationId, title: conv?.title});
    },
    [conversations, navigation],
  );

  const confirmDelete = useCallback(
    (conversationId: string) => {
      Alert.alert('Delete Conversation', 'Are you sure?', [
        {text: 'Cancel', style: 'cancel'},
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await deleteConversation(conversationId);
              actions.removeConversation(conversationId);
            } catch {
              Alert.alert('Error', 'Failed to delete conversation');
            }
          },
        },
      ]);
    },
    [actions],
  );

  const handleNewChat = useCallback(() => {
    navigation.navigate('Chat', {});
  }, [navigation]);

  return (
    <View style={styles.container}>
      <FlatList
        data={conversations}
        keyExtractor={item => item.conversation_id}
        renderItem={({item}) => (
          <ConversationItem
            conversation={item}
            onPress={handlePress}
            onLongPress={confirmDelete}
          />
        )}
        refreshing={refreshing}
        onRefresh={handleRefresh}
        ListEmptyComponent={
          !refreshing ? (
            <View style={styles.empty}>
              <Text style={styles.emptyText}>No conversations yet</Text>
              <Text style={styles.emptySubtext}>
                Tap + to start chatting
              </Text>
            </View>
          ) : null
        }
      />
      <TouchableOpacity
        style={[
          styles.fab,
          {bottom: Platform.OS === 'ios' ? insets.bottom + 12 : 30},
        ]}
        onPress={handleNewChat}>
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
