import React, {useEffect, useState} from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Modal,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import type {NativeStackScreenProps} from '@react-navigation/native-stack';
import {
  createRelationship,
  deleteRelationship,
  getUserRelationships,
  listProfiles,
} from '../services/api';
import {useSession} from '../store';
import type {RootStackParamList} from '../navigation/AppNavigator';
import type {MemberProfile, RelationshipType} from '../types';
import {colors} from '../theme';

type Props = NativeStackScreenProps<RootStackParamList, 'FamilyTree'>;

type RelationshipOption = RelationshipType | 'none';

const RELATIONSHIP_OPTIONS: {value: RelationshipOption; label: string}[] = [
  {value: 'none', label: 'No relationship'},
  {value: 'parent_of', label: 'My child'},
  {value: 'child_of', label: 'My parent'},
  {value: 'spouse_of', label: 'My spouse / partner'},
  {value: 'sibling_of', label: 'My sibling'},
];

function getLabelForType(type: RelationshipOption): string {
  return RELATIONSHIP_OPTIONS.find(o => o.value === type)?.label ?? 'No relationship';
}

export function FamilyTreeScreen(_props: Props) {
  const {session} = useSession();
  const currentUserId = session.user?.userId ?? '';

  const [members, setMembers] = useState<MemberProfile[]>([]);
  const [relationshipMap, setRelationshipMap] = useState<
    Record<string, RelationshipType>
  >({});
  const [loading, setLoading] = useState(true);
  const [savingFor, setSavingFor] = useState<string | null>(null);
  const [pickerMember, setPickerMember] = useState<MemberProfile | null>(null);

  useEffect(() => {
    if (!currentUserId) return;

    (async () => {
      try {
        const profileData = await listProfiles();

        const otherMembers = profileData.profiles.filter(
          p => p.user_id !== currentUserId,
        );
        setMembers(otherMembers);

        const relData = await getUserRelationships(currentUserId);
        const map: Record<string, RelationshipType> = {};
        for (const rel of relData.relationships) {
          map[rel.related_user_id] = rel.relationship_type;
        }
        setRelationshipMap(map);
      } catch (err) {
        Alert.alert(
          'Error',
          err instanceof Error ? err.message : 'Failed to load family data',
        );
      } finally {
        setLoading(false);
      }
    })();
  }, [currentUserId]);

  const handleSetRelationship = async (
    memberId: string,
    type: RelationshipOption,
  ) => {
    setPickerMember(null);
    setSavingFor(memberId);
    try {
      const currentType = relationshipMap[memberId];

      if (type === 'none') {
        if (currentType) {
          await deleteRelationship(currentUserId, memberId);
          setRelationshipMap(prev => {
            const next = {...prev};
            delete next[memberId];
            return next;
          });
        }
      } else {
        // Delete existing first if changing type
        if (currentType) {
          await deleteRelationship(currentUserId, memberId);
        }
        await createRelationship(currentUserId, memberId, type);
        setRelationshipMap(prev => ({...prev, [memberId]: type}));
      }
    } catch (err) {
      Alert.alert(
        'Error',
        err instanceof Error ? err.message : 'Failed to save relationship',
      );
    } finally {
      setSavingFor(null);
    }
  };

  if (loading) {
    return (
      <View style={[styles.container, styles.centered]}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  if (members.length === 0) {
    return (
      <View style={[styles.container, styles.centered]}>
        <Text style={styles.emptyText}>
          No other family members yet. Invite members first.
        </Text>
      </View>
    );
  }

  const renderMember = ({item}: {item: MemberProfile}) => {
    const currentType: RelationshipOption =
      (relationshipMap[item.user_id] as RelationshipOption | undefined) ?? 'none';
    const isSaving = savingFor === item.user_id;

    return (
      <TouchableOpacity
        style={styles.memberRow}
        onPress={() => setPickerMember(item)}
        disabled={isSaving}>
        <View style={styles.memberInfo}>
          <Text style={styles.memberName}>{item.display_name}</Text>
          <View style={styles.relationshipBadge}>
            {isSaving ? (
              <ActivityIndicator size="small" color="#007AFF" />
            ) : (
              <Text
                style={[
                  styles.relationshipLabel,
                  currentType !== 'none' && styles.relationshipLabelActive,
                ]}>
                {getLabelForType(currentType)}
              </Text>
            )}
          </View>
        </View>
        <Text style={styles.chevron}>›</Text>
      </TouchableOpacity>
    );
  };

  return (
    <View style={styles.container}>
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionHeaderText}>
          FAMILY MEMBERS
        </Text>
      </View>
      <Text style={styles.hint}>
        Tap a member to set their relationship to you.
      </Text>

      <FlatList
        data={members}
        keyExtractor={item => item.user_id}
        renderItem={renderMember}
      />

      {/* Relationship picker modal */}
      <Modal
        visible={pickerMember !== null}
        transparent
        animationType="slide"
        onRequestClose={() => setPickerMember(null)}>
        <TouchableOpacity
          style={styles.modalOverlay}
          activeOpacity={1}
          onPress={() => setPickerMember(null)}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>
                {pickerMember?.display_name}
              </Text>
              <TouchableOpacity onPress={() => setPickerMember(null)}>
                <Text style={styles.modalDone}>Cancel</Text>
              </TouchableOpacity>
            </View>
            {RELATIONSHIP_OPTIONS.map(option => {
              const isSelected =
                (relationshipMap[pickerMember?.user_id ?? ''] ?? 'none') ===
                option.value;
              return (
                <TouchableOpacity
                  key={option.value}
                  style={[
                    styles.modalOption,
                    isSelected && styles.modalOptionSelected,
                  ]}
                  onPress={() =>
                    pickerMember &&
                    handleSetRelationship(pickerMember.user_id, option.value)
                  }>
                  <Text
                    style={[
                      styles.modalOptionText,
                      isSelected && styles.modalOptionTextSelected,
                    ]}>
                    {option.label}
                  </Text>
                  {isSelected && <Text style={styles.checkmark}>✓</Text>}
                </TouchableOpacity>
              );
            })}
          </View>
        </TouchableOpacity>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  hint: {
    paddingHorizontal: 16,
    paddingBottom: 12,
    fontSize: 13,
    color: colors.textTertiary,
  },
  memberRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separator,
  },
  memberInfo: {
    flex: 1,
    marginLeft: 12,
  },
  memberName: {
    fontSize: 16,
    color: colors.textPrimary,
    fontWeight: '500',
  },
  relationshipBadge: {
    marginTop: 4,
  },
  relationshipLabel: {
    fontSize: 14,
    color: colors.textTertiary,
  },
  relationshipLabelActive: {
    color: colors.primary,
    fontWeight: '500',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: colors.overlay,
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: 14,
    borderTopRightRadius: 14,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separator,
  },
  modalTitle: {
    fontSize: 17,
    fontWeight: '600',
    color: colors.textPrimary,
  },
  modalDone: {
    fontSize: 17,
    color: colors.primary,
  },
  modalOption: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separator,
  },
  modalOptionSelected: {
    backgroundColor: colors.background,
  },
  modalOptionText: {
    flex: 1,
    fontSize: 16,
    color: colors.textPrimary,
  },
  modalOptionTextSelected: {
    color: colors.primary,
    fontWeight: '600',
  },
  sectionHeader: {
    paddingHorizontal: 16,
    paddingTop: 24,
    paddingBottom: 4,
  },
  sectionHeaderText: {
    fontSize: 13,
    color: colors.textTertiary,
    fontWeight: '500' as const,
    letterSpacing: 0.5,
  },
  chevron: {
    fontSize: 20,
    color: colors.chevron,
    marginLeft: 8,
  },
  emptyText: {
    fontSize: 15,
    color: colors.textTertiary,
    textAlign: 'center' as const,
  },
  checkmark: {
    fontSize: 17,
    color: colors.primary,
    fontWeight: '600' as const,
  },
});
