import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'timing.dart';

/// Scroll-aware reveal — fades and slides child into view when it scrolls
/// into the viewport. Equivalent to the web's `[data-reveal]` + `is-revealed`
/// pattern powered by IntersectionObserver.
///
/// Usage:
/// ```dart
/// ScrollReveal(
///   child: MyCard(),
///   delay: Duration(milliseconds: 100),
/// )
/// ```
///
/// For staggered children, wrap each in [ScrollReveal] with increasing delays:
/// ```dart
/// Column(children: [
///   ScrollReveal(delay: Duration.zero, child: Card1()),
///   ScrollReveal(delay: Duration(milliseconds: 80), child: Card2()),
///   ScrollReveal(delay: Duration(milliseconds: 160), child: Card3()),
/// ])
/// ```
class ScrollReveal extends StatefulWidget {
  final Widget child;
  final Duration delay;
  final Duration duration;
  final double offsetY;

  /// Fraction of the widget that must be visible to trigger (0.0–1.0).
  final double visibleFraction;

  const ScrollReveal({
    super.key,
    required this.child,
    this.delay = Duration.zero,
    this.duration = AeluTiming.base,
    this.offsetY = 24.0,
    this.visibleFraction = 0.1,
  });

  @override
  State<ScrollReveal> createState() => _ScrollRevealState();
}

class _ScrollRevealState extends State<ScrollReveal>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _opacity;
  late final Animation<Offset> _offset;
  bool _revealed = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: widget.duration);
    _opacity = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _controller, curve: AeluTiming.easeUpward),
    );
    _offset = Tween<Offset>(
      begin: Offset(0, widget.offsetY),
      end: Offset.zero,
    ).animate(
      CurvedAnimation(parent: _controller, curve: AeluTiming.easeUpward),
    );

    // Check visibility after first frame
    WidgetsBinding.instance.addPostFrameCallback((_) => _checkVisibility());
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _checkVisibility() {
    if (_revealed || !mounted) return;

    final renderObject = context.findRenderObject();
    if (renderObject == null || !renderObject.attached) return;

    final viewport = RenderAbstractViewport.of(renderObject);
    final revealOffset = viewport.getOffsetToReveal(renderObject, 0.0);
    final scrollableState = Scrollable.maybeOf(context);

    if (scrollableState == null) {
      // Not inside a scrollable — reveal immediately
      _reveal();
      return;
    }

    final scrollPosition = scrollableState.position;
    final viewportDimension = scrollPosition.viewportDimension;
    final scrollOffset = scrollPosition.pixels;

    final itemTop = revealOffset.offset;
    final itemHeight = renderObject.paintBounds.height;
    final visibleTop = scrollOffset;
    final visibleBottom = scrollOffset + viewportDimension;

    // Check if enough of the widget is visible
    final overlapStart = itemTop.clamp(visibleTop, visibleBottom);
    final overlapEnd = (itemTop + itemHeight).clamp(visibleTop, visibleBottom);
    final visibleAmount = overlapEnd - overlapStart;
    final fraction = itemHeight > 0 ? visibleAmount / itemHeight : 0.0;

    if (fraction >= widget.visibleFraction) {
      _reveal();
    }
  }

  void _reveal() {
    if (_revealed) return;
    _revealed = true;

    if (widget.delay == Duration.zero) {
      _controller.forward();
    } else {
      Future.delayed(widget.delay, () {
        if (mounted) _controller.forward();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return NotificationListener<ScrollNotification>(
      onNotification: (notification) {
        if (!_revealed) _checkVisibility();
        return false; // Don't consume the notification
      },
      child: RepaintBoundary(
        child: AnimatedBuilder(
          animation: _controller,
          builder: (context, child) => Transform.translate(
            offset: _offset.value,
            child: Opacity(opacity: _opacity.value, child: child),
          ),
          child: widget.child,
        ),
      ),
    );
  }
}
