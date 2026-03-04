import React from 'react';
import {StyleSheet, Text, TouchableOpacity} from 'react-native';

interface Props {
  onPress: () => void;
  disabled?: boolean;
  recording?: boolean;
}

export function VoiceButton({onPress, disabled, recording}: Props) {
  return (
    <TouchableOpacity
      style={[
        styles.button,
        recording && styles.buttonRecording,
        disabled && styles.buttonDisabled,
      ]}
      onPress={onPress}
      disabled={disabled}>
      <Text
        style={[
          styles.icon,
          recording && styles.iconRecording,
          disabled && styles.iconDisabled,
        ]}>
        {recording ? '●' : 'mic'}
      </Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  button: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#E9E9EB',
    justifyContent: 'center',
    alignItems: 'center',
    marginLeft: 6,
  },
  buttonRecording: {
    backgroundColor: '#FF3B30',
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  icon: {
    fontSize: 14,
    color: '#007AFF',
    fontWeight: '600',
  },
  iconRecording: {
    color: '#FFFFFF',
    fontSize: 16,
  },
  iconDisabled: {
    color: '#B0B0B0',
  },
});
