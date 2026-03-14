import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/animations/drift_up.dart';
import '../core/animations/pressable_scale.dart';
import '../core/error_handler.dart';
import '../shared/widgets/aelu_snackbar.dart';

class AboutScreen extends StatefulWidget {
  const AboutScreen({super.key});

  @override
  State<AboutScreen> createState() => _AboutScreenState();
}

class _AboutScreenState extends State<AboutScreen> {
  String _version = '';
  String _buildNumber = '';

  @override
  void initState() {
    super.initState();
    _loadInfo();
  }

  Future<void> _loadInfo() async {
    try {
      final info = await PackageInfo.fromPlatform();
      setState(() {
        _version = info.version;
        _buildNumber = info.buildNumber;
      });
    } catch (e, st) {
      ErrorHandler.log('About load version', e, st);
      setState(() => _version = '1.0.0');
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('About')),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          DriftUp(
            child: Center(
              child: Text('Aelu', style: theme.textTheme.displayLarge),
            ),
          ),
          const SizedBox(height: 8),
          DriftUp(
            delay: const Duration(milliseconds: 50),
            child: Center(
              child: Text(
                'Deep practice, not busy work.',
                style: theme.textTheme.bodyMedium,
                textAlign: TextAlign.center,
              ),
            ),
          ),
          const SizedBox(height: 16),
          DriftUp(
            delay: const Duration(milliseconds: 75),
            child: Center(
              child: Text(
                'Aelu uses adaptive spaced repetition, graded reading, and native listening to build lasting Mandarin fluency — not just recognition.',
                style: theme.textTheme.bodySmall,
                textAlign: TextAlign.center,
              ),
            ),
          ),
          const SizedBox(height: 24),
          DriftUp(
            delay: const Duration(milliseconds: 100),
            child: ListTile(
              title: const Text('Version'),
              subtitle: Text('$_version ($_buildNumber)'),
            ),
          ),
          const Divider(),
          DriftUp(
            delay: const Duration(milliseconds: 150),
            child: PressableScale(
            onTap: () {
              HapticFeedback.selectionClick();
              showLicensePage(
                context: context,
                applicationName: 'Aelu',
                applicationVersion: _version,
              );
            },
            child: const ListTile(
              title: Text('Licenses'),
              trailing: Icon(Icons.chevron_right),
            ),
          ),
          ),
          const Divider(),
          DriftUp(
            delay: const Duration(milliseconds: 200),
            child: PressableScale(
            onTap: () {
              HapticFeedback.selectionClick();
              _openUrl('https://aelu.app/privacy');
            },
            child: const ListTile(
              title: Text('Privacy Policy'),
              trailing: Icon(Icons.open_in_new_outlined, size: 18),
            ),
          ),
          ),
          DriftUp(
            delay: const Duration(milliseconds: 250),
            child: PressableScale(
            onTap: () {
              HapticFeedback.selectionClick();
              _openUrl('https://aelu.app/terms');
            },
            child: const ListTile(
              title: Text('Terms of Service'),
              trailing: Icon(Icons.open_in_new_outlined, size: 18),
            ),
          ),
          ),
          const Divider(),
          DriftUp(
            delay: const Duration(milliseconds: 300),
            child: PressableScale(
            onTap: () {
              HapticFeedback.selectionClick();
              _openUrl('mailto:support@aelu.app');
            },
            child: const ListTile(
              title: Text('Contact Support'),
              trailing: Icon(Icons.email_outlined, size: 18),
            ),
          ),
          ),
        ],
      ),
    );
  }

  Future<void> _openUrl(String url) async {
    final uri = Uri.parse(url);
    try {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (e, st) {
      ErrorHandler.log('About open URL', e, st);
      if (mounted) {
        AeluSnackbar.show(context, 'Couldn\'t open that link.', type: SnackbarType.error);
      }
    }
  }
}
