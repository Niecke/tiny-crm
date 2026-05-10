import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/task.dart';
import '../providers/tasks_provider.dart';

class TaskFormPage extends ConsumerStatefulWidget {
  const TaskFormPage({super.key, this.task});

  final Task? task;

  @override
  ConsumerState<TaskFormPage> createState() => _TaskFormPageState();
}

class _TaskFormPageState extends ConsumerState<TaskFormPage>
    with SingleTickerProviderStateMixin {
  final _formKey = GlobalKey<FormState>();
  bool _saving = false;

  late final TextEditingController _title;
  late final TextEditingController _description;
  late final TextEditingController _tags;
  late final TabController _descTabController;
  DateTime? _dueDate;
  int _priority = 0;

  bool get _isEdit => widget.task != null;

  @override
  void initState() {
    super.initState();
    final t = widget.task;
    _title = TextEditingController(text: t?.title);
    _description = TextEditingController(text: t?.description);
    _tags = TextEditingController(text: t?.tags.join(', '));
    _descTabController = TabController(length: 2, vsync: this);
    _dueDate = t?.dueDate;
    _priority = t?.priority ?? 0;
  }

  @override
  void dispose() {
    _title.dispose();
    _description.dispose();
    _tags.dispose();
    _descTabController.dispose();
    super.dispose();
  }

  String _formatDate(DateTime dt) {
    final local = dt.toLocal();
    final y = local.year.toString().padLeft(4, '0');
    final m = local.month.toString().padLeft(2, '0');
    final d = local.day.toString().padLeft(2, '0');
    return '$y-$m-$d';
  }

  Future<void> _pickDueDate() async {
    final now = DateTime.now();
    final initial = _dueDate ?? now;
    final date = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(now.year - 1),
      lastDate: DateTime(now.year + 5),
    );
    if (date == null || !mounted) return;
    // End-of-day so the task stays "today" until midnight.
    setState(() {
      _dueDate = DateTime(date.year, date.month, date.day, 23, 59);
    });
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);

    final tags = _tags.text.isEmpty
        ? <String>[]
        : _tags.text.split(',').map((t) => t.trim()).where((t) => t.isNotEmpty).toList();

    final body = {
      'title': _title.text,
      if (_description.text.isNotEmpty) 'description': _description.text,
      'due_date': _dueDate?.toUtc().toIso8601String(),
      'priority': _priority,
      'tags': tags,
    };

    final repo = ref.read(tasksRepositoryProvider);
    if (_isEdit) {
      await repo.update(widget.task!.id, body);
    } else {
      await repo.create(body);
    }

    ref.invalidate(tasksProvider);
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_isEdit ? 'Edit Task' : 'New Task')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: TextFormField(
                controller: _title,
                decoration: const InputDecoration(
                  labelText: 'Title',
                  border: OutlineInputBorder(),
                ),
                validator: (v) =>
                    (v == null || v.isEmpty) ? 'Title is required' : null,
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
                  labelText: 'Due date',
                  border: OutlineInputBorder(),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        _dueDate == null ? 'No due date' : _formatDate(_dueDate!),
                      ),
                    ),
                    if (_dueDate != null)
                      IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () => setState(() => _dueDate = null),
                      ),
                    TextButton(
                      onPressed: _pickDueDate,
                      child: const Text('Pick'),
                    ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: DropdownButtonFormField<int>(
                initialValue: _priority,
                decoration: const InputDecoration(
                  labelText: 'Priority',
                  border: OutlineInputBorder(),
                ),
                items: const [
                  DropdownMenuItem(value: 0, child: Text('Low')),
                  DropdownMenuItem(value: 1, child: Text('Medium')),
                  DropdownMenuItem(value: 2, child: Text('High')),
                ],
                onChanged: (v) => setState(() => _priority = v ?? 0),
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: TextFormField(
                controller: _tags,
                decoration: const InputDecoration(
                  labelText: 'Tags',
                  hintText: 'bug, urgent, feature',
                  border: OutlineInputBorder(),
                ),
              ),
            ),
            FilledButton(
              onPressed: _saving ? null : _save,
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
