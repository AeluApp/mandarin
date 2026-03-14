import 'package:flutter/material.dart';

/// Text input for drill answers with submit button.
class DrillInput extends StatelessWidget {
  final TextEditingController controller;
  final VoidCallback onSubmit;
  final String hintText;

  const DrillInput({
    super.key,
    required this.controller,
    required this.onSubmit,
    this.hintText = 'Your answer...',
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Answer input',
      child: TextField(
        controller: controller,
        decoration: InputDecoration(
          hintText: hintText,
          suffixIcon: IconButton(
            icon: const Icon(Icons.send_outlined),
            tooltip: 'Submit answer',
            onPressed: onSubmit,
          ),
        ),
        textInputAction: TextInputAction.done,
        onSubmitted: (_) => onSubmit(),
        autofocus: true,
      ),
    );
  }
}
