import React from 'react';
import {Image, StyleSheet, Text, View} from 'react-native';
import type {MediaInfo, Message} from '../types';

interface DisplayMedia {
  uri: string;
  media_id?: string;
}

interface Props {
  message: Pick<Message, 'role' | 'content'> & {
    media?: MediaInfo[];
    localImages?: DisplayMedia[];
  };
}

export function MessageBubble({message}: Props) {
  const isUser = message.role === 'user';
  const images = message.localImages || [];

  return (
    <View
      style={[
        styles.container,
        isUser ? styles.userContainer : styles.assistantContainer,
      ]}>
      <View
        style={[
          styles.bubble,
          isUser ? styles.userBubble : styles.assistantBubble,
        ]}>
        {images.length > 0 && (
          <View style={styles.imageRow}>
            {images.map((img, idx) => (
              <Image
                key={img.media_id || `img-${idx}`}
                source={{uri: img.uri}}
                style={styles.messageImage}
                resizeMode="cover"
              />
            ))}
          </View>
        )}
        {message.content ? (
          <Text
            style={[
              styles.text,
              isUser ? styles.userText : styles.assistantText,
            ]}
            selectable>
            {message.content}
          </Text>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginVertical: 4,
    marginHorizontal: 12,
  },
  userContainer: {
    alignItems: 'flex-end',
  },
  assistantContainer: {
    alignItems: 'flex-start',
  },
  bubble: {
    maxWidth: '80%',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 18,
  },
  userBubble: {
    backgroundColor: '#007AFF',
    borderBottomRightRadius: 4,
  },
  assistantBubble: {
    backgroundColor: '#E9E9EB',
    borderBottomLeftRadius: 4,
  },
  text: {
    fontSize: 16,
    lineHeight: 22,
  },
  userText: {
    color: '#FFFFFF',
  },
  assistantText: {
    color: '#000000',
  },
  imageRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 4,
    marginBottom: 6,
  },
  messageImage: {
    width: 150,
    height: 150,
    borderRadius: 10,
  },
});
