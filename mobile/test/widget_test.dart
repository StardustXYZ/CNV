import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:cnv/home.dart';
import 'package:cnv/main.dart';

void main() {
  testWidgets('title and the five pages in the menu', (tester) async {
    await tester.pumpWidget(const CnvApp());

    expect(find.text('CNV'), findsOneWidget);
    expect(find.text('Chi Ni Vidimu'), findsOneWidget);
    final menu = find.byType(NavigationBar);
    for (final page in cnvPages) {
      expect(find.descendant(of: menu, matching: find.text(page.label)), findsOneWidget);
    }
    expect(find.text(cnvPages.first.description), findsOneWidget); // "In sala" first
  });

  testWidgets('the menu and a swipe change the page', (tester) async {
    await tester.pumpWidget(const CnvApp());
    final menu = find.byType(NavigationBar);

    await tester.tap(find.descendant(of: menu, matching: find.text('Visti')));
    await tester.pumpAndSettle();
    expect(find.text(cnvPages[3].description), findsOneWidget);
    expect(tester.widget<NavigationBar>(menu).selectedIndex, 3);

    // Finger to the left: the next page, and the menu follows
    await tester.fling(find.byType(PageView), const Offset(-400, 0), 1500);
    await tester.pumpAndSettle();
    expect(find.text(cnvPages[4].description), findsOneWidget);
    expect(tester.widget<NavigationBar>(menu).selectedIndex, 4);

    await tester.fling(find.byType(PageView), const Offset(400, 0), 1500);
    await tester.pumpAndSettle();
    expect(tester.widget<NavigationBar>(menu).selectedIndex, 3);
  });
}
