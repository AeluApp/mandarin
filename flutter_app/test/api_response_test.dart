import 'package:flutter_test/flutter_test.dart';

import 'package:aelu/api/api_response.dart';

void main() {
  group('SafeMap.str', () {
    test('returns string value', () {
      final map = <String, dynamic>{'name': 'hello'};
      expect(map.str('name'), 'hello');
    });

    test('returns empty string for missing key', () {
      final map = <String, dynamic>{};
      expect(map.str('name'), '');
    });

    test('returns empty string for non-string value', () {
      final map = <String, dynamic>{'name': 42};
      expect(map.str('name'), '');
    });

    test('returns empty string for null value', () {
      final map = <String, dynamic>{'name': null};
      expect(map.str('name'), '');
    });
  });

  group('SafeMap.strOrNull', () {
    test('returns string value', () {
      final map = <String, dynamic>{'name': 'hello'};
      expect(map.strOrNull('name'), 'hello');
    });

    test('returns null for missing key', () {
      final map = <String, dynamic>{};
      expect(map.strOrNull('name'), isNull);
    });

    test('returns null for non-string value', () {
      final map = <String, dynamic>{'name': 42};
      expect(map.strOrNull('name'), isNull);
    });
  });

  group('SafeMap.integer', () {
    test('returns int value', () {
      final map = <String, dynamic>{'count': 42};
      expect(map.integer('count'), 42);
    });

    test('converts double to int', () {
      final map = <String, dynamic>{'count': 42.7};
      expect(map.integer('count'), 42);
    });

    test('returns default for missing key', () {
      final map = <String, dynamic>{};
      expect(map.integer('count'), 0);
    });

    test('returns custom default for missing key', () {
      final map = <String, dynamic>{};
      expect(map.integer('count', 99), 99);
    });

    test('returns default for non-numeric value', () {
      final map = <String, dynamic>{'count': 'abc'};
      expect(map.integer('count'), 0);
    });

    test('returns default for null value', () {
      final map = <String, dynamic>{'count': null};
      expect(map.integer('count'), 0);
    });

    test('returns default for bool value', () {
      final map = <String, dynamic>{'count': true};
      expect(map.integer('count'), 0);
    });
  });

  group('SafeMap.boolean', () {
    test('returns bool value true', () {
      final map = <String, dynamic>{'flag': true};
      expect(map.boolean('flag'), true);
    });

    test('returns bool value false', () {
      final map = <String, dynamic>{'flag': false};
      expect(map.boolean('flag'), false);
    });

    test('returns default for missing key', () {
      final map = <String, dynamic>{};
      expect(map.boolean('flag'), false);
    });

    test('returns custom default for missing key', () {
      final map = <String, dynamic>{};
      expect(map.boolean('flag', true), true);
    });

    test('returns default for non-bool value', () {
      final map = <String, dynamic>{'flag': 1};
      expect(map.boolean('flag'), false);
    });

    test('returns default for string "true"', () {
      // Intentional: type-safe means no string coercion
      final map = <String, dynamic>{'flag': 'true'};
      expect(map.boolean('flag'), false);
    });
  });

  group('SafeMap.nested', () {
    test('returns nested map', () {
      final inner = <String, dynamic>{'a': 1};
      final map = <String, dynamic>{'data': inner};
      expect(map.nested('data'), inner);
    });

    test('returns empty map for missing key', () {
      final map = <String, dynamic>{};
      expect(map.nested('data'), <String, dynamic>{});
    });

    test('returns empty map for non-map value', () {
      final map = <String, dynamic>{'data': 'string'};
      expect(map.nested('data'), <String, dynamic>{});
    });

    test('returns empty map for null value', () {
      final map = <String, dynamic>{'data': null};
      expect(map.nested('data'), <String, dynamic>{});
    });
  });

  group('SafeMap.nestedOrNull', () {
    test('returns nested map', () {
      final inner = <String, dynamic>{'a': 1};
      final map = <String, dynamic>{'data': inner};
      expect(map.nestedOrNull('data'), inner);
    });

    test('returns null for missing key', () {
      final map = <String, dynamic>{};
      expect(map.nestedOrNull('data'), isNull);
    });

    test('returns null for non-map value', () {
      final map = <String, dynamic>{'data': [1, 2]};
      expect(map.nestedOrNull('data'), isNull);
    });
  });

  group('SafeMap.list', () {
    test('returns list value', () {
      final map = <String, dynamic>{
        'items': [1, 2, 3],
      };
      expect(map.list('items'), [1, 2, 3]);
    });

    test('returns empty list for missing key', () {
      final map = <String, dynamic>{};
      expect(map.list('items'), <dynamic>[]);
    });

    test('returns empty list for non-list value', () {
      final map = <String, dynamic>{'items': 'not a list'};
      expect(map.list('items'), <dynamic>[]);
    });

    test('returns empty list for null value', () {
      final map = <String, dynamic>{'items': null};
      expect(map.list('items'), <dynamic>[]);
    });

    test('handles mixed-type lists', () {
      final map = <String, dynamic>{
        'items': [1, 'two', true, null],
      };
      expect(map.list('items').length, 4);
    });
  });

  group('SafeMap.from', () {
    test('returns map from valid data', () {
      final data = <String, dynamic>{'key': 'value'};
      expect(SafeMap.from(data), data);
    });

    test('returns null from null', () {
      expect(SafeMap.from(null), isNull);
    });

    test('returns null from non-map', () {
      expect(SafeMap.from('string'), isNull);
    });

    test('returns null from list', () {
      expect(SafeMap.from([1, 2, 3]), isNull);
    });

    test('returns null from int', () {
      expect(SafeMap.from(42), isNull);
    });
  });

  group('SafeMap chaining', () {
    test('safely navigates nested structure', () {
      final map = <String, dynamic>{
        'user': <String, dynamic>{
          'name': 'Alice',
          'age': 30,
          'verified': true,
          'scores': [95, 87, 92],
        },
      };

      final user = map.nested('user');
      expect(user.str('name'), 'Alice');
      expect(user.integer('age'), 30);
      expect(user.boolean('verified'), true);
      expect(user.list('scores').length, 3);
    });

    test('safely handles missing nested structure', () {
      final map = <String, dynamic>{'other': 'data'};

      final user = map.nested('user');
      expect(user.str('name'), '');
      expect(user.integer('age'), 0);
      expect(user.boolean('verified'), false);
      expect(user.list('scores'), <dynamic>[]);
    });
  });
}
