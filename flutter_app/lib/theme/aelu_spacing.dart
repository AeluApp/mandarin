/// Civic Sanctuary spacing tokens — consistent rhythm across all screens.
///
/// Based on a 4px base unit. Maps to CSS --space-{n} custom properties.
class AeluSpacing {
  AeluSpacing._();

  static const double xs = 4;    // --space-0.5
  static const double sm = 8;    // --space-1
  static const double md = 16;   // --space-2
  static const double lg = 24;   // --space-3
  static const double xl = 32;   // --space-4
  static const double xxl = 48;  // --space-6

  /// Screen edge padding (horizontal).
  static const double screenH = 20;

  /// Vertical gap between major sections.
  static const double sectionGap = 32;

  /// Vertical gap between items within a section.
  static const double itemGap = 12;

  /// Card internal padding.
  static const double cardPadding = 16;
}
