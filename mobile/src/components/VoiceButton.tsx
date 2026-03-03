import React from 'react';
import {StyleSheet, Text, TouchableOpacity} from 'react-native';

interface Props {
  onPress: () => void;
  disabled?: boolean;
}

export function VoiceButton({onPress, disabled}: Props) {
  return (
    <TouchableOpacity
      style={[styles.button, disabled && styles.buttonDisabled]}
      onPress={onPress}
      disabled={disabled}>
      <Text style={[styles.icon, disabled && styles.iconDisabled]}>mic</Text>
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
  buttonDisabled: {
    opacity: 0.5,
  },
  icon: {
    fontSize: 14,
    color: '#007AFF',
    fontWeight: '600',
  },
  iconDisabled: {
    color: '#B0B0B0',
  },
});
