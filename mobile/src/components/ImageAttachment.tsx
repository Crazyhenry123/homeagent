import React from 'react';
import {
  Image,
  StyleSheet,
  TouchableOpacity,
  View,
  Text,
} from 'react-native';
import type {ChatMediaUpload} from '../types';
import {colors} from '../theme';

interface Props {
  attachment: ChatMediaUpload;
  onRemove: (localId: string) => void;
}

export function ImageAttachment({attachment, onRemove}: Props) {
  return (
    <View style={styles.container}>
      <Image source={{uri: attachment.uri}} style={styles.thumbnail} />
      {attachment.status === 'uploading' && (
        <View style={styles.overlay}>
          <Text style={styles.overlayText}>...</Text>
        </View>
      )}
      {attachment.status === 'error' && (
        <View style={[styles.overlay, styles.errorOverlay]}>
          <Text style={styles.overlayText}>!</Text>
        </View>
      )}
      <TouchableOpacity
        style={styles.removeButton}
        onPress={() => onRemove(attachment.localId)}>
        <Text style={styles.removeText}>X</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    width: 64,
    height: 64,
    marginRight: 8,
    borderRadius: 8,
    overflow: 'hidden',
  },
  thumbnail: {
    width: 64,
    height: 64,
    borderRadius: 8,
  },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: colors.overlay,
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: 8,
  },
  errorOverlay: {
    backgroundColor: colors.errorOverlay,
  },
  overlayText: {
    color: colors.surface,
    fontSize: 16,
    fontWeight: '700',
  },
  removeButton: {
    position: 'absolute',
    top: 2,
    right: 2,
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.overlayDark,
    justifyContent: 'center',
    alignItems: 'center',
  },
  removeText: {
    color: colors.surface,
    fontSize: 11,
    fontWeight: '700',
  },
});
