import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/project.dart';
import '../providers/projects_provider.dart';

class ProjectFormPage extends ConsumerStatefulWidget {
  const ProjectFormPage({super.key, this.project});

  final Project? project;

  @override
  ConsumerState<ProjectFormPage> createState() => _ProjectFormPageState();
}

class _ProjectFormPageState extends ConsumerState<ProjectFormPage>
    with SingleTickerProviderStateMixin {
  final _formKey = GlobalKey<FormState>();
  bool _saving = false;

  late final TextEditingController _name;
  late final TextEditingController _description;
  late final TabController _descTabController;
  DateTime? _startDate;
  DateTime? _endDate;

  bool get _isEdit => widget.project != null;

  @override
  void initState() {
    super.initState();
    final p = widget.project;
    _name = TextEditingController(text: p?.name);
    _description = TextEditingController(text: p?.description);
    _descTabController = TabController(length: 2, vsync: this);
    _startDate = p?.startDate;
    _endDate = p?.endDate;
  }

  @override
  void dispose() {
    _name.dispose();
    _description.dispose();
    _descTabController.dispose();
    super.dispose();
  }

  String _ymd(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  Future<void> _pickDate({required bool isStart}) async {
    final now = DateTime.now();
    final initial = isStart ? (_startDate ?? now) : (_endDate ?? _startDate ?? now);
    final date = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(now.year - 5),
      lastDate: DateTime(now.year + 10),
    );
    if (date == null || !mounted) return;
    setState(() {
      if (isStart) {
        _startDate = date;
        if (_endDate != null && _endDate!.isBefore(date)) _endDate = null;
      } else {
        _endDate = date;
      }
    });
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);

    final body = <String, dynamic>{
      'name': _name.text,
      if (_description.text.isNotEmpty) 'description': _description.text,
      'start_date': _ymd(_startDate!),
      'end_date': _endDate == null ? null : _ymd(_endDate!),
    };

    final repo = ref.read(projectsRepositoryProvider);
    if (_isEdit) {
      await repo.update(widget.project!.id, body);
    } else {
      await repo.create(body);
    }

    ref.invalidate(projectsProvider);
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_isEdit ? 'Edit Project' : 'New Project')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: TextFormField(
                controller: _name,
                decoration: const InputDecoration(
                  labelText: 'Name',
                  border: OutlineInputBorder(),
                ),
                validator: (v) =>
                    (v == null || v.isEmpty) ? 'Name is required' : null,
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: InputDecorator(
                decoration: const InputDecoration(
                  border: OutlineInputBorder(),
                  contentPadding: EdgeInsets.zero,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    TabBar(
                      controller: _descTabController,
                      tabs: const [Tab(text: 'Edit'), Tab(text: 'Preview')],
                      dividerColor: Colors.transparent,
                    ),
                    const Divider(height: 1),
                    SizedBox(
                      height: 180,
                      child: TabBarView(
                        controller: _descTabController,
                        children: [
                          Padding(
                            padding: const EdgeInsets.all(8),
                            child: TextField(
                              controller: _description,
                              maxLines: null,
                              expands: true,
                              decoration: const InputDecoration.collapsed(
                                hintText: 'Description (Markdown supported)',
                              ),
                            ),
                          ),
                          SingleChildScrollView(
                            padding: const EdgeInsets.all(12),
                            child: ListenableBuilder(
                              listenable: _description,
                              builder: (context, _) {
                                final text = _description.text;
                                return text.isEmpty
                                    ? const Text(
                                        'Nothing to preview.',
                                        style: TextStyle(color: Colors.grey),
                                      )
                                    : MarkdownBody(data: text);
                              },
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: InputDecorator(
                decoration: const InputDecoration(
                  labelText: 'Start date *',
                  border: OutlineInputBorder(),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        _startDate == null ? 'Required' : _ymd(_startDate!),
                        style: _startDate == null
                            ? const TextStyle(color: Colors.grey)
                            : null,
                      ),
                    ),
                    TextButton(
                      onPressed: () => _pickDate(isStart: true),
                      child: const Text('Pick'),
                    ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: InputDecorator(
                decoration: const InputDecoration(
                  labelText: 'End date',
                  border: OutlineInputBorder(),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        _endDate == null ? 'No end date' : _ymd(_endDate!),
                        style: _endDate == null
                            ? const TextStyle(color: Colors.grey)
                            : null,
                      ),
                    ),
                    if (_endDate != null)
                      IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () => setState(() => _endDate = null),
                      ),
                    TextButton(
                      onPressed: () => _pickDate(isStart: false),
                      child: const Text('Pick'),
                    ),
                  ],
                ),
              ),
            ),
            FilledButton(
              onPressed: (_saving || _startDate == null) ? null : _save,
              child: _saving
                  ? const CircularProgressIndicator()
                  : const Text('Save'),
            ),
          ],
        ),
      ),
    );
  }
}
