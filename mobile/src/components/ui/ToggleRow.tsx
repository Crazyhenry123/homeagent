import React from 'react';
import {StyleSheet, Switch, Text, View} from 'react-native';
import {colors} from '../../theme';

interface Props {
  label: string;
  sublabel?: string;
  description?: string;
  value: boolean;
  onValueChange: (value: boolean) => void;
  disabled?: boolean;
}

export function ToggleRow({label, sublabel, description, value, onValueChange, disabled}: Props) {
  return (
    <View style={styles.container}>
      <View style={styles.content}>
        <Text style={styles.label}>{label}</Text>
        {(sublabel || description) && <Text style={styles.description}>{sublabel || description}</Text>}
      </View>
      <Switch
        value={value}
        onValueChange={onValueChange}
        disabled={disabled}
        trackColor={{false: colors.separator, true: colors.success}}
        thumbColor={colors.surface}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.separator,
  },
  content: {
    flex: 1,
    marginRight: 12,
  },
  label: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.textPrimary,
    marginBottom: 4,
  },
  description: {
    fontSize: 13,
    color: colors.textTertiary,
    lineHeight: 17,
  },
});
