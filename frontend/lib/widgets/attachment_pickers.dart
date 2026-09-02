import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/contacts_provider.dart';
import '../providers/deals_provider.dart';
import '../providers/organizations_provider.dart';
import '../providers/projects_provider.dart';
import 'record_picker.dart';

/// The four things a document or an interaction can be attached to.
///
/// A record rather than four loose lists so the whole set moves through one
/// callback — the document dialogs and the interaction form all need the same
/// four pickers, and four copies would drift apart.
typedef AttachmentLinks = ({
  List<String> contactIds,
  List<String> organizationIds,
  List<String> dealIds,
  List<String> projectIds,
});

const emptyAttachmentLinks = (
  contactIds: <String>[],
  organizationIds: <String>[],
  dealIds: <String>[],
  projectIds: <String>[],
);

/// Existing links plus the record the form was opened from, without
/// duplicating one that is already linked.
List<String> withInitial(List<String>? existing, String? initial) => [
      ...?existing,
      if (initial != null && !(existing?.contains(initial) ?? false)) initial,
    ];

class AttachmentPickers extends ConsumerWidget {
  const AttachmentPickers({
    super.key,
    required this.value,
    required this.onChanged,
  });

  final AttachmentLinks value;
  final ValueChanged<AttachmentLinks> onChanged;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        RecordPicker(
          label: 'Contacts',
          addLabel: 'Link contact',
          emptyLabel: 'No contact linked yet.',
          optionsAsync: ref
              .watch(allContactsProvider)
              .whenData((cs) => {for (final c in cs) c.id: c.name}),
          selectedIds: value.contactIds,
          onChanged: (ids) => onChanged((
            contactIds: ids,
            organizationIds: value.organizationIds,
            dealIds: value.dealIds,
            projectIds: value.projectIds,
          )),
        ),
        RecordPicker(
          label: 'Organizations',
          addLabel: 'Link organization',
          emptyLabel: 'No organization linked yet.',
          optionsAsync: ref
              .watch(allOrganizationsProvider)
              .whenData((os) => {for (final o in os) o.id: o.name}),
          selectedIds: value.organizationIds,
          onChanged: (ids) => onChanged((
            contactIds: value.contactIds,
            organizationIds: ids,
            dealIds: value.dealIds,
            projectIds: value.projectIds,
          )),
        ),
        RecordPicker(
          label: 'Deals',
          addLabel: 'Link deal',
          emptyLabel: 'No deal linked yet.',
          optionsAsync: ref
              .watch(allDealsProvider)
              .whenData((ds) => {for (final d in ds) d.id: d.title}),
          selectedIds: value.dealIds,
          onChanged: (ids) => onChanged((
            contactIds: value.contactIds,
            organizationIds: value.organizationIds,
            dealIds: ids,
            projectIds: value.projectIds,
          )),
        ),
        RecordPicker(
          label: 'Projects',
          addLabel: 'Link project',
          emptyLabel: 'No project linked yet.',
          optionsAsync: ref
              .watch(allProjectsProvider)
              .whenData((ps) => {for (final p in ps) p.id: p.name}),
          selectedIds: value.projectIds,
          onChanged: (ids) => onChanged((
            contactIds: value.contactIds,
            organizationIds: value.organizationIds,
            dealIds: value.dealIds,
            projectIds: ids,
          )),
        ),
      ],
    );
  }
}
