# Deploying tinyCRM

Merges to `main` reach the cluster through Flux. Nothing pushes: the cluster
pulls, so no GitHub workflow holds cluster credentials and the k3s API stays
unpublished.

```
merge to main
  ├─ promote.yml           retags the tested image digest, commits sha-<short>
  │                        into deploy/flux/staging/helmrelease.yaml
  └─ source-controller     fetches the commit
       ├─ kustomize-ctrl   applies deploy/flux/ — so the committed tag
       │                   actually reaches the HelmRelease objects
       └─ helm-controller  re-renders charts/tinycrm, upgrades the releases
```

Two environments on the one k3s node, one HelmRelease each:

| | Namespace | Host | Image tag written by |
|---|---|---|---|
| `deploy/flux/staging/` | `tinycrm-staging` | `crm-staging.niecke-it.de` | `promote.yml`, every merge |
| `deploy/flux/prod/` | `tinycrm` | `crm.niecke-it.de` | frozen until the release workflow (#114 step 4) |

`deploy/flux/base/` holds the shared GitRepository and the Flux Kustomization.
The entry point stays `deploy/flux/kustomization.yaml`, the path that
Kustomization reads.

The kustomize step is not optional. A HelmRelease is a cluster object; editing
its manifest in git changes nothing until something applies it. Without that
controller the images get tagged, the sha lands in git, and the cluster silently
keeps running the previous release.

Two things trigger a redeploy, and both are just commits on `main`:

- a chart change under `charts/tinycrm/` — picked up because the HelmRelease
  sets `reconcileStrategy: Revision`, so Flux keys off the git commit rather
  than `Chart.yaml`'s version
- a new image — `promote.yml` writes `sha-<short>` into the staging HelmRelease

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
250 Mi of real memory. Its first admin comes from `create_admin.py` exactly as in
production, with `-n tinycrm-staging`.

### The React client at `/next`

Staging also runs the React client (#122) from the `frontend-next` image, at
`https://crm-staging.niecke-it.de/next/`. It is a path on the Flutter app's
own Ingress, so the same basic auth and `noindex` apply, and it reads the
same `config.json` ConfigMap (mounted at `/srv/next/config.json`).

`frontendNext.enabled` is `false` in the chart and set only in the staging
HelmRelease; production gets it with the cutover. `promote.yml` writes its tag
alongside the others. With the flag on but no tag yet, the chart leaves the
client out instead of failing the render. That covers the merge commit that
introduces it, which reaches Flux before the Deploy commit that writes the
first tag.

## Repository settings this depends on

`promote.yml` pushes a commit to `main`, which the `protect_main` ruleset only
allows for deploy keys. The push therefore goes over SSH with the `DEPLOY_KEY`
secret — a write deploy key on this repository. Without it the promote job fails
at the push step, images are tagged but the deployed sha never moves, and
staging silently keeps running the previous build.

Unlike a `GITHUB_TOKEN` push, a deploy-key push does trigger workflows. promote
skips its own `Deploy <sha> to staging` commits with a job-level `if:`.

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

### Creating an admin user

No signup flow; the first account comes from the CLI.

```bash
read -rsp 'password: ' PW && echo
kubectl -n tinycrm exec -i deploy/tinycrm-backend -- \
  env PYTHONPATH=/app python scripts/create_admin.py you@niecke-it.de "$PW"
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
  # optional, the React client at /next:
  #   --set frontendNext.enabled=true --set frontendNext.image.tag=sha-<short>
```

The chart has no default image tag, so leaving these out fails the render.

`values-secrets.yaml` is gitignored. `values-crm-new.yaml` exists so a manual
install does not default to the live hostname — cert-manager would fail http-01
against it while DNS still points at GCP, and Let's Encrypt rate-limits failed
validations per account.
