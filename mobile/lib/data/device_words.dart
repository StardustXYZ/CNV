/// The few words that change between the app on the phone and the same app in a browser.
library;

import 'package:flutter/foundation.dart';

/// "su questo telefono" / "in questo browser"
const onThisDevice = kIsWeb ? 'in questo browser' : 'su questo telefono';

/// "sul telefono" / "nel browser"
const onDevice = kIsWeb ? 'nel browser' : 'sul telefono';
