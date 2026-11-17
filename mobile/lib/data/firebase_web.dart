import 'package:firebase_core/firebase_core.dart';

/// The Firebase project of CNV as seen by the browser version (the phone reads the same
/// project from android/app/google-services.json). These values are not secret: every web
/// page that uses Firebase carries them, and what an account can read or write is decided by
/// the rules (firebase/firestore.rules) and by the allowed addresses in the console.
/// From the Firebase console: Impostazioni progetto → Le tue app → CNV web.
const webFirebaseOptions = FirebaseOptions(
  apiKey: 'AIzaSyAB9AEop82zy2KuFxZzIwvPQJ88ClMR7nc',
  appId: '1:432894659987:web:d1c94f26d8fc41c9f26c66',
  messagingSenderId: '432894659987',
  projectId: 'cnv-chi-ni-vidimu',
  authDomain: 'cnv-chi-ni-vidimu.firebaseapp.com',
  storageBucket: 'cnv-chi-ni-vidimu.firebasestorage.app',
);
