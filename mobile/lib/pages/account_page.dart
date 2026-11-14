import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../data/account.dart';
import '../theme.dart';
import '../widgets/letterboxd_widgets.dart' show say;

/// Gives the pages the account (and rebuilds them when it changes).
class AccountScope extends InheritedNotifier<AccountStore> {
  const AccountScope({super.key, required AccountStore store, required super.child}) : super(notifier: store);

  static AccountStore of(BuildContext context) => context.dependOnInheritedWidgetOfExactType<AccountScope>()!.notifier!;
}

/// Runs an account action and shows its error, if any.
Future<bool> _attempt(BuildContext context, Future<void> Function() action) async {
  try {
    await action();
    return true;
  } on AccountError catch (err) {
    if (context.mounted) say(context, err.message);
  } catch (err) {
    if (context.mounted) say(context, 'Qualcosa non ha funzionato: $err');
  }
  return false;
}

/// The "Account" box of the Voti page: sign in, the confirmation of the e-mail, whether the
/// account is admitted, and for the administrator the list of admitted e-mails.
class AccountSection extends StatelessWidget {
  const AccountSection({super.key});

  @override
  Widget build(BuildContext context) {
    final account = AccountScope.of(context);
    final user = account.user;
    final children = <Widget>[
      const Text('Account', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
      const SizedBox(height: 4),
    ];
    void text(String s, {Color color = CnvColors.textMuted}) =>
        children.add(Padding(padding: const EdgeInsets.only(bottom: 8), child: Text(s, style: TextStyle(fontSize: 13, color: color, height: 1.35))));

    if (!account.available) {
      text("L'accesso non è disponibile su questo telefono. CNV funziona lo stesso.");
    } else if (user == null) {
      text("Con l'account ritrovi i tuoi voti su un altro telefono e, più avanti, ricevi le notifiche. "
          'CNV funziona anche senza. L’account è solo su invito: se non sei nella lista, chiedi di aggiungerti.');
      children.addAll([
        FilledButton.icon(
          onPressed: account.busy ? null : () => _attempt(context, account.signInWithGoogle),
          icon: const Icon(Icons.account_circle),
          label: const Text('Accedi con Google'),
        ),
        const SizedBox(height: 6),
        OutlinedButton.icon(
          onPressed: account.busy
              ? null
              : () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => EmailLoginPage(account: account))),
          icon: const Icon(Icons.mail_outline),
          label: const Text('Accedi con email e password'),
        ),
      ]);
    } else {
      children.add(Text(user.name != null && user.name!.isNotEmpty ? '${user.name} · ${user.email}' : user.email,
          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)));
      children.add(const SizedBox(height: 6));
      if (!user.verified) {
        text('Ti ho mandato un’email di conferma a ${user.email}. Apri il link che contiene (guarda anche nello spam), '
            'poi torna qui e tocca “Ho confermato”.', color: CnvColors.yellow);
        children.addAll([
          FilledButton(
            onPressed: account.busy
                ? null
                : () => _attempt(context, () async {
                      if (!await account.reloadVerified() && context.mounted) {
                        say(context, 'L’email non risulta ancora confermata.');
                      }
                    }),
            child: const Text('Ho confermato'),
          ),
          const SizedBox(height: 6),
          OutlinedButton(
            onPressed: account.busy
                ? null
                : () => _attempt(context, () async {
                      await account.sendVerification();
                      if (context.mounted) say(context, 'Email di conferma mandata di nuovo.');
                    }),
            child: const Text('Rimanda l’email'),
          ),
        ]);
      } else {
        switch (account.admission) {
          case Admission.checking:
          case Admission.none:
            children.add(const Padding(
              padding: EdgeInsets.only(bottom: 8),
              child: Row(children: [
                SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)),
                SizedBox(width: 8),
                Text('Controllo se sei nella lista…', style: TextStyle(fontSize: 13, color: CnvColors.textMuted)),
              ]),
            ));
          case Admission.admitted:
            text('✓ Sei nella lista. Nella prossima versione i tuoi voti passeranno all’account.', color: CnvColors.green);
          case Admission.notAdmitted:
            text('Non sei ancora nella lista degli ammessi: chiedi a chi ti ha dato CNV di aggiungere ${user.email}, '
                'poi tocca “Riprova”.', color: CnvColors.yellow);
          case Admission.error:
            text('Non riesco a controllare se sei nella lista. Controlla la connessione e riprova.', color: CnvColors.yellow);
        }
        if (account.admission == Admission.notAdmitted || account.admission == Admission.error) {
          children.add(OutlinedButton(onPressed: account.busy ? null : account.checkAdmission, child: const Text('Riprova')));
        }
        if (account.isAdmin) {
          children.add(FilledButton.tonalIcon(
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => AllowListPage(account: account))),
            icon: const Icon(Icons.group_add),
            label: Text('Gestisci gli ammessi (${account.allowed!.length})'),
          ));
        }
      }
      children.addAll([
        const SizedBox(height: 4),
        Row(
          children: [
            Expanded(
              child: Text('Codice utente: ${user.uid}',
                  overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 11, color: CnvColors.textMuted)),
            ),
            IconButton(
              tooltip: 'Copia il codice utente',
              visualDensity: VisualDensity.compact,
              icon: const Icon(Icons.copy, size: 16),
              onPressed: () async {
                await Clipboard.setData(ClipboardData(text: user.uid));
                if (context.mounted) say(context, 'Codice utente copiato.');
              },
            ),
          ],
        ),
        TextButton.icon(
          onPressed: account.busy ? null : () => _attempt(context, account.signOut),
          icon: const Icon(Icons.logout, size: 18),
          label: const Text('Esci dall’account'),
        ),
      ]);
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 22),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: CnvColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: CnvColors.border),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
    );
  }
}

/// Sign in or create an account with e-mail and password, or get a new password.
class EmailLoginPage extends StatefulWidget {
  const EmailLoginPage({super.key, required this.account});

  final AccountStore account;

  @override
  State<EmailLoginPage> createState() => _EmailLoginPageState();
}

class _EmailLoginPageState extends State<EmailLoginPage> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _register = false;
  bool _hidden = true;
  String? _problem;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final email = _email.text.trim(), password = _password.text;
    setState(() => _problem = !looksLikeEmail(email)
        ? 'Scrivi un indirizzo email valido.'
        : password.length < 6
            ? 'La password deve avere almeno 6 caratteri.'
            : null);
    if (_problem != null) return;
    try {
      await (_register ? widget.account.register(email, password) : widget.account.signInWithEmail(email, password));
      if (mounted) Navigator.of(context).pop();
    } on AccountError catch (err) {
      if (mounted) setState(() => _problem = err.message); // under the fields, where the eyes are
    } catch (err) {
      if (mounted) setState(() => _problem = 'Qualcosa non ha funzionato: $err');
    }
  }

  Future<void> _reset() async {
    final email = _email.text.trim();
    if (!looksLikeEmail(email)) {
      setState(() => _problem = 'Scrivi prima la tua email, poi tocca di nuovo “Password dimenticata?”.');
      return;
    }
    final ok = await _attempt(context, () => widget.account.sendPasswordReset(email));
    if (ok && mounted) say(context, 'Ti ho mandato un’email per scegliere una nuova password.');
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.account,
      builder: (context, _) {
        final busy = widget.account.busy;
        return Scaffold(
          appBar: AppBar(title: Text(_register ? 'Crea un account' : 'Accedi con email')),
          body: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              SegmentedButton<bool>(
                segments: const [
                  ButtonSegment(value: false, label: Text('Ho già un account')),
                  ButtonSegment(value: true, label: Text('Sono nuovo')),
                ],
                selected: {_register},
                onSelectionChanged: (s) => setState(() {
                  _register = s.first;
                  _problem = null;
                }),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                autofillHints: const [AutofillHints.email],
                autocorrect: false,
                decoration: const InputDecoration(labelText: 'Email', border: OutlineInputBorder()),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _password,
                obscureText: _hidden,
                autofillHints: [_register ? AutofillHints.newPassword : AutofillHints.password],
                onSubmitted: (_) => _submit(),
                decoration: InputDecoration(
                  labelText: 'Password',
                  helperText: _register ? 'Almeno 6 caratteri' : null,
                  border: const OutlineInputBorder(),
                  suffixIcon: IconButton(
                    tooltip: _hidden ? 'Mostra la password' : 'Nascondi la password',
                    icon: Icon(_hidden ? Icons.visibility : Icons.visibility_off),
                    onPressed: () => setState(() => _hidden = !_hidden),
                  ),
                ),
              ),
              if (_problem != null)
                Padding(
                  padding: const EdgeInsets.only(top: 10),
                  child: Text(_problem!, style: const TextStyle(color: CnvColors.red)),
                ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: busy ? null : _submit,
                child: Text(busy ? 'Un momento…' : (_register ? 'Crea l’account' : 'Accedi')),
              ),
              if (_register)
                const Padding(
                  padding: EdgeInsets.only(top: 10),
                  child: Text('Ti arriva un’email di conferma: l’account vale solo dopo aver aperto il suo link.',
                      style: TextStyle(fontSize: 12, color: CnvColors.textMuted)),
                )
              else
                TextButton(onPressed: busy ? null : _reset, child: const Text('Password dimenticata?')),
            ],
          ),
        );
      },
    );
  }
}

/// The administrator's page: the e-mails admitted to CNV.
class AllowListPage extends StatefulWidget {
  const AllowListPage({super.key, required this.account});

  final AccountStore account;

  @override
  State<AllowListPage> createState() => _AllowListPageState();
}

class _AllowListPageState extends State<AllowListPage> {
  final _email = TextEditingController();

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _add() async {
    final email = _email.text.trim().toLowerCase();
    if (!looksLikeEmail(email)) {
      say(context, 'Scrivi un indirizzo email valido.');
      return;
    }
    final list = widget.account.allowed ?? const [];
    if (list.contains(email)) {
      say(context, '$email è già nella lista.');
      return;
    }
    if (await _attempt(context, () => widget.account.setAllowList([...list, email]))) _email.clear();
  }

  Future<void> _remove(String email) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (dialog) => AlertDialog(
        title: const Text('Togliere dalla lista?'),
        content: Text('$email non potrà più usare il suo account in CNV. I suoi voti restano salvati.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(dialog).pop(false), child: const Text('Annulla')),
          FilledButton(onPressed: () => Navigator.of(dialog).pop(true), child: const Text('Togli')),
        ],
      ),
    );
    if (ok == true && mounted) {
      await _attempt(context, () => widget.account.setAllowList([...?widget.account.allowed]..remove(email)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.account,
      builder: (context, _) {
        final list = widget.account.allowed ?? const <String>[];
        return Scaffold(
          appBar: AppBar(title: const Text('Ammessi')),
          body: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const Text('Chi è in questa lista può usare il suo account in CNV, con Google o con email e password '
                  '(l’email va confermata). Ognuno vede solo i suoi voti; tu non vedi i loro.',
                  style: TextStyle(fontSize: 13, color: CnvColors.textMuted, height: 1.35)),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _email,
                      keyboardType: TextInputType.emailAddress,
                      autocorrect: false,
                      onSubmitted: (_) => _add(),
                      decoration: const InputDecoration(labelText: 'Email da aggiungere', border: OutlineInputBorder(), isDense: true),
                    ),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(onPressed: widget.account.busy ? null : _add, child: const Text('Aggiungi')),
                ],
              ),
              const SizedBox(height: 14),
              if (list.isEmpty)
                const Text('Nessuno per ora, a parte te.', style: TextStyle(color: CnvColors.textMuted)),
              for (final email in list)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.person_outline),
                  title: Text(email),
                  trailing: IconButton(
                    tooltip: 'Togli $email',
                    icon: const Icon(Icons.remove_circle_outline),
                    onPressed: widget.account.busy ? null : () => _remove(email),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}
