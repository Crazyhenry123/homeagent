import React from 'react';
import {StyleSheet, Text, View} from 'react-native';
import {colors} from '../../theme';

interface Props {
  title: string;
  description?: string;
}

export function SectionHeader({title, description}: Props) {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>{title}</Text>
      {description && <Text style={styles.description}>{description}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginBottom: 12,
  },
  title: {
    fontSize: 20,
    fontWeight: '600',
    color: colors.textPrimary,
    marginBottom: 4,
  },
  description: {
    fontSize: 14,
    color: colors.textTertiary,
    lineHeight: 18,
  },
});
