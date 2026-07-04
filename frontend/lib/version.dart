/// Frontend build version, baked in at compile time via `--dart-define`.
///
/// This deliberately identifies the *frontend* build the user is actually
/// running and is NOT fetched from the backend — the two are deployed
/// independently and can be at different commits.
const String gitCommit =
    String.fromEnvironment('GIT_COMMIT', defaultValue: 'dev');

/// Short 7-character commit for display in the footer.
String get shortGitCommit =>
    gitCommit.length > 7 ? gitCommit.substring(0, 7) : gitCommit;
