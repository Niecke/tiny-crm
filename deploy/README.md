# Deploying tinyCRM

Merges to `main` reach staging, release tags reach production, both through
Flux. Nothing pushes: the cluster pulls, so no GitHub workflow holds cluster
credentials and the k3s API stays unpublished.

```
merge to main
  ├─ promote.yml           retags the tested image digest, commits sha-<short>
  │                        into deploy/flux/staging/helmrelease.yaml
  └─ source-controller     fetches the commit
       ├─ kustomize-ctrl   applies deploy/flux/ — so the committed tag
       │                   actually reaches the HelmRelease objects
       └─ helm-controller  re-renders charts/tinycrm, upgrades staging

merge the release-please pull request → tag vX.Y.Z
  └─ release.yml           retags sha-<short> as X.Y.Z, X.Y, X, stable,
                           pushes charts/tinycrm as the OCI chart X.Y.Z,
                           signs both and attests the SBOMs (cosign keyless),
                           commits X.Y.Z into deploy/flux/prod/ — images in
                           helmrelease.yaml, chart in ocirepository.yaml
```

Two environments on the one k3s node, one HelmRelease each:

| | Namespace | Host | Chart from | Image tag written by |
|---|---|---|---|---|
| `deploy/flux/staging/` | `tinycrm-staging` | `crm-staging.niecke-it.de` | `charts/tinycrm` on `main` | `promote.yml`, every merge |
| `deploy/flux/prod/` | `tinycrm` | `crm.niecke-it.de` | `oci://ghcr.io/niecke/tiny-crm/charts/tinycrm`, pinned to the release | `release.yml`, every `vX.Y.Z` tag |

`deploy/flux/base/` holds the shared GitRepository and the Flux Kustomization.
The entry point stays `deploy/flux/kustomization.yaml`, the path that
Kustomization reads.

The kustomize step is not optional. A HelmRelease is a cluster object; editing
its manifest in git changes nothing until something applies it. Without that
controller the images get tagged, the sha lands in git, and the cluster silently
keeps running the previous release.

Staging redeploys on two kinds of commit on `main`:

- a chart change under `charts/tinycrm/` — picked up because the staging
  HelmRelease sets `reconcileStrategy: Revision`, so Flux keys off the git
  commit rather than `Chart.yaml`'s version
- a new image — `promote.yml` writes `sha-<short>` into the staging HelmRelease

Production redeploys only on `release.yml`'s `Deploy X.Y.Z to production`
commit, which moves the chart and the images together. A chart change on
`main` reaches production with the next release, never before.

## Releasing

release-please keeps a `chore(main): release X.Y.Z` pull request open against
`main`, collecting the conventional commits since the last tag. Merging it is
the production decision:

1. CI builds and tests the release pull request like any other — its images
   report the plain `vX.Y.Z`.
2. The merge runs `promote.yml` (images tagged `sha-<short>`, staging moves) and
   release-please, which tags `vX.Y.Z` and publishes the GitHub Release.
3. The tag runs `release.yml`. It waits for `sha-<short>` on all three images
   and fails if they never appear — it never builds. Then it tags that digest
   `X.Y.Z`, `X.Y`, `X` and `stable`, packages `charts/tinycrm` as the tag has
   it and pushes it to `oci://ghcr.io/niecke/tiny-crm/charts` (failing if
   `Chart.yaml` is not at `X.Y.Z`), signs every digest with cosign (keyless,
   GitHub OIDC) and attaches a signed syft SPDX SBOM to each image, commits
   `Deploy X.Y.Z to production`, and appends the image and chart digests and
   the `cosign verify` commands to the GitHub Release notes. The SBOMs are not
   uploaded as Release assets — immutable releases refuse uploads once a Release
   is published — so they are read back from GHCR with
   `cosign verify-attestation`.

Every image also carries SLSA provenance (`mode=max`) from its build on the
pull request; the retags copy it along with the digest. It records the build
args, so a build arg must never carry a secret.

`stable`, `X`, `X.Y` and production only move forward: a tag older than the
newest release gets its `X.Y.Z` and nothing else.

### Rolling back

```bash
# flips production's images and chart back to the previous release
git revert <Deploy X.Y.Z to production commit>   # through a pull request
```

Or edit the image tags in `deploy/flux/prod/helmrelease.yaml` and the chart tag
in `deploy/flux/prod/ocirepository.yaml` directly — keep all four on the same
release — then `flux -n tinycrm reconcile helmrelease tinycrm --with-source`. To freeze the
cluster where it stands: `flux -n tinycrm suspend helmrelease tinycrm`.

> [!WARNING]
> Migrations do not roll back with the image. Every Alembic migration has to
> work with release N−1: add and backfill in one release, stop writing the old
> column in the next, drop it in a third.

## One-time cluster setup

Flux, with only the two controllers this needs. The image automation
controllers are deliberately absent: `promote.yml` already decides which digest
is deployable, and a scanner picking up tags it never blessed would undo the
promote-by-digest guarantee.

```bash
flux install --components=source-controller,helm-controller,kustomize-controller
kubectl create namespace tinycrm
```

The credentials Secret. This is the one thing that is never in git — it carries
the same YAML a local `values-secrets.yaml` would, and Flux merges it underneath
the HelmRelease's inline values.

```bash
cat > /tmp/values.yaml <<EOF
postgres:
  password: $(openssl rand -base64 24)
s3:
  # the tinycrm-backend key from the Hetzner Cloud Console
  # (infrastructure repo, MANUAL-STEPS.md §9)
  accessKey: ...
  secretKey: ...
backend:
  jwtSecret: $(openssl rand -hex 32)
EOF

kubectl -n tinycrm create secret generic tinycrm-values \
  --from-file=values.yaml=/tmp/values.yaml

shred -u /tmp/values.yaml
```

Put those four values in a password manager before deleting the file.
`postgres.password` cannot be rotated by re-running this: CloudNativePG sets it
at `initdb`, and changing it afterwards leaves the chart handing the backend a
URL the database rejects.

Then point Flux at the repo:

```bash
# -k, not -f: kustomization.yaml is a kustomize build file, not a cluster
# resource, and `apply -f` would try to POST it to the API.
kubectl apply -k deploy/flux/
flux -n tinycrm get kustomization tinycrm-flux
flux -n tinycrm get helmrelease tinycrm
```

That `kubectl apply` is a bootstrap, run once. From then on the Kustomization
manages all three objects — including itself and the GitRepository — so later
changes go through git rather than through `kubectl`.

Which also means hand-patching the GitRepository's branch stops sticking: the
next reconcile restores whatever git says. To work off a branch, suspend first:

```bash
flux -n tinycrm suspend kustomization tinycrm-flux
kubectl -n tinycrm patch gitrepository tinycrm --type=merge \
  -p '{"spec":{"ref":{"branch":"some-branch"}}}'
# ... and when done
flux -n tinycrm resume kustomization tinycrm-flux
```

## Staging setup

Flux creates the `tinycrm-staging` namespace and the `tinycrm-staging`
PriorityClass itself. Three things it cannot create, all by hand, before or
right after the first merge — the HelmRelease reports not-ready until they exist:

1. **Object storage.** A bucket `niecke-tinycrm-documents-staging` with
   versioning on, in a **separate Hetzner project** — a Hetzner key reaches every
   bucket in its project. Create that project's key the same way as production's
   (infrastructure repo, MANUAL-STEPS.md §9).
2. **The credentials Secret**, same shape as production's, all values new:

   ```bash
   cat > /tmp/values.yaml <<EOF
   postgres:
     password: $(openssl rand -base64 24)
   s3:
     # the key from the staging Hetzner project
     accessKey: ...
     secretKey: ...
   backend:
     jwtSecret: $(openssl rand -hex 32)
   EOF

   kubectl -n tinycrm-staging create secret generic tinycrm-values \
     --from-file=values.yaml=/tmp/values.yaml
   shred -u /tmp/values.yaml
   ```

3. **Basic auth** for the frontend. htpasswd lines under the key `users`:

   ```bash
   # htpasswd is in httpd-tools (Fedora) / apache2-utils (Debian)
   PW="$(openssl rand -base64 18)"; echo "staging password: $PW"
   kubectl -n tinycrm-staging create secret generic tinycrm-staging-basic-auth \
     --from-literal=users="$(htpasswd -nbB staging "$PW" | head -1)" \
     --dry-run=client -o yaml | kubectl apply -f -
   unset PW
   ```

   The Secret holds only the bcrypt hash, so put the printed password in the
   password manager — it cannot be read back. Re-running the block replaces it.
   The user name is `staging`.

   Until this Secret exists, Traefik cannot load the basic-auth middleware and
   drops the frontend route: `/` answers 404 while `/api/health` still works.

   Only the frontend sits behind it. `/api` keeps its own JWT auth — both use
   the `Authorization` header, so basic auth on the API would reject every
   logged-in request.

The staging stack has no backup and no briefing CronJob, runs at a negative
priority so the kubelet evicts it before production, and is sized to about
250 Mi of real memory. Its first admin comes from `python -m app.cli create-user`
exactly as in production, with `-n tinycrm-staging`.

### The frontend image

The `frontend` image is the React client, built from `frontend-next/` (#122).
It kept the name of the Flutter client it replaced, which CI no longer builds;
its code stays in `frontend/` for now. Tags promoted before the cutover are
still Flutter builds, and both kinds run on the current chart: each serves at
`/` and reads `config.json` from `/srv/config.json`.

So production switches when its `frontend.image.tag` moves to a sha built
after the cutover, together with the backend tag of the same build. The React
image redirects the preview's old `/next/…` URLs to the same page at the root.

## Repository settings this depends on

`promote.yml` pushes a commit to `main`, which the `protect_main` ruleset only
allows for deploy keys. The push therefore goes over SSH with the `DEPLOY_KEY`
secret — a write deploy key on this repository. Without it the promote job fails
at the push step, images are tagged but the deployed sha never moves, and
staging silently keeps running the previous build.

`release.yml` pushes its `Deploy X.Y.Z to production` commit the same way.

The chart package `tiny-crm/charts/tinycrm` on GHCR must be **public**: the
production `OCIRepository` pulls it anonymously, like the kubelet pulls the
images. GHCR creates a package private on its first push, and there is no API
to change that — after the first release, set it under the package's settings,
*Change visibility*. Until then the `OCIRepository` reports an authentication
error and production stays on the release it already runs.

Unlike a `GITHUB_TOKEN` push, a deploy-key push does trigger workflows. promote
skips both kinds of `Deploy …` commit with a job-level `if:`.

The tag that starts `release.yml` must come from `RELEASE_PLEASE_TOKEN`, not
`GITHUB_TOKEN` — GitHub starts no workflows for a tag pushed with the latter.

## Cutover

Phase 7's DNS flip pairs with editing one line in
`deploy/flux/prod/helmrelease.yaml`:

```yaml
    ingress:
      host: crm.niecke-it.de
```

Merge it and Flux rolls the ingress and the frontend's `apiUrl` together.

## Operating it

```bash
flux -n tinycrm get helmrelease tinycrm      # what is deployed, and whether it reconciled
flux -n tinycrm reconcile helmrelease tinycrm --with-source   # don't wait for the interval
flux -n tinycrm events --for HelmRelease/tinycrm              # why an upgrade failed
helm -n tinycrm history tinycrm                               # rollback targets
```

A failed upgrade is retried three times and then rolled back
(`remediateLastFailure`), so a bad merge leaves the previous release running
rather than a half-applied one.

If an upgrade times out mid-flight, Helm can be left claiming an operation is
still running and will refuse the next one. `helm -n tinycrm list -a` shows
`pending-upgrade` when that has happened; `helm -n tinycrm rollback tinycrm`
clears it, then reconcile.

`flux resume` and `flux reconcile` block while watching. Ctrl-C only stops the
watching — pass `--wait=false` to skip it.

### Turning on the morning briefing

Off by default: it cannot work without a Slack webhook, and a CronJob that
fails every morning is worse than no CronJob. Enabling it is two changes that
must land together — the credential in the cluster Secret, the flag in git.

The webhook is a bearer credential (anyone holding it can post to the channel),
so it goes in the same Secret as the database and JWT secrets, never in git.
Create it in Slack under Apps → Incoming Webhooks → add to a channel, then
merge it into the existing values:

```bash
kubectl -n tinycrm get secret tinycrm-values \
  -o jsonpath='{.data.values\.yaml}' | base64 -d > /tmp/values.yaml

cat >> /tmp/values.yaml <<'EOF'
briefing:
  slackWebhookUrl: https://hooks.slack.com/services/T000/B000/XXXX
EOF

kubectl -n tinycrm create secret generic tinycrm-values \
  --from-file=values.yaml=/tmp/values.yaml --dry-run=client -o yaml \
  | kubectl apply -f -

shred -u /tmp/values.yaml
```

Then set `briefing.enabled: true` under `values:` in
`deploy/flux/prod/helmrelease.yaml` and merge. Doing it in the other order renders
a template error — `briefing.slackWebhookUrl is required` — and Flux leaves
the previous release running, which is the intended failure.

```bash
kubectl -n tinycrm get cronjob tinycrm-briefing
kubectl -n tinycrm create job briefing-now --from=cronjob/tinycrm-briefing  # send one now
kubectl -n tinycrm logs job/briefing-now
```

The schedule (`0 7 * * 1-5`, Europe/Berlin) and the timezone are in
`charts/tinycrm/values.yaml`. The timezone is also the operator's day boundary,
which decides whether a task due at 23:59 counts as today — change both
together or not at all.

### Turning on business card scanning

Scanned business cards are read by Claude through the Anthropic API
(`app/business_cards.py`). Until a key is set, the scan screen says scanning
is not set up; nothing else changes.

Create a key at console.anthropic.com → API keys. It is a bearer credential,
so it goes into the `tinycrm-values` Secret like the others:

```yaml
backend:
  businessCards:
    anthropicApiKey: sk-ant-...
```

The photos are sent to Anthropic to be read and are not stored anywhere.

The model that reads them is `backend.businessCards.model` (default
`claude-opus-5-5`). It is not secret, so set it under `values:` in
`deploy/flux/prod/helmrelease.yaml` — or in `tinycrm-values`, if you would
rather not commit it. Either change rolls the backend pods with the new
`BUSINESS_CARD_MODEL`; no new image or release is needed. Each scan shows the
model and tokens it used on the review screen, to compare the cost.

### Turning on mail

Invites and password-reset links go out through Brevo's API (`app/mail.py`).
Until it is configured, `POST /auth/forgot-password` logs the request and sends
nothing, and `create-user` refuses to invite.

In Brevo, once:

1. Senders, Domains & Dedicated IPs → Domains: add the sending domain and put
   the SPF, DKIM and DMARC records it shows into DNS. Wait for "Authenticated".
2. Add the from-address as a sender on that domain.
3. SMTP & API → API keys: create a key for this instance.
4. Turn off click tracking for transactional mail. It rewrites every link
   through Brevo's redirect domain — for a reset link, that routes a live
   password token through a third party's logs.

The API key is a bearer credential, so it goes into the `tinycrm-values`
Secret exactly like the Slack webhook above:

```yaml
backend:
  mail:
    brevoApiKey: xkeysib-...
```

The from-address is not secret; set `backend.mail.fromAddress` under `values:`
in `deploy/flux/prod/helmrelease.yaml`.

Links point at `https://<ingress.host>/reset-password`: the page exists only
in the React client, so a release still running a Flutter `frontend` tag lands
invites on an app that has no such page.

### Creating a user

No signup flow; accounts come from the CLI, which mails an invite with a
single-use link to choose a password (valid 12 hours):

```bash
kubectl -n tinycrm exec deploy/tinycrm-backend -- \
  python -m app.cli create-user you@niecke-it.de --name "You" --superuser
kubectl -n tinycrm exec deploy/tinycrm-backend -- \
  python -m app.cli invite you@niecke-it.de      # expired or lost invite
```

Before mail is set up, set the password directly. It is read from stdin, never
passed as an argument:

```bash
read -rsp 'password: ' PW && echo
printf '%s\n' "$PW" | kubectl -n tinycrm exec -i deploy/tinycrm-backend -- \
  python -m app.cli create-user you@niecke-it.de --superuser --set-password
unset PW
```

## Local install, without Flux

For a k3d cluster, or to test the chart before merging:

```bash
helm upgrade --install tinycrm ./charts/tinycrm \
  -n tinycrm --create-namespace \
  -f charts/tinycrm/values-crm-new.yaml \
  -f values-secrets.yaml \
  --set backend.image.tag=sha-<short> \
  --set frontend.image.tag=sha-<short> \
  --set backup.image.tag=sha-<short>
```

The chart has no default image tag, so leaving these out fails the render.

`values-secrets.yaml` is gitignored. `values-crm-new.yaml` exists so a manual
install does not default to the live hostname — cert-manager would fail http-01
against it while DNS still points at GCP, and Let's Encrypt rate-limits failed
validations per account.
