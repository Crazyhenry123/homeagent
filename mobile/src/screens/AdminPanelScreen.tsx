import React, {useState} from 'react';
import {
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import {generateInviteCode} from '../services/api';
import type {RootStackParamList} from '../navigation/AppNavigator';

type Props = NativeStackScreenProps<RootStackParamList, 'AdminPanel'>;

export function AdminPanelScreen({navigation}: Props) {
  const [generatingCode, setGeneratingCode] = useState(false);

  const handleGenerateInviteCode = async () => {
    setGeneratingCode(true);
    try {
      const result = await generateInviteCode();
      Alert.alert(
        'Invite Code Created',
        `Share this code with a family member:\n\n${result.code ?? 'Unknown'}`,
        [{text: 'OK'}],
      );
    } catch (err) {
      Alert.alert(
        'Error',
        err instanceof Error ? err.message : 'Failed to generate invite code',
      );
    } finally {
      setGeneratingCode(false);
    }
  };

  return (
    <ScrollView style={styles.container}>
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionHeaderText}>FAMILY MANAGEMENT</Text>
      </View>
      <TouchableOpacity
        style={styles.actionRow}
        onPress={() => navigation.navigate('AdminMembers')}>
        <View style={styles.actionRowContent}>
          <Text style={styles.actionIcon}>👥</Text>
          <View style={styles.actionInfo}>
            <Text style={styles.actionText}>Family Members</Text>
            <Text style={styles.actionSubtext}>View and manage member profiles</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </View>
      </TouchableOpacity>
      <TouchableOpacity
        style={styles.actionRow}
        onPress={() => navigation.navigate('FamilyTree')}>
        <View style={styles.actionRowContent}>
          <Text style={styles.actionIcon}>🌳</Text>
          <View style={styles.actionInfo}>
            <Text style={styles.actionText}>Family Tree</Text>
            <Text style={styles.actionSubtext}>Manage family relationships</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </View>
      </TouchableOpacity>
      <TouchableOpacity
        style={styles.actionRow}
        onPress={() => navigation.navigate('FamilyManage')}>
        <View style={styles.actionRowContent}>
          <Text style={styles.actionIcon}>🏠</Text>
          <View style={styles.actionInfo}>
            <Text style={styles.actionText}>Family & Invites</Text>
            <Text style={styles.actionSubtext}>Manage family members and send invites</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </View>
      </TouchableOpacity>
      <TouchableOpacity
        style={styles.actionRow}
        onPress={handleGenerateInviteCode}
        disabled={generatingCode}>
        <View style={styles.actionRowContent}>
          <Text style={styles.actionIcon}>🔑</Text>
          <View style={styles.actionInfo}>
            <Text style={styles.actionText}>
              {generatingCode ? 'Generating...' : 'Generate Invite Code'}
            </Text>
            <Text style={styles.actionSubtext}>Create a code to invite a new member</Text>
          </View>
        </View>
      </TouchableOpacity>

      <View style={styles.sectionHeader}>
        <Text style={styles.sectionHeaderText}>AGENT MANAGEMENT</Text>
      </View>
      <TouchableOpacity
        style={styles.actionRow}
        onPress={() => navigation.navigate('AdminMembers')}>
        <View style={styles.actionRowContent}>
          <Text style={styles.actionIcon}>🤖</Text>
          <View style={styles.actionInfo}>
            <Text style={styles.actionText}>Agent Configurations</Text>
            <Text style={styles.actionSubtext}>Enable/disable agents per member</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </View>
      </TouchableOpacity>

      <View style={styles.sectionHeader}>
        <Text style={styles.sectionHeaderText}>SYSTEM</Text>
      </View>
      <View style={styles.actionRow}>
        <View style={styles.actionRowContent}>
          <Text style={styles.actionIcon}>ℹ️</Text>
          <View style={styles.actionInfo}>
            <Text style={styles.actionText}>System Info</Text>
            <Text style={styles.actionSubtext}>Agent templates managed via Debug Console</Text>
          </View>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F2F2F7',
  },
  sectionHeader: {
    paddingHorizontal: 16,
    paddingTop: 24,
    paddingBottom: 8,
  },
  sectionHeaderText: {
    fontSize: 13,
    color: '#8E8E93',
    fontWeight: '500',
    letterSpacing: 0.5,
  },
  actionRow: {
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E5E5EA',
  },
  actionRowContent: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  actionIcon: {
    fontSize: 24,
    marginRight: 14,
    width: 32,
    textAlign: 'center',
  },
  actionInfo: {
    flex: 1,
  },
  actionText: {
    fontSize: 16,
    color: '#000000',
    fontWeight: '500',
  },
  actionSubtext: {
    fontSize: 13,
    color: '#8E8E93',
    marginTop: 2,
  },
  chevron: {
    fontSize: 20,
    color: '#C7C7CC',
    marginLeft: 8,
  },
});
