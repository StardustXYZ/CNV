import 'package:flutter/material.dart';

import 'data/repository.dart';
import 'home.dart';
import 'theme.dart';

void main() => runApp(const CnvApp());

/// CNV (Chi Ni Vidimu): the films in the cinemas of Cosenza and Rende, on the phone.
class CnvApp extends StatelessWidget {
  const CnvApp({super.key, this.store});

  final DataStore? store; // given by the tests; otherwise the app downloads the real data

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'CNV',
      debugShowCheckedModeBanner: false,
      theme: cnvTheme(),
      home: HomeShell(store: store),
    );
  }
}
