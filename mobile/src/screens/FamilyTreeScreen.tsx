import React, {useCallback, useEffect, useState} from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import {Picker} from '@react-native-picker/picker';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import {
  createRelationship,
  deleteRelationship,
  getFamilyRelationships,
  listProfiles,
} from '../services/api';
import type {RootStackParamList} from '../navigation/AppNavigator';
import type {FamilyRelationship, MemberProfile, RelationshipType} from '../types';

type Props = NativeStackScreenProps<RootStackParamList, 'FamilyTree'>;

const RELATIONSHIP_LABELS: Record<RelationshipType, string> = {
  parent_of: 'is parent of',
  child_of: 'is child of',
  spouse_of: 'is spouse of',
  sibling_of: 'is sibling of',
};

export function FamilyTreeScreen(_props: Props) {
  const [relationships, setRelationships] = useState<FamilyRelationship[]>([]);
  const [members, setMembers] = useState<MemberProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);

  const [selectedUser, setSelectedUser] = useState('');
  const [selectedRelated, setSelectedRelated] = useState('');
  const [selectedType, setSelectedType] = useState<RelationshipType>('parent_of');

  const loadData = useCallback(async () => {
    try {
      const [relData, profileData] = await Promise.all([
        getFamilyRelationships(),
        listProfiles(),
      ]);
      setRelationships(relData.relationships);
      setMembers(profileData.profiles);
      if (profileData.profiles.length > 0) {
        if (!selectedUser) setSelectedUser(profileData.profiles[0].user_id);
        if (!selectedRelated) {
          const second = profileData.profiles.length > 1 ? profileData.profiles[1] : profileData.profiles[0];
          setSelectedRelated(second.user_id);
        }
      }
    } catch (err) {
      Alert.alert(
        'Error',
        err instanceof Error ? err.message : 'Failed to load data',
      );
    } finally {
      setLoading(false);
    }
  }, [selectedUser, selectedRelated]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Deduplicate: for symmetric types (spouse_of, sibling_of) only show one direction
  const deduped = relationships.filter(rel => {
    if (rel.relationship_type === 'spouse_of' || rel.relationship_type === 'sibling_of') {
      return rel.user_id < rel.related_user_id;
    }
    return true;
  });

  const handleAdd = async () => {
    if (selectedUser === selectedRelated) {
      Alert.alert('Error', 'Cannot create a relationship with the same person.');
      return;
    }
    setAdding(true);
    try {
      await createRelationship(selectedUser, selectedRelated, selectedType);
      await loadData();
    } catch (err) {
      Alert.alert(
        'Error',
        err instanceof Error ? err.message : 'Failed to create relationship',
      );
    } finally {
      setAdding(false);
    }
  };

  const handleDelete = (userId: string, relatedUserId: string) => {
    Alert.alert(
      'Remove Relationship',
      'Are you sure you want to remove this relationship?',
      [
        {text: 'Cancel', style: 'cancel'},
        {
          text: 'Remove',
          style: 'destructive',
          onPress: async () => {
            try {
              await deleteRelationship(userId, relatedUserId);
              await loadData();
            } catch (err) {
              Alert.alert(
                'Error',
                err instanceof Error ? err.message : 'Failed to remove',
              );
            }
          },
        },
      ],
    );
  };

  if (loading) {
    return (
      <View style={[styles.container, styles.centered]}>
        <ActivityIndicator size="large" color="#007AFF" />
      </View>
    );
  }

  const renderRelationship = ({item}: {item: FamilyRelationship}) => (
    <View style={styles.relationshipRow}>
      <View style={styles.relationshipInfo}>
        <Text style={styles.relationshipText}>
          {item.user_name ?? item.user_id}{' '}
          <Text style={styles.relationshipType}>
            {RELATIONSHIP_LABELS[item.relationship_type] ?? item.relationship_type}
          </Text>{' '}
          {item.related_user_name ?? item.related_user_id}
        </Text>
      </View>
      <TouchableOpacity
        style={styles.deleteIcon}
        onPress={() => handleDelete(item.user_id, item.related_user_id)}>
        <Text style={styles.deleteIconText}>×</Text>
      </TouchableOpacity>
    </View>
  );

  return (
    <View style={styles.container}>
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionHeaderText}>ADD RELATIONSHIP</Text>
      </View>

      <View style={styles.formCard}>
        <Text style={styles.pickerLabel}>Person</Text>
        <View style={styles.pickerContainer}>
          <Picker
            selectedValue={selectedUser}
            onValueChange={setSelectedUser}
            style={styles.picker}>
            {members.map(m => (
              <Picker.Item
                key={m.user_id}
                label={m.display_name}
                value={m.user_id}
              />
            ))}
          </Picker>
        </View>

        <Text style={styles.pickerLabel}>Relationship</Text>
        <View style={styles.pickerContainer}>
          <Picker
            selectedValue={selectedType}
            onValueChange={val => setSelectedType(val as RelationshipType)}
            style={styles.picker}>
            {(Object.keys(RELATIONSHIP_LABELS) as RelationshipType[]).map(
              type => (
                <Picker.Item
                  key={type}
                  label={RELATIONSHIP_LABELS[type]}
                  value={type}
                />
              ),
            )}
          </Picker>
        </View>

        <Text style={styles.pickerLabel}>Related Person</Text>
        <View style={styles.pickerContainer}>
          <Picker
            selectedValue={selectedRelated}
            onValueChange={setSelectedRelated}
            style={styles.picker}>
            {members.map(m => (
              <Picker.Item
                key={m.user_id}
                label={m.display_name}
                value={m.user_id}
              />
            ))}
          </Picker>
        </View>

        <TouchableOpacity
          style={[styles.addButton, adding && styles.addButtonDisabled]}
          onPress={handleAdd}
          disabled={adding}>
          <Text style={styles.addButtonText}>
            {adding ? 'Adding...' : 'Add Relationship'}
          </Text>
        </TouchableOpacity>
      </View>

      <View style={styles.sectionHeader}>
        <Text style={styles.sectionHeaderText}>EXISTING RELATIONSHIPS</Text>
      </View>

      {deduped.length === 0 ? (
        <View style={styles.emptyState}>
          <Text style={styles.emptyText}>No relationships defined yet.</Text>
        </View>
      ) : (
        <FlatList
          data={deduped}
          keyExtractor={item => `${item.user_id}-${item.related_user_id}`}
          renderItem={renderRelationship}
          style={styles.list}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F2F2F7',
  },
  centered: {
    justifyContent: 'center',
    alignItems: 'center',
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
  formCard: {
    backgroundColor: '#FFFFFF',
    marginHorizontal: 16,
    borderRadius: 10,
    padding: 16,
  },
  pickerLabel: {
    fontSize: 13,
    color: '#8E8E93',
    marginBottom: 4,
    marginTop: 8,
  },
  pickerContainer: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#E5E5EA',
    borderRadius: 8,
    overflow: 'hidden',
  },
  picker: {
    height: 50,
  },
  addButton: {
    marginTop: 16,
    height: 44,
    borderRadius: 10,
    backgroundColor: '#007AFF',
    justifyContent: 'center',
    alignItems: 'center',
  },
  addButtonDisabled: {
    opacity: 0.6,
  },
  addButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  list: {
    flex: 1,
  },
  relationshipRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E5E5EA',
  },
  relationshipInfo: {
    flex: 1,
  },
  relationshipText: {
    fontSize: 16,
    color: '#000000',
  },
  relationshipType: {
    color: '#8E8E93',
    fontStyle: 'italic',
  },
  deleteIcon: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#FF3B30',
    justifyContent: 'center',
    alignItems: 'center',
  },
  deleteIconText: {
    color: '#FFFFFF',
    fontSize: 20,
    fontWeight: '600',
    lineHeight: 22,
  },
  emptyState: {
    padding: 32,
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 15,
    color: '#8E8E93',
  },
});
