import React, {useCallback, useEffect, useState} from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Modal,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
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

const RELATIONSHIP_TYPES: RelationshipType[] = [
  'parent_of',
  'child_of',
  'spouse_of',
  'sibling_of',
];

type PickerField = 'user' | 'related' | 'type' | null;

export function FamilyTreeScreen(_props: Props) {
  const [relationships, setRelationships] = useState<FamilyRelationship[]>([]);
  const [members, setMembers] = useState<MemberProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [activePicker, setActivePicker] = useState<PickerField>(null);

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
          const second =
            profileData.profiles.length > 1
              ? profileData.profiles[1]
              : profileData.profiles[0];
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

  const deduped = relationships.filter(rel => {
    if (
      rel.relationship_type === 'spouse_of' ||
      rel.relationship_type === 'sibling_of'
    ) {
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

  const getMemberName = (userId: string): string => {
    const m = members.find(p => p.user_id === userId);
    return m?.display_name ?? userId;
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
          <Text style={styles.relationshipTypeText}>
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
      <ScrollView>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionHeaderText}>ADD RELATIONSHIP</Text>
        </View>

        <View style={styles.formCard}>
          <Text style={styles.fieldLabel}>Person</Text>
          <TouchableOpacity
            style={styles.selectorButton}
            onPress={() => setActivePicker('user')}>
            <Text style={styles.selectorText}>{getMemberName(selectedUser)}</Text>
            <Text style={styles.chevron}>›</Text>
          </TouchableOpacity>

          <Text style={styles.fieldLabel}>Relationship</Text>
          <TouchableOpacity
            style={styles.selectorButton}
            onPress={() => setActivePicker('type')}>
            <Text style={styles.selectorText}>
              {RELATIONSHIP_LABELS[selectedType]}
            </Text>
            <Text style={styles.chevron}>›</Text>
          </TouchableOpacity>

          <Text style={styles.fieldLabel}>Related Person</Text>
          <TouchableOpacity
            style={styles.selectorButton}
            onPress={() => setActivePicker('related')}>
            <Text style={styles.selectorText}>
              {getMemberName(selectedRelated)}
            </Text>
            <Text style={styles.chevron}>›</Text>
          </TouchableOpacity>

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
          deduped.map(item => (
            <View key={`${item.user_id}-${item.related_user_id}`}>
              {renderRelationship({item})}
            </View>
          ))
        )}
      </ScrollView>

      {/* Selection Modal */}
      <Modal
        visible={activePicker !== null}
        transparent
        animationType="slide"
        onRequestClose={() => setActivePicker(null)}>
        <TouchableOpacity
          style={styles.modalOverlay}
          activeOpacity={1}
          onPress={() => setActivePicker(null)}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>
                {activePicker === 'user'
                  ? 'Select Person'
                  : activePicker === 'related'
                    ? 'Select Related Person'
                    : 'Select Relationship'}
              </Text>
              <TouchableOpacity onPress={() => setActivePicker(null)}>
                <Text style={styles.modalDone}>Done</Text>
              </TouchableOpacity>
            </View>
            <FlatList
              data={
                activePicker === 'type'
                  ? RELATIONSHIP_TYPES.map(t => ({id: t, label: RELATIONSHIP_LABELS[t]}))
                  : members.map(m => ({id: m.user_id, label: m.display_name}))
              }
              keyExtractor={item => item.id}
              renderItem={({item}) => {
                const isSelected =
                  activePicker === 'user'
                    ? item.id === selectedUser
                    : activePicker === 'related'
                      ? item.id === selectedRelated
                      : item.id === selectedType;
                return (
                  <TouchableOpacity
                    style={[
                      styles.modalOption,
                      isSelected && styles.modalOptionSelected,
                    ]}
                    onPress={() => {
                      if (activePicker === 'user') setSelectedUser(item.id);
                      else if (activePicker === 'related') setSelectedRelated(item.id);
                      else if (activePicker === 'type')
                        setSelectedType(item.id as RelationshipType);
                      setActivePicker(null);
                    }}>
                    <Text
                      style={[
                        styles.modalOptionText,
                        isSelected && styles.modalOptionTextSelected,
                      ]}>
                      {item.label}
                    </Text>
                    {isSelected && <Text style={styles.checkmark}>✓</Text>}
                  </TouchableOpacity>
                );
              }}
            />
          </View>
        </TouchableOpacity>
      </Modal>
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
  fieldLabel: {
    fontSize: 13,
    color: '#8E8E93',
    marginBottom: 4,
    marginTop: 12,
  },
  selectorButton: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#E5E5EA',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 12,
  },
  selectorText: {
    flex: 1,
    fontSize: 16,
    color: '#000000',
  },
  chevron: {
    fontSize: 20,
    color: '#C7C7CC',
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
  relationshipTypeText: {
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
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 14,
    borderTopRightRadius: 14,
    maxHeight: '50%',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E5E5EA',
  },
  modalTitle: {
    fontSize: 17,
    fontWeight: '600',
    color: '#000000',
  },
  modalDone: {
    fontSize: 17,
    fontWeight: '600',
    color: '#007AFF',
  },
  modalOption: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E5E5EA',
  },
  modalOptionSelected: {
    backgroundColor: '#F2F2F7',
  },
  modalOptionText: {
    flex: 1,
    fontSize: 16,
    color: '#000000',
  },
  modalOptionTextSelected: {
    color: '#007AFF',
    fontWeight: '600',
  },
  checkmark: {
    fontSize: 17,
    color: '#007AFF',
    fontWeight: '600',
  },
});
