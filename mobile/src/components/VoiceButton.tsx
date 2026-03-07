import React from 'react';
import {StyleSheet, Text, TouchableOpacity} from 'react-native';
import {colors} from '../theme';

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
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.assistantBubble,
    justifyContent: 'center',
    alignItems: 'center',
    marginLeft: 6,
  },
  buttonRecording: {
    backgroundColor: colors.destructive,
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  icon: {
    fontSize: 14,
    color: colors.primary,
    fontWeight: '600',
  },
  iconRecording: {
    color: colors.surface,
    fontSize: 16,
  },
  iconDisabled: {
    color: colors.disabledText,
  },
});
