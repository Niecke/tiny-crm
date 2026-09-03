# Deploying tinyCRM

Merges to `main` reach the cluster through Flux. Nothing pushes: the cluster
pulls, so no GitHub workflow holds cluster credentials and the k3s API stays
unpublished.

```
merge to main
  ├─ promote.yml           retags the tested image digest, commits the sha
  │                        into deploy/flux/helmrelease.yaml
  └─ source-controller     fetches the commit
       ├─ kustomize-ctrl   applies deploy/flux/ — so the committed tag
       │                   actually reaches the HelmRelease object
       └─ helm-controller  re-renders charts/tinycrm, upgrades the release
```

The kustomize step is not optional. A HelmRelease is a cluster object; editing
its manifest in git changes nothing until something applies it. Without that
controller the images get tagged, the sha lands in git, and the cluster silently
keeps running the previous release.

Two things trigger a redeploy, and both are just commits on `main`:

- a chart change under `charts/tinycrm/` — picked up because the HelmRelease
  sets `reconcileStrategy: Revision`, so Flux keys off the git commit rather
  than `Chart.yaml`'s version
- a new image — `promote.yml` writes the short sha into the HelmRelease

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
minio:
  rootUser: tinycrm
  rootPassword: $(openssl rand -base64 24)
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
kubectl apply -f deploy/flux/
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

## Repository settings this depends on

`promote.yml` pushes a commit to `main`. Branch protection must allow it —
either exempt the GitHub Actions app, or allow the push from the `promote`
workflow. Without this the promote job fails at the push step, images are tagged
but the deployed sha never moves, and the cluster silently keeps running the
previous release.

The push uses `GITHUB_TOKEN`, and GitHub does not re-trigger workflows for
commits made with it, so promote cannot loop back into itself.

## Cutover

Phase 7's DNS flip pairs with editing one line in
`deploy/flux/helmrelease.yaml`:

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

## Local install, without Flux

For a k3d cluster, or to test the chart before merging:

```bash
helm upgrade --install tinycrm ./charts/tinycrm \
  -n tinycrm --create-namespace \
  -f charts/tinycrm/values-crm-new.yaml \
  -f values-secrets.yaml
```

`values-secrets.yaml` is gitignored. `values-crm-new.yaml` exists so a manual
install does not default to the live hostname — cert-manager would fail http-01
against it while DNS still points at GCP, and Let's Encrypt rate-limits failed
validations per account.
