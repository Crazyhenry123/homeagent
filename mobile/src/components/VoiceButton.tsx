import React from 'react';
import {StyleSheet, TouchableOpacity} from 'react-native';
import {Ionicons} from '@expo/vector-icons';
import {colors} from '../theme';

interface Props {
  onPress: () => void;
  disabled?: boolean;
  recording?: boolean;
}

export function VoiceButton({onPress, disabled, recording}: Props) {
  const iconColor = disabled
    ? colors.disabledText
    : recording
      ? colors.surface
      : colors.primary;

  return (
    <TouchableOpacity
      style={[
        styles.button,
        recording && styles.buttonRecording,
        disabled && styles.buttonDisabled,
      ]}
      onPress={onPress}
      disabled={disabled}>
      <Ionicons
        name={recording ? 'stop' : 'mic'}
        size={20}
        color={iconColor}
      />
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
});
