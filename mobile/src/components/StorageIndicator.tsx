import React from 'react';
import {StyleSheet, Text, View} from 'react-native';
import {useSession} from '../store';
import type {StorageProviderType} from '../types';

const PROVIDER_LABELS: Record<StorageProviderType, string> = {
  local: 'HomeAgent Cloud',
  google_drive: 'Google Drive',
  onedrive: 'OneDrive',
  dropbox: 'Dropbox',
  box: 'Box',
};

const PROVIDER_COLORS: Record<StorageProviderType, string> = {
  local: '#34C759',
  google_drive: '#4285F4',
  onedrive: '#0078D4',
  dropbox: '#0061FF',
  box: '#0061D5',
};

export function StorageIndicator() {
  const {session} = useSession();
  const provider = session.storage?.provider ?? 'local';

  return (
    <View style={styles.container}>
      <View style={[styles.dot, {backgroundColor: PROVIDER_COLORS[provider]}]} />
      <Text style={styles.text}>Stored in {PROVIDER_LABELS[provider]}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 4,
    paddingHorizontal: 8,
    backgroundColor: '#F2F2F7',
    borderRadius: 8,
    alignSelf: 'flex-start',
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginRight: 6,
  },
  text: {
    fontSize: 12,
    color: '#8E8E93',
    fontWeight: '500',
  },
});
