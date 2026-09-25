{{- define "tinycrm.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "tinycrm.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "tinycrm.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{ include "tinycrm.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "tinycrm.selectorLabels" -}}
app.kubernetes.io/name: {{ include "tinycrm.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Name of the CloudNativePG Cluster. The operator derives its Services from this,
so the read-write endpoint is <cluster>-rw — that is what DATABASE_URL points at.
*/}}
{{- define "tinycrm.postgresCluster" -}}
{{- printf "%s-postgres" (include "tinycrm.fullname" .) -}}
{{- end -}}

{{- define "tinycrm.postgresHost" -}}
{{- printf "%s-rw" (include "tinycrm.postgresCluster" .) -}}
{{- end -}}

{{/*
Used by both the backend Secret and the migration hook's own Secret. The two
cannot share one object: pre-upgrade hooks run before the release's regular
manifests are applied, so the backend Secret does not exist yet when the hook
starts.
*/}}
{{- define "tinycrm.databaseUrl" -}}
{{- printf "postgresql+asyncpg://%s:%s@%s:5432/%s" .Values.postgres.username .Values.postgres.password (include "tinycrm.postgresHost" .) .Values.postgres.database -}}
{{- end -}}

{{/*
Full image reference for one of the application images. The tag has no default:
an unset tag fails the render instead of silently pulling whatever a floating
tag happens to point at. Call with (list "backend" .Values.backend.image).
*/}}
{{- define "tinycrm.image" -}}
{{- $name := index . 0 -}}
{{- $image := index . 1 -}}
{{- $tag := required (printf "%s.image.tag is required — set it to a promoted tag such as sha-<short>" $name) $image.tag -}}
{{- printf "%s:%s" $image.repository $tag -}}
{{- end -}}

{{/*
Whether the React client (#122) renders at all: switched on *and* given a tag.
The tag condition breaks with tinycrm.image's rule of failing on an empty tag,
on purpose: promote.yml writes the tag in the Deploy commit that follows a
merge, so the merge commit itself reaches Flux with enabled=true and no tag
yet. Skipping the React client for that one revision lets the rest of the
release upgrade normally instead of failing to render.
*/}}
{{- define "tinycrm.frontendNext.enabled" -}}
{{- if and .Values.frontendNext.enabled .Values.frontendNext.image.tag -}}true{{- end -}}
{{- end -}}
